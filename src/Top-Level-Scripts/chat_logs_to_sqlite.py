"""Ingest Copilot chat debug exports (``*.chatreplay.json``) and VS Code chat
session archives into a SQLite catalog so downstream tools—including LLMs—can
query accumulated chat history.

The script can be pointed at either a single export file or a directory. By
default it also scans the well-known Copilot Chat global-storage folders and
workspace chat session caches so you can drop exports there and re-run the
importer without extra flags.

Schema summary (created on first run):
- ``prompts``: one row per exported prompt, keyed by promptId.
- ``prompt_logs``: flattened log entries (requests, tool calls, elements) with
  the original JSON preserved.
- ``tool_results``: optional sub-table for structured tool call output when
  available.

Repeated imports are idempotent; existing rows are updated when their content
changes. Use ``sqlite3 <db>`` or any client to explore the resulting database.

Example:
    python chat_logs_to_sqlite.py exports/copilot_all_prompts.chatreplay.json
    python chat_logs_to_sqlite.py --db copilot.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

CHATREPLAY_EXTENSION = ".chatreplay.json"
DEFAULT_DB_NAME = "copilot_chat_logs.db"
DEFAULT_OUTPUT_DIR = Path(".vscode") / "CopilotChatHistory"
CATALOG_VERSION = "2"
READ_ME_NAME = "README_CopilotChatHistory.md"
SCHEMA_MANIFEST_NAME = "schema_manifest.json"

SCHEMA_VERSION_HISTORY: List[Dict[str, Any]] = [
    {
        "version": "1",
        "released": "2025-10-18",
        "changes": [
            "Initial catalog with prompts, prompt_logs, tool_results tables, and helper views.",
        ],
    },
    {
        "version": CATALOG_VERSION,
        "released": "2025-10-22",
        "changes": [
            "Added source_kind classifier to prompts for downstream filtering.",
            "Introduced schema migration runner for forward-compatible upgrades.",
        ],
    },
]


class UserVisibleError(RuntimeError):
    """Raised when user-facing validation fails."""


def vscode_user_dirs() -> Sequence[Path]:
    dirs: List[Path] = []
    platform = sys.platform
    home = Path.home()

    if platform.startswith("win"):
        appdata = os.getenv("APPDATA")
        if appdata:
            base = Path(appdata)
            dirs.extend([
                base / "Code" / "User",
                base / "Code - Insiders" / "User",
                base / "Code - OSS" / "User",
            ])
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
        dirs.extend([
            base / "Code" / "User",
            base / "Code - Insiders" / "User",
            base / "Code - OSS" / "User",
        ])
    else:
        config_base = home / ".config"
        dirs.extend([
            config_base / "Code" / "User",
            config_base / "Code - Insiders" / "User",
            config_base / "Code - OSS" / "User",
        ])

    return [path for path in dirs if path.exists()]


def default_storage_dirs() -> Sequence[Path]:
    dirs: List[Path] = []
    for user_dir in vscode_user_dirs():
        candidate = user_dir / "globalStorage" / "github.copilot-chat"
        if candidate.exists():
            dirs.append(candidate)
    return dirs


def default_session_dirs() -> Sequence[Path]:
    dirs: List[Path] = []
    for user_dir in vscode_user_dirs():
        empty_window = user_dir / "globalStorage" / "emptyWindowChatSessions"
        if empty_window.exists():
            dirs.append(empty_window)

        workspace_storage = user_dir / "workspaceStorage"
        if workspace_storage.exists():
            for workspace_dir in workspace_storage.iterdir():
                if not workspace_dir.is_dir():
                    continue
                chat_sessions = workspace_dir / "chatSessions"
                if chat_sessions.exists():
                    dirs.append(chat_sessions)
    return dirs


def gather_input_files(target: Optional[Path]) -> List[Path]:
    seen: Set[Path] = set()
    candidates: List[Path] = []

    def consider(path: Path) -> None:
        if not path.is_file():
            return
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    if target:
        target = target.expanduser()
        if target.is_file():
            consider(target)
        elif target.is_dir():
            for pattern in (f"*{CHATREPLAY_EXTENSION}", "*.json"):
                for item in target.rglob(pattern):
                    consider(item)
        else:
            raise UserVisibleError(f"No such file or directory: {target}")
    else:
        for directory in default_storage_dirs():
            for item in directory.rglob(f"*{CHATREPLAY_EXTENSION}"):
                consider(item)
        for directory in default_session_dirs():
            for item in directory.glob("*.json"):
                consider(item)

    return candidates


def safe_json_dumps(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False)
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return json.dumps(payload, ensure_ascii=True)


def ms_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    return None


def is_vscode_chat_session(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("requests"), list)
        and (
            "version" in data
            or "requesterUsername" in data
            or "responderUsername" in data
        )
    )


def convert_session_to_prompts(data: Dict[str, Any], path: Path) -> List[Dict[str, Any]]:
    requests = data.get("requests")
    if not isinstance(requests, list) or not requests:
        return []

    session_id = str(data.get("sessionId") or path.stem or path.name)
    logs: List[Dict[str, Any]] = []
    first_text: Optional[str] = None

    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            continue

        request_id = str(request.get("requestId") or f"{session_id}:request:{index}")
        time_iso = ms_to_iso(request.get("timestamp"))

        message = request.get("message")
        message_text = None
        if isinstance(message, dict):
            message_text = message.get("text") if isinstance(message.get("text"), str) else None

        if first_text is None and message_text:
            first_text = message_text

        request_log = {key: value for key, value in request.items() if key not in {"response", "result"}}
        request_log["id"] = request_id
        request_log["kind"] = "request"
        if time_iso and "time" not in request_log:
            request_log["time"] = time_iso

        logs.append(request_log)

        response_payload = request.get("response")
        result_payload = request.get("result")
        if response_payload is None and result_payload is None:
            continue

        response_id = str(request.get("responseId") or f"{request_id}:response")
        response_log: Dict[str, Any] = {
            "id": response_id,
            "kind": "response",
            "requestId": request_id,
        }
        if time_iso:
            response_log["time"] = time_iso
        if response_payload is not None:
            response_log["response"] = response_payload
        if result_payload is not None:
            response_log["result"] = result_payload
        if request.get("followups"):
            response_log["followups"] = request.get("followups")
        if request.get("isCanceled"):
            response_log["isCanceled"] = request.get("isCanceled")

        logs.append(response_log)

    session_metadata = {key: value for key, value in data.items() if key != "requests"}

    prompt = {
        "promptId": session_id,
        "prompt": first_text or "",
        "hasSeen": True,
        "logCount": len(logs),
        "logs": logs,
        "session": session_metadata,
    }

    return [prompt]


def load_prompts(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    metadata: Dict[str, Any] = {
        "source_file": str(path),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if isinstance(data, dict) and isinstance(data.get("prompts"), list):
        prompts = [p for p in data["prompts"] if isinstance(p, dict)]
        metadata["source_kind"] = "chatreplay"
    elif isinstance(data, dict) and is_vscode_chat_session(data):
        prompts = convert_session_to_prompts(data, path)
        metadata["source_kind"] = "vscodeSession"
    elif isinstance(data, list):
        prompts = [p for p in data if isinstance(p, dict)]
        metadata["source_kind"] = "chatreplay"
    elif isinstance(data, dict):
        prompts = [data]
        metadata["source_kind"] = "chatreplay"
    else:
        raise UserVisibleError(f"Unrecognized chat history format in {path}")

    return prompts, metadata


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            prompt_id TEXT PRIMARY KEY,
            prompt_text TEXT,
            has_seen INTEGER,
            log_count INTEGER,
            source_file TEXT,
            source_kind TEXT,
            imported_at TEXT,
            raw_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_logs (
            prompt_id TEXT,
            log_id TEXT,
            log_index INTEGER,
            kind TEXT,
            time TEXT,
            summary TEXT,
            raw_json TEXT,
            PRIMARY KEY (prompt_id, log_id),
            FOREIGN KEY (prompt_id) REFERENCES prompts(prompt_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_results (
            prompt_id TEXT,
            log_id TEXT,
            part_index INTEGER,
            content TEXT,
            FOREIGN KEY (prompt_id, log_id) REFERENCES prompt_logs(prompt_id, log_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS tool_call_details AS
        SELECT
            p.prompt_id,
            p.prompt_text,
            p.imported_at,
            l.log_id,
            l.log_index,
            l.kind,
            l.time,
            l.summary,
            l.raw_json AS log_json,
            tr.part_index,
            tr.content AS tool_content
        FROM prompt_logs l
        JOIN prompts p ON p.prompt_id = l.prompt_id
        LEFT JOIN tool_results tr
            ON tr.prompt_id = l.prompt_id
            AND tr.log_id = l.log_id
        WHERE l.kind = 'toolCall'
        """
    )

    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS prompt_activity AS
        SELECT
            p.prompt_id,
            p.prompt_text,
            p.imported_at,
            l.kind,
            COUNT(*) AS entry_count
        FROM prompt_logs l
        JOIN prompts p ON p.prompt_id = l.prompt_id
        GROUP BY p.prompt_id, l.kind
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_logs_kind ON prompt_logs(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prompt_logs_prompt ON prompt_logs(prompt_id, log_index)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_results_prompt ON tool_results(prompt_id, log_id, part_index)"
    )


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(row[1] == column for row in info)


def detect_schema_version(conn: sqlite3.Connection) -> str:
    try:
        cur = conn.execute("SELECT value FROM catalog_metadata WHERE key='schema_version'")
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0])
    except sqlite3.OperationalError:
        pass

    if _table_has_column(conn, "prompts", "source_kind"):
        return "2"

    if _table_has_column(conn, "prompts", "prompt_id"):
        return "1"

    return "0"


def migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    if not _table_has_column(conn, "prompts", "source_kind"):
        conn.execute("ALTER TABLE prompts ADD COLUMN source_kind TEXT")

    conn.execute(
        """
        UPDATE prompts
        SET source_kind = CASE
            WHEN lower(COALESCE(source_file, '')) LIKE '%.chatreplay.json' THEN 'chatreplay'
            WHEN source_file LIKE '%chatSessions%' THEN 'vscodeSession'
            ELSE 'unknown'
        END
        WHERE source_kind IS NULL OR source_kind = ''
        """
    )


MigrationFunc = Callable[[sqlite3.Connection], None]
SCHEMA_MIGRATIONS: Dict[str, Tuple[str, MigrationFunc]] = {
    "1": ("2", migrate_v1_to_v2),
}


def run_schema_migrations(conn: sqlite3.Connection) -> str:
    current = detect_schema_version(conn)
    target = CATALOG_VERSION

    while current != target:
        step = SCHEMA_MIGRATIONS.get(current)
        if not step:
            break
        next_version, func = step
        func(conn)
        migrated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO catalog_metadata(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            ("schema_version", next_version),
        )
        conn.execute(
            """
            INSERT INTO catalog_metadata(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            ("schema_migrated_at_utc", migrated_at),
        )
        current = next_version

    return current


def summarize_log(log: Dict[str, Any]) -> str:
    kind = log.get("kind") or "unknown"
    if kind == "request":
        metadata = log.get("metadata") or {}
        intent = metadata.get("intent") if isinstance(metadata, dict) else None
        return f"Request ({intent})" if intent else "Request"
    if kind == "response":
        result_metadata = log.get("result")
        if isinstance(result_metadata, dict):
            meta = result_metadata.get("metadata")
            if isinstance(meta, dict):
                agent = meta.get("agentId") or meta.get("agent")
                if agent:
                    return f"Response ({agent})"
        return "Response"
    if kind == "toolCall":
        tool = log.get("tool") or log.get("name") or "tool"
        return f"Tool call: {tool}"
    if kind == "element":
        name = log.get("name") or "element"
        return f"Prompt element: {name}"
    return kind


def extract_time(log: Dict[str, Any]) -> Optional[str]:
    value = log.get("time")
    if isinstance(value, str):
        return value
    iso = ms_to_iso(log.get("timestamp"))
    if iso:
        return iso
    metadata = log.get("metadata")
    if isinstance(metadata, dict):
        start = metadata.get("startTime")
        if isinstance(start, str):
            return start
    return None


def iter_tool_parts(log: Dict[str, Any]) -> Iterable[str]:
    content = log.get("response")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                yield item
            else:
                yield safe_json_dumps(item)
    elif isinstance(content, (str, int, float)):
        yield str(content)


def ingest_prompt(conn: sqlite3.Connection, prompt: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    prompt_id = str(prompt.get("promptId") or prompt.get("id") or "")
    if not prompt_id:
        raise UserVisibleError("Prompt is missing a promptId; cannot store.")

    prompt_text = str(prompt.get("prompt") or "")
    has_seen = 1 if prompt.get("hasSeen") else 0
    log_count = int(prompt.get("logCount") or len(prompt.get("logs") or []))
    raw_json = safe_json_dumps(prompt)
    source_file = str(metadata.get("source_file") or "")
    source_kind = str(metadata.get("source_kind") or "").strip()
    if not source_kind:
        lowered = source_file.lower()
        if lowered.endswith(".chatreplay.json"):
            source_kind = "chatreplay"
        elif "chatsessions" in lowered:
            source_kind = "vscodeSession"
        else:
            source_kind = "unknown"

    conn.execute(
        """
        INSERT INTO prompts(prompt_id, prompt_text, has_seen, log_count, source_file, source_kind, imported_at, raw_json)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(prompt_id) DO UPDATE SET
            prompt_text=excluded.prompt_text,
            has_seen=excluded.has_seen,
            log_count=excluded.log_count,
            source_file=excluded.source_file,
            source_kind=excluded.source_kind,
            imported_at=excluded.imported_at,
            raw_json=excluded.raw_json
        """,
        (
            prompt_id,
            prompt_text,
            has_seen,
            log_count,
            source_file,
            source_kind,
            metadata["imported_at"],
            raw_json,
        ),
    )


    logs = prompt.get("logs")
    if not isinstance(logs, list):
        return

    conn.execute("DELETE FROM prompt_logs WHERE prompt_id = ?", (prompt_id,))
    conn.execute("DELETE FROM tool_results WHERE prompt_id = ?", (prompt_id,))

    for index, log in enumerate(logs):
        if not isinstance(log, dict):
            continue
        log_id = str(log.get("id") or f"{prompt_id}:{index}")
        kind = str(log.get("kind") or "unknown")
        summary = summarize_log(log)
        time_value = extract_time(log)
        raw_log_json = safe_json_dumps(log)

        conn.execute(
            """
            INSERT INTO prompt_logs(prompt_id, log_id, log_index, kind, time, summary, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prompt_id,
                log_id,
                index,
                kind,
                time_value,
                summary,
                raw_log_json,
            ),
        )

        if kind == "toolCall":
            for part_index, part in enumerate(iter_tool_parts(log)):
                conn.execute(
                    """
                    INSERT INTO tool_results(prompt_id, log_id, part_index, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        prompt_id,
                        log_id,
                        part_index,
                        part,
                    ),
                )

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Copilot chat debug exports into a SQLite database.")
    parser.add_argument(
        "path",
        nargs="?",
        help="Optional path to a chat history file or directory (.chatreplay.json or VS Code chatSessions). When omitted the script scans the default Copilot storage folders.",
    )
    parser.add_argument(
        "--db",

        default=DEFAULT_DB_NAME,
        help="SQLite database file to create or update (default: copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to place the catalog artifacts (default: .vscode/CopilotChatHistory).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing tables before importing (dangerous).",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> Tuple[Path, Path]:
    output_dir = Path(args.output_dir).expanduser()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        if db_path.parent == Path('.'):
            db_path = output_dir / db_path
        else:
            db_path = Path.cwd() / db_path
    output_dir = db_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, db_path


def update_metadata(conn: sqlite3.Connection, *, source_files: Sequence[Path]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO catalog_metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        ("schema_version", CATALOG_VERSION),
    )
    conn.execute(
        """
        INSERT INTO catalog_metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        ("generated_at_utc", generated_at),
    )
    conn.execute(
        """
        INSERT INTO catalog_metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (
            "source_files",
            ",".join(sorted({str(path) for path in source_files})),
        ),
    )

def write_support_files(output_dir: Path, db_path: Path) -> List[Path]:
    manifest_path = output_dir / SCHEMA_MANIFEST_NAME
    readme_path = output_dir / READ_ME_NAME

    manifest = {
        "schema_version": CATALOG_VERSION,
        "database_file": db_path.name,
        "schema_history": SCHEMA_VERSION_HISTORY,
        "tables": [
            {
                "name": "prompts",
                "description": "One row per Copilot prompt.",
                "columns": [
                    {"name": "prompt_id", "type": "TEXT", "meaning": "Stable identifier for the prompt."},
                    {"name": "prompt_text", "type": "TEXT", "meaning": "User-authored prompt text."},
                    {"name": "has_seen", "type": "INTEGER", "meaning": "Whether the prompt has been rendered in the UI."},
                    {"name": "log_count", "type": "INTEGER", "meaning": "Number of log entries associated with the prompt."},
                    {
                        "name": "source_file",
                        "type": "TEXT",
                        "meaning": "Original chat history file path (.chatreplay.json or VS Code chatSessions .json).",
                    },
                    {
                        "name": "source_kind",
                        "type": "TEXT",
                        "meaning": "Classifier describing the origin of the prompt (chatreplay, vscodeSession, etc.).",
                    },
                    {"name": "imported_at", "type": "TEXT", "meaning": "UTC timestamp of import."},
                    {"name": "raw_json", "type": "TEXT", "meaning": "Full prompt payload."},
                ],
            },
            {
                "name": "prompt_logs",
                "description": "Detailed log entries per prompt, including tool calls and metadata.",
                "columns": [
                    {"name": "prompt_id", "type": "TEXT", "meaning": "Foreign key to prompts."},
                    {"name": "log_id", "type": "TEXT", "meaning": "Log entry identifier."},
                    {"name": "log_index", "type": "INTEGER", "meaning": "Ordering index."},
                    {"name": "kind", "type": "TEXT", "meaning": "Entry classification (request, toolCall, element, etc.)."},
                    {"name": "time", "type": "TEXT", "meaning": "Timestamp when available."},
                    {"name": "summary", "type": "TEXT", "meaning": "Readable summary of the entry."},
                    {"name": "raw_json", "type": "TEXT", "meaning": "Full log payload."},
                ],
            },
            {
                "name": "tool_results",
                "description": "Flattened tool responses for toolCall entries.",
                "columns": [
                    {"name": "prompt_id", "type": "TEXT", "meaning": "Foreign key to prompts."},
                    {"name": "log_id", "type": "TEXT", "meaning": "Matches prompt_logs.log_id."},
                    {"name": "part_index", "type": "INTEGER", "meaning": "Ordering for multipart responses."},
                    {"name": "content", "type": "TEXT", "meaning": "Tool output snippet."},
                ],
            },
        ],
        "views": [
            {
                "name": "tool_call_details",
                "description": "Convenience view joining prompts, prompt_logs, and tool_results for toolCall entries.",
            },
            {
                "name": "prompt_activity",
                "description": "Aggregated counts of log entry kinds per prompt.",
            },
        ],
        "sample_queries": [
            "SELECT prompt_id, prompt_text FROM prompts ORDER BY imported_at DESC LIMIT 5;",
            "SELECT prompt_text, kind, summary FROM prompt_logs JOIN prompts USING(prompt_id) WHERE kind <> 'toolCall' ORDER BY imported_at DESC LIMIT 10;",
            "SELECT prompt_text, summary, tool_content FROM tool_call_details WHERE tool_content IS NOT NULL ORDER BY imported_at DESC LIMIT 5;",
            "SELECT kind, COUNT(*) AS total FROM prompt_logs GROUP BY kind ORDER BY total DESC;",
        ],
    }

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme_lines = [
        "# Copilot Chat History Catalog",
        "",
        f"- Database file: `{db_path.name}`",
        f"- Schema version: {CATALOG_VERSION}",
        "- Views: `tool_call_details`, `prompt_activity`",
        "",
        "## Purpose",
        "This catalog normalizes Copilot Chat prompt logs so language models and analysts can query historical tool usage, timelines, and prompt content without bespoke parsing.",
        "",
        "## Tables",
        "- `prompts`: One row per chat prompt; contains text, origin file/kind classifiers, and raw JSON payload.",
        "- `prompt_logs`: Entries tied to each prompt (requests, tool calls, elements).",
        "- `tool_results`: Flattened tool outputs linked to tool-call log rows.",
        "- `catalog_metadata`: Key/value metadata about the catalog build.",
        "",
        "## Views",
        "- `tool_call_details`: Joins prompts, logs, and tool outputs for direct inspection of tool calls.",
        "- `prompt_activity`: Aggregates how many entries of each kind appear per prompt.",
        "",
        "## Sample Queries",
        "```sql",
        "SELECT prompt_id, prompt_text",
        "FROM prompts",
        "ORDER BY imported_at DESC",
        "LIMIT 5;",
        "",
        "SELECT prompt_text, summary, tool_content",
        "FROM tool_call_details",
        "WHERE tool_content IS NOT NULL",
        "ORDER BY imported_at DESC",
        "LIMIT 5;",
        "",
        "SELECT p.prompt_text, l.summary",
        "FROM prompt_logs l",
        "JOIN prompts p ON p.prompt_id = l.prompt_id",
        "WHERE l.kind = 'request'",
        "ORDER BY l.time DESC",
        "LIMIT 10;",
        "",
        "SELECT kind, COUNT(*) AS total",
        "FROM prompt_logs",
        "GROUP BY kind",
        "ORDER BY total DESC;",
        "```",
        "",
        "## LLM Prompting Tips",
        "1. Ask the model to read this README first so it understands the table relationships.",
        "2. Encourage use of the `tool_call_details` view for most tool analytics.",
        "3. Remind the model that timestamps are stored as text in ISO-8601 format.",
        "4. For large result sets, add `LIMIT` clauses to keep outputs manageable.",
        "",
        "## Regeneration",
        "Run `python script/chat_logs_to_sqlite.py` to refresh the catalog after exporting new prompt logs or mirroring live data.",
    ]

    readme_lines.extend(["", "## Schema Change Log", ""])
    for entry in SCHEMA_VERSION_HISTORY:
        version = entry.get("version", "?")
        released = entry.get("released", "unknown date")
        readme_lines.append(f"- v{version} ({released})")
        for change in entry.get("changes", []):
            readme_lines.append(f"  - {change}")
    readme_lines.append("")

    readme_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    return [manifest_path, readme_path]


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    output_dir, db_path = resolve_paths(args)
    target_path = Path(args.path).expanduser() if args.path else None

    files = gather_input_files(target_path)
    if not files:
        raise UserVisibleError(
            "No Copilot chat history files found (.chatreplay.json or chatSessions *.json)."
        )

    conn = sqlite3.connect(str(db_path))
    try:
        if args.reset:
            conn.executescript(
                """
                DROP TABLE IF EXISTS tool_results;
                DROP TABLE IF EXISTS prompt_logs;
                DROP TABLE IF EXISTS prompts;
                """
            )
        ensure_schema(conn)
        run_schema_migrations(conn)

        imported_files: List[Path] = []
        total_prompts = 0

        for file_path in files:
            prompts, metadata = load_prompts(file_path)
            if not prompts:
                continue
            imported_files.append(file_path)
            for prompt in prompts:
                ingest_prompt(conn, prompt, metadata)
            total_prompts += len(prompts)

        if not imported_files:
            raise UserVisibleError("No usable chat history entries were found.")

        update_metadata(conn, source_files=imported_files)
        conn.commit()
    finally:
        conn.close()

    support_files = write_support_files(output_dir, db_path)

    print(f"Imported {total_prompts} prompt(s) from {len(imported_files)} file(s) into {db_path}")
    for path in support_files:
        print(f"Wrote {path}")


if __name__ == "__main__":
    try:
        main()
    except UserVisibleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
