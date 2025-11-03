"""Normalize Copilot chat telemetry into a workspace-scoped SQLite catalog.

This module ingests VS Code chat session archives (and legacy ``*.chatreplay``
exports) into a normalized schema, applies redaction safeguards, aggregates
repeat failure metrics, and regenerates catalog companion files. The goal is to
make historical Copilot interactions queryable without bespoke parsing while
keeping records scoped to the active workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple


CHATREPLAY_EXTENSION = ".chatreplay.json"
DEFAULT_DB_NAME = "copilot_chat_logs.db"
DEFAULT_OUTPUT_DIR = Path(".vscode") / "CopilotChatHistory"
READ_ME_NAME = "README_CopilotChatHistory.md"
SCHEMA_MANIFEST_NAME = "schema_manifest.json"
CATALOG_VERSION = "3"

SCHEMA_VERSION_HISTORY = [
    {
        "version": CATALOG_VERSION,
        "released": "2024-11-01",
        "changes": [
            "Normalize Copilot chat telemetry into workspace-scoped tables.",
            "Persist repeat command failure metrics (SC-004).",
            "Regenerate catalog manifest and README on each ingest run.",
        ],
    }
]


class UserVisibleError(Exception):
    """Raised for user-facing failures that should not surface stack traces."""


def safe_json_dumps(payload: Any) -> str:
    """JSON encode a payload while gracefully handling unserialisable objects."""

    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=False)
    except (TypeError, ValueError):
        return json.dumps(str(payload), ensure_ascii=False, sort_keys=False)


def ensure_within_workspace(path: Path, workspace_root: Path) -> None:
    """Ensure ``path`` does not escape the active workspace boundary."""

    try:
        path.resolve().relative_to(workspace_root.resolve())
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise UserVisibleError(
            f"Path {path} is outside the workspace boundary {workspace_root}."
        ) from exc


def compute_workspace_fingerprint(workspace_root: Path) -> str:
    """Return a stable fingerprint for the workspace location."""

    resolved = workspace_root.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()
    return digest[:16]


def _default_storage_dirs() -> List[Path]:
    """Best-effort list of VS Code global storage directories to scan."""

    candidates: List[Path] = []
    env_paths = [
        os.getenv("APPDATA"),
        os.getenv("XDG_DATA_HOME"),
        os.getenv("HOME"),
    ]
    for root in env_paths:
        if not root:
            continue
        path = Path(root)
        candidates.append(path / "Code" / "User" / "globalStorage" / "github.copilot-chat" / "chatSessions")
        candidates.append(path / "VSCodium" / "User" / "globalStorage" / "github.copilot-chat" / "chatSessions")
    return candidates


def gather_input_files(target: Optional[Path]) -> List[Path]:
    """Collect candidate chat history files to ingest."""

    candidates: List[Path] = []
    seen: set[Path] = set()

    def consider(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        if not resolved.is_file():
            return
        if resolved.suffix.lower() == ".json" or resolved.name.endswith(CHATREPLAY_EXTENSION):
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
        for directory in _default_storage_dirs():
            if directory.is_dir():
                for item in directory.glob("*.json"):
                    consider(item)

    candidates.sort()
    return candidates


def is_vscode_chat_session(payload: Mapping[str, Any]) -> bool:
    return isinstance(payload.get("requests"), list)


def convert_prompt_to_session(prompt: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """Convert a chatreplay prompt entry into a synthetic session payload."""

    prompt_json = safe_json_dumps(prompt)
    base_id = prompt.get("promptId") or prompt.get("id") or hashlib.sha1(prompt_json.encode("utf-8")).hexdigest()
    session_id = str(base_id)
    message_text = str(prompt.get("prompt") or "")
    request_id = str(prompt.get("promptId") or f"{session_id}:request")
    request = {
        "requestId": request_id,
        "message": {
            "text": message_text,
            "parts": [
                {
                    "kind": "text",
                    "text": message_text,
                    "range": None,
                    "editorRange": None,
                }
            ],
        },
        "response": [],
        "followups": [],
        "isCanceled": False,
        "timestamp": None,
        "result": {"messages": []},
    }

    logs = prompt.get("logs") if isinstance(prompt.get("logs"), list) else []
    for log in logs:
        if not isinstance(log, Mapping):
            continue
        if log.get("kind") == "response":
            payload = log.get("response") or log.get("result") or ""
            request.setdefault("response", []).append(
                {
                    "value": payload if isinstance(payload, str) else safe_json_dumps(payload),
                    "supportThemeIcons": False,
                    "supportHtml": False,
                }
            )
            request.setdefault("result", {}).setdefault("messages", []).append(
                {
                    "role": "assistant",
                    "content": payload if isinstance(payload, str) else safe_json_dumps(payload),
                }
            )
        if log.get("kind") == "request" and isinstance(log.get("followups"), list):
            followups = [item for item in log["followups"] if isinstance(item, Mapping)]
            request.setdefault("followups", []).extend(followups)

    return {
        "version": 1,
        "sessionId": session_id,
        "initialLocation": "panel",
        "creationDate": prompt.get("timestamp"),
        "lastMessageDate": prompt.get("timestamp"),
        "requests": [request],
    }


def load_session_payloads(path: Path) -> Tuple[List[MutableMapping[str, Any]], str]:
    """Load a chat archive and normalise it into chat session payloads."""

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        sessions = [convert_prompt_to_session(item) for item in data if isinstance(item, Mapping)]
        return sessions, "chatreplay"

    if isinstance(data, Mapping):
        if is_vscode_chat_session(data):
            return [dict(data)], "vscodeSession"
        if isinstance(data.get("prompts"), list):
            sessions = [convert_prompt_to_session(item) for item in data["prompts"] if isinstance(item, Mapping)]
            return sessions, "chatreplay"
        return [convert_prompt_to_session(data)], "chatreplay"

    raise UserVisibleError(f"Unrecognized chat history format in {path}")


def extract_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def extract_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return safe_json_dumps(value)


def parse_exit_code(payload: Any, *, _seen: Optional[Set[int]] = None) -> Optional[int]:
    if _seen is None:
        _seen = set()

    obj_id = id(payload)
    if obj_id in _seen:
        return None
    _seen.add(obj_id)

    if isinstance(payload, Mapping):
        for key in ("exitCode", "exit_code", "code"):
            if key in payload:
                code = extract_int(payload.get(key))
                if code is not None:
                    return code
        for value in payload.values():
            code = parse_exit_code(value, _seen=_seen)
            if code is not None:
                return code
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in payload:
            code = parse_exit_code(item, _seen=_seen)
            if code is not None:
                return code
    elif isinstance(payload, str):
        match = re.search(r"exit code\s*(-?\d+)", payload, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def determine_command_text(request: Mapping[str, Any], metadata: Mapping[str, Any]) -> Optional[str]:
    candidates: List[Optional[str]] = []
    if isinstance(metadata, Mapping):
        candidates.extend(
            metadata.get(key) for key in ("command", "lastCommand", "toolCommand")
        )
    candidates.extend(request.get(key) for key in ("command", "lastCommand"))

    message_text: Optional[str] = None
    message = request.get("message") if isinstance(request.get("message"), Mapping) else {}
    if isinstance(message, Mapping):
        message_text = message.get("text")

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    for source in (metadata, request):
        command = _walk_command_hints(source)
        if command:
            return command

    if isinstance(message_text, str) and message_text.strip():
        return message_text.strip()
    return None


def _normalise_command_candidate(value: Any) -> Optional[str]:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            return candidate
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
        if parts:
            return " ".join(parts)
    return None


def _walk_command_hints(payload: Any, *, _seen: Optional[Set[int]] = None) -> Optional[str]:
    if _seen is None:
        _seen = set()

    obj_id = id(payload)
    if obj_id in _seen:
        return None
    _seen.add(obj_id)

    if isinstance(payload, Mapping):
        command_line = payload.get("commandLine")
        candidate = _normalise_command_candidate(command_line)
        if candidate:
            return candidate
        if isinstance(command_line, Mapping):
            candidate = _normalise_command_candidate(command_line.get("original"))
            if candidate:
                return candidate

        for key in ("command", "toolCommand", "lastCommand", "fullCommand"):
            candidate = _normalise_command_candidate(payload.get(key))
            if candidate:
                return candidate

        for key in ("argv", "args"):
            candidate = _normalise_command_candidate(payload.get(key))
            if candidate:
                return candidate

        for value in payload.values():
            command = _walk_command_hints(value, _seen=_seen)
            if command:
                return command
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in payload:
            command = _walk_command_hints(item, _seen=_seen)
            if command:
                return command
    return None


class Redactor:
    SECRET_PATTERNS = [
        re.compile(r"(token|secret|key)=([A-Za-z0-9_\-]{6,})", re.IGNORECASE),
        re.compile(r"[A-Za-z0-9+/=_-]{32,}"),
    ]

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.redacted_count = 0

    def _redact(self, text: str) -> str:
        if not self.enabled:
            return text

        redacted = text

        def substitute(match: re.Match[str]) -> str:
            self.redacted_count += 1
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}=<redacted>"
            return "<redacted>"

        for pattern in self.SECRET_PATTERNS:
            redacted = pattern.sub(substitute, redacted)
        return redacted

    def redact_text(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return self._redact(value)

    def dumps(self, payload: Any) -> Optional[str]:
        if payload is None:
            return None
        text = safe_json_dumps(payload)
        return self._redact(text)


@dataclass
class AuditLog:
    workspace_root: Path
    output_dir: Path
    db_path: Path
    redaction_enabled: bool
    files: List[str] = field(default_factory=list)
    sessions_ingested: int = 0
    requests_ingested: int = 0
    warnings: List[str] = field(default_factory=list)
    secrets_redacted: int = 0

    def record_file(self, path: Path) -> None:
        self.files.append(str(path))

    def record_session(self) -> None:
        self.sessions_ingested += 1

    def record_requests(self, count: int) -> None:
        self.requests_ingested += count

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def record_redactions(self, count: int) -> None:
        self.secrets_redacted += count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "output_dir": str(self.output_dir),
            "database_path": str(self.db_path),
            "redaction_enabled": self.redaction_enabled,
            "files": self.files,
            "sessions_ingested": self.sessions_ingested,
            "requests_ingested": self.requests_ingested,
            "warnings": self.warnings,
            "secrets_redacted": self.secrets_redacted,
        }


@dataclass
class RepeatFailureEntry:
    command_text: str
    exit_code: int
    occurrence_count: int
    last_seen_ms: int
    request_id: str
    sample_snippet: str
    payload_json: Optional[str]


class RepeatFailureAggregator:
    def __init__(self, workspace_fingerprint: str, redactor: Redactor) -> None:
        self.workspace_fingerprint = workspace_fingerprint
        self.redactor = redactor
        self._entries: Dict[Tuple[str, int], RepeatFailureEntry] = {}

    def register(
        self,
        *,
        request_id: str,
        command_text: Optional[str],
        exit_code: Optional[int],
        timestamp_ms: Optional[int],
        payload: Mapping[str, Any],
    ) -> None:
        if command_text is None or not command_text.strip():
            return
        if exit_code is None or exit_code == 0:
            return
        canonical = command_text.strip()
        command_hash = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
        key = (command_hash, exit_code)
        redacted_payload = self.redactor.dumps(payload)
        if redacted_payload and len(redacted_payload) > 20000:
            redacted_payload = redacted_payload[:20000] + "..."
        snippet = self.redactor.redact_text(canonical) or ""
        snippet = snippet[:200]
        ts = timestamp_ms or 0

        existing = self._entries.get(key)
        if existing:
            existing.occurrence_count += 1
            if ts >= existing.last_seen_ms:
                existing.last_seen_ms = ts
                existing.request_id = request_id
                existing.sample_snippet = snippet
                existing.payload_json = redacted_payload
        else:
            self._entries[key] = RepeatFailureEntry(
                command_text=canonical,
                exit_code=exit_code,
                occurrence_count=1,
                last_seen_ms=ts,
                request_id=request_id,
                sample_snippet=snippet,
                payload_json=redacted_payload,
            )

    def persist(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "DELETE FROM metrics_repeat_failures WHERE workspace_fingerprint = ?",
            (self.workspace_fingerprint,),
        )
        for (command_hash, exit_code), entry in self._entries.items():
            conn.execute(
                """
                INSERT INTO metrics_repeat_failures(
                    workspace_fingerprint,
                    command_hash,
                    command_text,
                    exit_code,
                    occurrence_count,
                    last_seen_ms,
                    request_id,
                    sample_snippet,
                    redacted_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.workspace_fingerprint,
                    command_hash,
                    entry.command_text,
                    exit_code,
                    entry.occurrence_count,
                    entry.last_seen_ms,
                    entry.request_id,
                    entry.sample_snippet,
                    entry.payload_json,
                ),
            )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            workspace_fingerprint TEXT NOT NULL,
            version INTEGER,
            requester_username TEXT,
            responder_username TEXT,
            initial_location TEXT,
            creation_date_ms INTEGER,
            last_message_date_ms INTEGER,
            custom_title TEXT,
            is_imported INTEGER,
            source_file TEXT,
            raw_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            session_id TEXT REFERENCES chat_sessions(session_id) ON DELETE SET NULL,
            descriptor_json TEXT,
            is_default INTEGER,
            locations_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
            workspace_fingerprint TEXT NOT NULL,
            timestamp_ms INTEGER,
            prompt_text TEXT,
            response_id TEXT,
            agent_id TEXT,
            is_canceled INTEGER,
            timing_first_progress_ms INTEGER,
            timing_total_ms INTEGER,
            result_metadata_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_parts (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            part_index INTEGER NOT NULL,
            kind TEXT,
            text TEXT,
            range_json TEXT,
            editor_range_json TEXT,
            PRIMARY KEY (request_id, part_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_variables (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            variable_id TEXT NOT NULL,
            name TEXT,
            value_json TEXT,
            is_file INTEGER,
            model_description TEXT,
            PRIMARY KEY (request_id, variable_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            response_index INTEGER NOT NULL,
            value TEXT,
            supports_html INTEGER,
            supports_theme_icons INTEGER,
            PRIMARY KEY (request_id, response_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS result_messages (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            message_index INTEGER NOT NULL,
            role TEXT,
            content TEXT,
            PRIMARY KEY (request_id, message_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS followups (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            followup_index INTEGER NOT NULL,
            kind TEXT,
            agent_id TEXT,
            message TEXT,
            PRIMARY KEY (request_id, followup_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS content_references (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            reference_index INTEGER NOT NULL,
            uri_json TEXT,
            range_json TEXT,
            PRIMARY KEY (request_id, reference_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS code_citations (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            citation_index INTEGER NOT NULL,
            citation_json TEXT,
            PRIMARY KEY (request_id, citation_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_outputs (
            request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
            output_index INTEGER NOT NULL,
            tool_kind TEXT,
            payload_json TEXT,
            PRIMARY KEY (request_id, output_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_repeat_failures (
            workspace_fingerprint TEXT NOT NULL,
            command_hash TEXT NOT NULL,
            command_text TEXT,
            exit_code INTEGER NOT NULL,
            occurrence_count INTEGER NOT NULL,
            last_seen_ms INTEGER,
            request_id TEXT,
            sample_snippet TEXT,
            redacted_payload_json TEXT,
            PRIMARY KEY (workspace_fingerprint, command_hash, exit_code)
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


def run_schema_migrations(conn: sqlite3.Connection) -> None:
    # The current implementation only needs to guarantee catalog_metadata entries.
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
        ("schema_migrated_at_utc", generated_at),
    )


def persist_session(
    conn: sqlite3.Connection,
    *,
    session: MutableMapping[str, Any],
    source_file: Path,
    source_kind: str,
    workspace_fingerprint: str,
    redactor: Redactor,
    aggregator: RepeatFailureAggregator,
    audit: AuditLog,
) -> int:
    session_id = str(session.get("sessionId") or session.get("sessionID") or "")
    if not session_id:
        audit.add_warning(f"Skipped session without sessionId from {source_file}")
        return 0

    requests = session.get("requests")
    if not isinstance(requests, list) or not requests:
        audit.add_warning(f"Session {session_id} in {source_file} has no requests")
        return 0

    conn.execute("DELETE FROM requests WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))

    sanitized_session = redactor.dumps(session) or safe_json_dumps(session)
    creation_ms = extract_int(session.get("creationDate"))
    last_ms = extract_int(session.get("lastMessageDate"))

    conn.execute(
        """
        INSERT INTO chat_sessions(
            session_id,
            workspace_fingerprint,
            version,
            requester_username,
            responder_username,
            initial_location,
            creation_date_ms,
            last_message_date_ms,
            custom_title,
            is_imported,
            source_file,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            workspace_fingerprint,
            extract_int(session.get("version")),
            session.get("requesterUsername"),
            session.get("responderUsername"),
            session.get("initialLocation"),
            creation_ms,
            last_ms,
            session.get("customTitle"),
            int(bool(session.get("isImported"))),
            str(source_file),
            sanitized_session,
        ),
    )

    inserted_requests = 0
    for index, raw_request in enumerate(requests):
        if not isinstance(raw_request, MutableMapping):
            continue

        request_id = str(raw_request.get("requestId") or raw_request.get("id") or f"{session_id}:{index}")
        timestamp_ms = extract_int(raw_request.get("timestamp"))
        message = raw_request.get("message") if isinstance(raw_request.get("message"), Mapping) else {}
        prompt_text = None
        if isinstance(message, Mapping):
            prompt_text = redactor.redact_text(message.get("text"))

        response_id = raw_request.get("responseId") if isinstance(raw_request.get("responseId"), str) else None
        agent_payload = raw_request.get("agent") if isinstance(raw_request.get("agent"), Mapping) else None
        agent_id = agent_payload.get("id") if isinstance(agent_payload, Mapping) else None

        if agent_payload and agent_id:
            conn.execute(
                """
                INSERT INTO agents(agent_id, session_id, descriptor_json, is_default, locations_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    descriptor_json = excluded.descriptor_json,
                    is_default = excluded.is_default,
                    locations_json = excluded.locations_json
                """,
                (
                    agent_id,
                    session_id,
                    redactor.dumps(agent_payload) or safe_json_dumps(agent_payload),
                    int(bool(agent_payload.get("isDefault"))),
                    redactor.dumps(agent_payload.get("locations")),
                ),
            )

        result = raw_request.get("result") if isinstance(raw_request.get("result"), Mapping) else {}
        timings = result.get("timings") if isinstance(result.get("timings"), Mapping) else {}
        metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}

        conn.execute(
            """
            INSERT INTO requests(
                request_id,
                session_id,
                workspace_fingerprint,
                timestamp_ms,
                prompt_text,
                response_id,
                agent_id,
                is_canceled,
                timing_first_progress_ms,
                timing_total_ms,
                result_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                session_id,
                workspace_fingerprint,
                timestamp_ms,
                prompt_text,
                response_id,
                agent_id,
                int(bool(raw_request.get("isCanceled"))),
                extract_int(timings.get("firstProgress")),
                extract_int(timings.get("totalElapsed")),
                redactor.dumps(metadata) or (safe_json_dumps(metadata) if metadata else None),
            ),
        )

        parts = None
        if isinstance(message, Mapping):
            parts = message.get("parts")
        if isinstance(parts, list):
            for part_index, part in enumerate(parts):
                if not isinstance(part, Mapping):
                    continue
                conn.execute(
                    """
                    INSERT INTO request_parts(request_id, part_index, kind, text, range_json, editor_range_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        part_index,
                        part.get("kind"),
                        redactor.redact_text(part.get("text")) if isinstance(part.get("text"), str) else extract_text(part.get("text")),
                        redactor.dumps(part.get("range")),
                        redactor.dumps(part.get("editorRange")),
                    ),
                )

        variables = raw_request.get("variableData") if isinstance(raw_request.get("variableData"), list) else []
        for variable in variables:
            if not isinstance(variable, Mapping):
                continue
            variable_id = str(variable.get("id") or variable.get("name") or f"var-{len(variable)}")
            conn.execute(
                """
                INSERT INTO request_variables(request_id, variable_id, name, value_json, is_file, model_description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    variable_id,
                    variable.get("name"),
                    redactor.dumps(variable.get("value")),
                    int(bool(variable.get("isFile"))),
                    variable.get("modelDescription"),
                ),
            )

        responses = raw_request.get("response") if isinstance(raw_request.get("response"), list) else []
        for response_index, response in enumerate(responses):
            if not isinstance(response, Mapping):
                continue
            conn.execute(
                """
                INSERT INTO responses(request_id, response_index, value, supports_html, supports_theme_icons)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    response_index,
                    redactor.redact_text(extract_text(response.get("value"))),
                    int(bool(response.get("supportHtml"))),
                    int(bool(response.get("supportThemeIcons"))),
                ),
            )

        result_messages = result.get("messages") if isinstance(result.get("messages"), list) else []
        for message_index, item in enumerate(result_messages):
            if not isinstance(item, Mapping):
                continue
            conn.execute(
                """
                INSERT INTO result_messages(request_id, message_index, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    message_index,
                    item.get("role"),
                    redactor.redact_text(extract_text(item.get("content"))),
                ),
            )

        followups = raw_request.get("followups") if isinstance(raw_request.get("followups"), list) else []
        for followup_index, followup in enumerate(followups):
            if not isinstance(followup, Mapping):
                continue
            conn.execute(
                """
                INSERT INTO followups(request_id, followup_index, kind, agent_id, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    followup_index,
                    followup.get("kind"),
                    followup.get("agentId"),
                    redactor.redact_text(followup.get("message")) if isinstance(followup.get("message"), str) else extract_text(followup.get("message")),
                ),
            )

        content_refs = raw_request.get("contentReferences") if isinstance(raw_request.get("contentReferences"), list) else []
        for reference_index, reference in enumerate(content_refs):
            if not isinstance(reference, Mapping):
                continue
            conn.execute(
                """
                INSERT INTO content_references(request_id, reference_index, uri_json, range_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    reference_index,
                    redactor.dumps(reference.get("reference")),
                    redactor.dumps(reference.get("reference", {}).get("range")) if isinstance(reference.get("reference"), Mapping) else None,
                ),
            )

        code_citations = raw_request.get("codeCitations") if isinstance(raw_request.get("codeCitations"), list) else []
        for citation_index, citation in enumerate(code_citations):
            if not isinstance(citation, Mapping):
                continue
            conn.execute(
                """
                INSERT INTO code_citations(request_id, citation_index, citation_json)
                VALUES (?, ?, ?)
                """,
                (
                    request_id,
                    citation_index,
                    redactor.dumps(citation),
                ),
            )

        tool_outputs: List[Mapping[str, Any]] = []
        metadata_outputs = metadata.get("codeBlocks") if isinstance(metadata.get("codeBlocks"), list) else []
        for block in metadata_outputs:
            if isinstance(block, Mapping):
                tool_outputs.append({"kind": "codeBlock", "payload": block})
        if isinstance(raw_request.get("toolOutputs"), list):
            for item in raw_request["toolOutputs"]:
                if isinstance(item, Mapping):
                    tool_outputs.append({"kind": item.get("kind") or "toolOutput", "payload": item})

        for output_index, output in enumerate(tool_outputs):
            conn.execute(
                """
                INSERT INTO tool_outputs(request_id, output_index, tool_kind, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    request_id,
                    output_index,
                    output.get("kind"),
                    redactor.dumps(output.get("payload")) or safe_json_dumps(output.get("payload")),
                ),
            )

        exit_code = parse_exit_code(metadata) or parse_exit_code(result) or None
        if exit_code is None:
            for resp in responses:
                code = parse_exit_code(resp)
                if code is not None:
                    exit_code = code
                    break

        command_text = determine_command_text(raw_request, metadata)
        aggregator.register(
            request_id=request_id,
            command_text=command_text,
            exit_code=exit_code,
            timestamp_ms=timestamp_ms,
            payload={"metadata": metadata, "response": responses},
        )

        inserted_requests += 1

    return inserted_requests


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
        ("source_files", ",".join(sorted({str(path) for path in source_files}))),
    )


SCHEMA_TABLES: Sequence[Mapping[str, Any]] = [
    {
        "name": "chat_sessions",
        "description": "One row per Copilot chat session scoped to this workspace.",
        "columns": [
            {"name": "session_id", "type": "TEXT", "meaning": "Stable session identifier."},
            {"name": "workspace_fingerprint", "type": "TEXT", "meaning": "Hash anchoring the workspace."},
            {"name": "creation_date_ms", "type": "INTEGER", "meaning": "Session creation epoch timestamp."},
            {"name": "source_file", "type": "TEXT", "meaning": "Original JSON source path."},
        ],
    },
    {
        "name": "requests",
        "description": "Normalized prompt turns with timing, agent, and metadata.",
        "columns": [
            {"name": "request_id", "type": "TEXT", "meaning": "Unique request identifier."},
            {"name": "prompt_text", "type": "TEXT", "meaning": "Redacted user prompt."},
            {"name": "agent_id", "type": "TEXT", "meaning": "Agent responding to the request."},
            {"name": "timing_total_ms", "type": "INTEGER", "meaning": "Total elapsed time."},
        ],
    },
    {
        "name": "tool_outputs",
        "description": "Structured tool outputs and code blocks associated with requests.",
        "columns": [
            {"name": "tool_kind", "type": "TEXT", "meaning": "Descriptor for the tool output."},
            {"name": "payload_json", "type": "TEXT", "meaning": "Redacted JSON payload."},
        ],
    },
    {
        "name": "metrics_repeat_failures",
        "description": "Aggregated telemetry for repeated commands that exited with non-zero codes.",
        "columns": [
            {"name": "command_hash", "type": "TEXT", "meaning": "SHA-1 hash of the normalized command text."},
            {"name": "exit_code", "type": "INTEGER", "meaning": "Exit code shared by the repeated failures."},
            {"name": "occurrence_count", "type": "INTEGER", "meaning": "How many times the command failed."},
            {"name": "sample_snippet", "type": "TEXT", "meaning": "Redacted example of the failing command."},
        ],
    },
]


SCHEMA_SAMPLE_QUERIES = [
    "SELECT session_id, last_message_date_ms FROM chat_sessions ORDER BY last_message_date_ms DESC LIMIT 5;",
    "SELECT request_id, prompt_text, timing_total_ms FROM requests ORDER BY timestamp_ms DESC LIMIT 10;",
    "SELECT request_id, tool_kind FROM tool_outputs ORDER BY request_id LIMIT 10;",
    "SELECT command_text, exit_code, occurrence_count FROM metrics_repeat_failures ORDER BY last_seen_ms DESC LIMIT 10;",
]


def write_support_files(output_dir: Path, db_path: Path, workspace_fingerprint: str) -> List[Path]:
    manifest_path = output_dir / SCHEMA_MANIFEST_NAME
    readme_path = output_dir / READ_ME_NAME

    manifest = {
        "schema_version": CATALOG_VERSION,
        "database_file": db_path.name,
        "workspace_fingerprint": workspace_fingerprint,
        "schema_history": SCHEMA_VERSION_HISTORY,
        "tables": SCHEMA_TABLES,
        "sample_queries": SCHEMA_SAMPLE_QUERIES,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme_lines: List[str] = [
        "# Copilot Chat History Catalog",
        "",
        f"- Database file: `{db_path.name}`",
        f"- Schema version: {CATALOG_VERSION}",
        f"- Workspace fingerprint: `{workspace_fingerprint}`",
        "",
        "## Purpose",
        "This catalog normalizes Copilot chat telemetry into queryable, workspace-scoped tables.",
        "",
        "## Tables",
    ]

    for table in SCHEMA_TABLES:
        readme_lines.append(f"- `{table['name']}`: {table['description']}")
        for column in table.get("columns", []):
            readme_lines.append(
                f"  - `{column['name']}` ({column['type']}): {column['meaning']}"
            )

    readme_lines.extend(["", "## Sample Queries", "```sql"])
    for query in SCHEMA_SAMPLE_QUERIES:
        readme_lines.append(query)
        readme_lines.append("")
    readme_lines.append("```")

    readme_lines.extend(["", "## Schema Change Log"])
    for entry in SCHEMA_VERSION_HISTORY:
        readme_lines.append(f"- v{entry['version']} ({entry['released']})")
        for change in entry.get("changes", []):
            readme_lines.append(f"  - {change}")
    readme_lines.append("")

    readme_path.write_text("\n".join(readme_lines), encoding="utf-8")

    return [manifest_path, readme_path]


def write_audit_log(audit: AuditLog) -> Path:
    audit_dir = audit.workspace_root / "AI-Agent-Workspace" / "_temp"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "ingest_audit.json"
    audit_path.write_text(json.dumps(audit.to_dict(), indent=2), encoding="utf-8")
    return audit_path


def resolve_paths(args: argparse.Namespace, workspace_root: Path) -> Tuple[Path, Path]:
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = workspace_root / output_dir

    db_path = Path(args.db).expanduser()
    if not db_path.is_absolute():
        if db_path.parent == Path('.'):
            db_path = output_dir / db_path
        else:
            db_path = workspace_root / db_path

    output_dir = db_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, db_path


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Copilot chat telemetry into a normalized SQLite catalog."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Optional path to a chat history file or directory (.chatreplay.json or VS Code chatSessions).",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_NAME,
        help="SQLite database file to create or update (default: copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to place catalog artifacts (default: .vscode/CopilotChatHistory).",
    )
    parser.add_argument(
        "--workspace-root",
        help="Optional override for the workspace root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing tables before importing (dangerous).",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable secret redaction safeguards (not recommended).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    workspace_root = Path(args.workspace_root).expanduser() if args.workspace_root else Path.cwd()
    output_dir, db_path = resolve_paths(args, workspace_root)
    ensure_within_workspace(output_dir, workspace_root)

    target_path = Path(args.path).expanduser() if args.path else None
    input_files = gather_input_files(target_path)
    if not input_files:
        raise UserVisibleError("No Copilot chat history files found (.chatreplay.json or chatSessions *.json).")

    audit = AuditLog(
        workspace_root=workspace_root,
        output_dir=output_dir,
        db_path=db_path,
        redaction_enabled=not args.no_redact,
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        if args.reset:
            conn.executescript(
                """
                DELETE FROM metrics_repeat_failures;
                DELETE FROM tool_outputs;
                DELETE FROM code_citations;
                DELETE FROM content_references;
                DELETE FROM followups;
                DELETE FROM result_messages;
                DELETE FROM responses;
                DELETE FROM request_variables;
                DELETE FROM request_parts;
                DELETE FROM requests;
                DELETE FROM chat_sessions;
                DELETE FROM agents;
                """
            )
        run_schema_migrations(conn)

        fingerprint = compute_workspace_fingerprint(workspace_root)
        redactor = Redactor(enabled=not args.no_redact)
        aggregator = RepeatFailureAggregator(fingerprint, redactor)

        imported_files: List[Path] = []
        total_sessions = 0
        total_requests = 0

        for file_path in input_files:
            try:
                sessions, source_kind = load_session_payloads(file_path)
            except json.JSONDecodeError as exc:
                audit.add_warning(
                    f"Skipped {file_path}: invalid JSON (line {exc.lineno} column {exc.colno})."
                )
                continue
            except UserVisibleError as exc:
                audit.add_warning(f"Skipped {file_path}: {exc}")
                continue

            if not sessions:
                audit.add_warning(f"No sessions extracted from {file_path}")
                continue
            imported_files.append(file_path)
            audit.record_file(file_path)

            for session in sessions:
                count = persist_session(
                    conn,
                    session=session,
                    source_file=file_path,
                    source_kind=source_kind,
                    workspace_fingerprint=fingerprint,
                    redactor=redactor,
                    aggregator=aggregator,
                    audit=audit,
                )
                if count:
                    total_sessions += 1
                    total_requests += count
                    audit.record_session()
                    audit.record_requests(count)

        aggregator.persist(conn)
        update_metadata(conn, source_files=imported_files)
        conn.commit()
    finally:
        conn.close()

    audit.record_redactions(redactor.redacted_count)
    support_files = write_support_files(output_dir, db_path, fingerprint)
    audit_path = write_audit_log(audit)

    print(
        f"Imported {total_sessions} session(s) across {total_requests} request(s) from {len(imported_files)} file(s) into {db_path}"
    )
    for path in support_files:
        print(f"Wrote {path}")
    print(f"Wrote audit log {audit_path}")


if __name__ == "__main__":
    try:
        main()
    except UserVisibleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
