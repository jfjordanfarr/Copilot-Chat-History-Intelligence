"""Render Copilot chat session archives to Markdown matching the in-editor view."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from analysis import similarity_threshold as similarity_threshold_module
from chat_logs_to_sqlite import gather_input_files, is_vscode_chat_session
from .markdown import ms_to_iso, render_session_markdown
CATALOG_DB_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"


class UserVisibleError(RuntimeError):
    """Raised when an actionable, friendly error message should be surfaced."""


@dataclass
class SessionRecord:
    session: Dict[str, Any]
    source: Optional[Path]
    workspace_key: Optional[str]
    origin: str


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render VS Code Copilot chat session archives to Markdown."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Optional file or directory to scan for chat sessions. Default scans VS Code global storage.",
    )
    parser.add_argument(
        "--session",
        dest="session_id",
        help="Session ID to export (defaults to most-recent session).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Render every discovered session. When used with --output pointing to a directory, files are written per session.",
    )
    parser.add_argument(
        "--output",
        help="Path to write output. File path when exporting a single session; directory when combined with --all.",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Include non-success status annotations when sessions contain error details.",
    )
    parser.add_argument(
        "--raw-actions",
        action="store_true",
        help="Include raw JSON payloads for action blocks (verbose).",
    )
    parser.add_argument(
        "--lod",
        type=int,
        choices=[0],
        help="Render a specific level-of-detail transcript (0 = Copy-All style with fenced blocks collapsed to ...).",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        help="Override the actionable similarity threshold (0-1). Defaults to the 90th percentile derived from metrics_repeat_failures telemetry.",
    )
    parser.add_argument(
        "--database",
        help="Optional SQLite catalog produced by chat_logs_to_sqlite.py. When supplied, sessions are reconstructed from the database instead of raw JSON files.",
    )
    parser.add_argument(
        "--workspace-directories",
        action="store_true",
        help="Group exported Markdown under directories derived from each session's source workspace.",
    )
    parser.add_argument(
        "--since",
        help="Only include sessions with last activity on or after this date/time (YYYY-MM-DD or ISO-8601).",
    )
    parser.add_argument(
        "--until",
        help="Only include sessions with last activity on or before this date/time (YYYY-MM-DD or ISO-8601).",
    )
    parser.add_argument(
        "--workspace-key",
        help="Only include sessions whose workspace key matches this value (use --workspace-directories to discover keys).",
    )
    return parser.parse_args(argv)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalise_workspace_key(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    safe = [ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in label.strip()]
    normalised = "".join(safe).strip("-_")
    return normalised or None


def workspace_key_from_source(source: Optional[str]) -> Optional[str]:
    if not source:
        return None
    text = str(source).replace("\\", "/")
    lowered = text.lower()
    if "emptywindowchatsessions" in lowered:
        return "empty-window"
    marker = "/workspacestorage/"
    if marker in lowered:
        remainder = lowered.split(marker, 1)[1]
        workspace_id = remainder.split("/", 1)[0]
        if workspace_id:
            return workspace_id
    return None


def collect_candidate_sessions(target: Optional[Path]) -> List[SessionRecord]:
    files = gather_input_files(target)
    sessions: List[SessionRecord] = []
    for file_path in files:
        try:
            data = load_json(file_path)
        except (json.JSONDecodeError, OSError):
            continue
        if is_vscode_chat_session(data):
            workspace_key = normalise_workspace_key(workspace_key_from_source(str(file_path)))
            sessions.append(
                SessionRecord(
                    session=data,
                    source=file_path,
                    workspace_key=workspace_key,
                    origin=str(file_path),
                )
            )
    sessions.sort(
        key=lambda item: item.source.stat().st_mtime if item.source and item.source.exists() else 0,
        reverse=True,
    )
    return sessions


def describe_session(record: SessionRecord) -> str:
    session = record.session
    created = ms_to_iso(session.get("creationDate")) or "unknown"
    last = ms_to_iso(session.get("lastMessageDate")) or created
    session_id = session.get("sessionId") or (record.source.stem if record.source is not None else "unknown-session")
    request_count = len(session.get("requests") or [])
    workspace_hint = f" — workspace {record.workspace_key}" if record.workspace_key else ""
    origin_hint = f" — {record.origin}" if record.origin else ""
    return f"{session_id} — {request_count} turns — created {created}, last activity {last}{workspace_hint}{origin_hint}"


def choose_item(items: Sequence[Any], formatter, noun: str) -> Any:
    if not items:
        raise UserVisibleError(f"No {noun}s are available.")
    if len(items) == 1:
        return items[0]

    print(f"Found {len(items)} {noun}s:")
    for index, item in enumerate(items, start=1):
        print(f"  [{index}] {formatter(item)}")

    while True:
        try:
            choice = input(f"Select {noun} [1-{len(items)}] (default 1): ").strip()
        except EOFError:
            choice = ""
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(1)

        if not choice:
            return items[0]
        if choice.isdigit():
            position = int(choice)
            if 1 <= position <= len(items):
                return items[position - 1]
        print("Please enter a valid number within range.")


def determine_output_path(
    base_output: Optional[str],
    session_id: str,
    exporting_multiple: bool,
    *,
    workspace_key: Optional[str],
    group_by_workspace: bool,
) -> Optional[Path]:
    if not base_output:
        return None
    output_path = Path(base_output).expanduser()
    if group_by_workspace and workspace_key:
        output_path = output_path / workspace_key
    if exporting_multiple or output_path.is_dir():
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path / f"{session_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def export_session(markdown: str, destination: Optional[Path]) -> None:
    if destination is None:
        print(markdown)
    else:
        destination.write_text(markdown, encoding="utf-8")
        print(f"Wrote {destination}")


def reconstruct_requests(log_rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    order: List[str] = []
    requests: Dict[str, Dict[str, Any]] = {}
    for row in log_rows:
        kind = row["kind"] if isinstance(row, sqlite3.Row) else row[1]
        payload_raw = row["raw_json"] if isinstance(row, sqlite3.Row) else row[2]
        try:
            payload = json.loads(payload_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if kind == "request":
            request_id = payload.get("requestId") or payload.get("id") or f"request_{len(order)}"
            request = {
                key: value
                for key, value in payload.items()
                if key not in {"id", "kind", "time", "log_index"}
            }
            requests[request_id] = request
            order.append(request_id)
        elif kind == "response":
            request_id = payload.get("requestId")
            if not request_id or request_id not in requests:
                continue
            request = requests[request_id]
            for field in ("response", "result", "followups"):
                if field in payload and payload[field] is not None:
                    request[field] = payload[field]
            if "isCanceled" in payload and "isCanceled" not in request:
                request["isCanceled"] = payload["isCanceled"]
        else:
            continue
    return [requests[request_id] for request_id in order]


def collect_sessions_from_database(db_path: Path) -> List[SessionRecord]:
    records: List[SessionRecord] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        prompt_rows = conn.execute("SELECT prompt_id, raw_json, source_file FROM prompts")
        for prompt_row in prompt_rows:
            try:
                prompt_payload = json.loads(prompt_row["raw_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            session_meta = prompt_payload.get("session")
            if not isinstance(session_meta, dict):
                continue
            session_copy = dict(session_meta)
            session_id = session_copy.get("sessionId") or prompt_row["prompt_id"]
            session_copy["sessionId"] = session_id

            log_rows = conn.execute(
                "SELECT log_index, kind, raw_json FROM prompt_logs WHERE prompt_id=? ORDER BY log_index",
                (prompt_row["prompt_id"],),
            ).fetchall()
            requests = reconstruct_requests(log_rows)
            if not requests:
                continue
            session_copy["requests"] = requests
            workspace_key = normalise_workspace_key(workspace_key_from_source(prompt_row["source_file"]))
            records.append(
                SessionRecord(
                    session=session_copy,
                    source=None,
                    workspace_key=workspace_key,
                    origin=prompt_row["source_file"],
                )
            )
    records.sort(
        key=lambda record: record.session.get("lastMessageDate")
        or record.session.get("creationDate")
        or 0,
        reverse=True,
    )
    return records


def _parse_iso_date(text: Optional[str]) -> Optional[int]:
    """Parse YYYY-MM-DD or ISO-8601 string to epoch milliseconds (UTC)."""
    if not text:
        return None
    s = text.strip()
    try:
        # Try full ISO first
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        # Try YYYY-MM-DD
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
            dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    target_path = Path(args.path).expanduser() if args.path else None

    db_path: Optional[Path] = None
    if args.database:
        db_path = Path(args.database).expanduser()
        if not db_path.exists():
            raise UserVisibleError(f"Database '{db_path}' was not found.")
        sessions = collect_sessions_from_database(db_path)
    else:
        sessions = collect_candidate_sessions(target_path)

    if not sessions:
        raise UserVisibleError("No Copilot chat session archives were found. Start a chat, then try again.")

    # Apply scoped filters before selection
    since_ms = _parse_iso_date(args.since)
    until_ms = _parse_iso_date(args.until)
    workspace_filter = normalise_workspace_key(args.workspace_key) if args.workspace_key else None

    def last_activity(rec: SessionRecord) -> int:
        sess = rec.session
        val = sess.get("lastMessageDate") or sess.get("creationDate") or 0
        try:
            return int(val)
        except Exception:
            return 0

    filtered: List[SessionRecord] = []
    for rec in sessions:
        ts = last_activity(rec)
        if since_ms is not None and ts < since_ms:
            continue
        if until_ms is not None and ts > until_ms:
            continue
        if workspace_filter and (rec.workspace_key or "") != workspace_filter:
            continue
        filtered.append(rec)
    sessions = filtered or sessions

    def session_matches(record: SessionRecord, session_id: str) -> bool:
        return (record.session.get("sessionId") or (record.source.stem if record.source else None)) == session_id

    if args.session_id:
        selected_sessions = [entry for entry in sessions if session_matches(entry, args.session_id)]
        if not selected_sessions:
            raise UserVisibleError(f"Session '{args.session_id}' was not located.")
    elif args.all:
        selected_sessions = sessions
    else:
        selected_sessions = [
            choose_item(
                sessions,
                lambda item: describe_session(item),
                "chat session",
            )
        ]

    exporting_multiple = len(selected_sessions) > 1 or args.all

    if args.similarity_threshold is not None:
        similarity_threshold_value = max(0.0, min(1.0, args.similarity_threshold))
    else:
        threshold_source = db_path if db_path is not None else CATALOG_DB_PATH
        try:
            similarity_threshold_value = similarity_threshold_module.compute_similarity_threshold(
                threshold_source
            ).threshold
        except Exception:
            similarity_threshold_value = similarity_threshold_module.FALLBACK_THRESHOLD

    for record in selected_sessions:
        session = record.session
        if record.source is not None and not session.get("sessionId") and record.source:
            session["sessionId"] = record.source.stem
        session_id = session.get("sessionId")
        if not session_id and record.source is not None:
            session_id = record.source.stem
            session["sessionId"] = session_id
        if not session_id:
            session_id = "unknown-session"

        # Surface workspace/source hints in the session for the renderer to include
        try:
            if record.workspace_key and not session.get("workspaceKey"):
                session["workspaceKey"] = record.workspace_key
            if record.origin and not session.get("sourceOrigin"):
                session["sourceOrigin"] = record.origin
        except Exception:
            # Best-effort only; continue rendering without these hints if any issues arise
            pass

        destination = determine_output_path(
            args.output,
            session_id,
            exporting_multiple,
            workspace_key=record.workspace_key or ("workspace-unknown" if args.workspace_directories else None),
            group_by_workspace=args.workspace_directories,
        )
        # Determine cross-session index directory: prefer the destination's parent if writing to a file
        cross_dir = destination.parent if destination is not None else None
        markdown = render_session_markdown(
            session,
            include_status=args.include_status,
            include_raw_actions=args.raw_actions,
            cross_session_dir=cross_dir,
            lod_level=args.lod,
            similarity_threshold=similarity_threshold_value,
        )
        export_session(markdown, destination)


if __name__ == "__main__":
    try:
        main()
    except UserVisibleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
