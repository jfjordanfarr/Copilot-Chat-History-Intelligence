"""Validate catalog provenance fields and duplicate protection.

This helper inspects the normalized Copilot chat catalog to confirm
workspace fingerprints, timestamps, and source paths are populated and that
request/session identifiers remain unique after repeated ingest runs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB = Path(".vscode/CopilotChatHistory/copilot_chat_logs.db")


def resolve_db(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def fetch_counts(cursor: sqlite3.Cursor) -> Dict[str, Any]:
    # Aggregate request-level provenance guarantees.
    counts: Dict[str, Any] = {
        "requests": {
            "total": cursor.execute("SELECT COUNT(*) FROM requests").fetchone()[0],
            "distinct_request_id": cursor.execute(
                "SELECT COUNT(DISTINCT request_id) FROM requests"
            ).fetchone()[0],
            "distinct_session_id": cursor.execute(
                "SELECT COUNT(DISTINCT session_id) FROM requests"
            ).fetchone()[0],
            "missing_fingerprint": cursor.execute(
                "SELECT COUNT(*) FROM requests WHERE workspace_fingerprint IS NULL OR workspace_fingerprint = ''"
            ).fetchone()[0],
            "missing_timestamp": cursor.execute(
                "SELECT COUNT(*) FROM requests WHERE timestamp_ms IS NULL"
            ).fetchone()[0],
            "missing_agent": cursor.execute(
                "SELECT COUNT(*) FROM requests WHERE agent_id IS NULL OR agent_id = ''"
            ).fetchone()[0],
        },
        "chat_sessions": {
            "total": cursor.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0],
            "distinct_fingerprint": cursor.execute(
                "SELECT COUNT(DISTINCT workspace_fingerprint) FROM chat_sessions"
            ).fetchone()[0],
            "missing_fingerprint": cursor.execute(
                "SELECT COUNT(*) FROM chat_sessions WHERE workspace_fingerprint IS NULL OR workspace_fingerprint = ''"
            ).fetchone()[0],
            "missing_source_file": cursor.execute(
                "SELECT COUNT(*) FROM chat_sessions WHERE source_file IS NULL OR source_file = ''"
            ).fetchone()[0],
        },
    }

    # Surface duplicate identifiers (if any) to prove idempotence.
    dup_requests = cursor.execute(
        "SELECT request_id, COUNT(*) AS dup_count FROM requests GROUP BY request_id HAVING dup_count > 1"
    ).fetchall()
    dup_sessions = cursor.execute(
        "SELECT session_id, COUNT(*) AS dup_count FROM chat_sessions GROUP BY session_id HAVING dup_count > 1"
    ).fetchall()

    counts["duplicates"] = {
        "request_id": [dict(row) for row in dup_requests],
        "session_id": [dict(row) for row in dup_sessions],
    }
    return counts


def fetch_samples(cursor: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT request_id, session_id, workspace_fingerprint, timestamp_ms, agent_id, is_canceled
        FROM requests
        ORDER BY timestamp_ms
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def run(db_path: Path, sample_limit: int) -> Dict[str, Any]:
    resolved = resolve_db(db_path)
    if not resolved.exists():
        raise FileNotFoundError(f"Catalog not found at {resolved}")

    with sqlite3.connect(resolved) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        counts = fetch_counts(cursor)
        duplicates = counts.pop("duplicates")
        samples = fetch_samples(cursor, sample_limit)
        manifest: Dict[str, Any] = {
            "database": str(resolved),
            "counts": counts,
            "duplicates": duplicates,
            "sample": samples,
        }
        if duplicates["request_id"] or duplicates["session_id"]:
            manifest["duplicates"]["note"] = "Duplicate identifiers detected; inspect ingest safeguards."
        return manifest


def display(report: Dict[str, Any]) -> None:
    print(json.dumps(report, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect catalog provenance fields and duplicate safeguards.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to the normalized Copilot catalog (default: .vscode/CopilotChatHistory/copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of sample request rows to display (default: 5).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run(args.db, args.limit)
    display(report)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
