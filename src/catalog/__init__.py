"""Catalog helper queries used by recall and export tooling."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

ConnectionLike = Union[str, Path, sqlite3.Connection]


def _ensure_connection(database: ConnectionLike) -> Tuple[sqlite3.Connection, bool]:
    if isinstance(database, sqlite3.Connection):
        return database, False
    conn = sqlite3.connect(str(database))
    conn.row_factory = sqlite3.Row
    return conn, True


def fetch_session_documents(
    database: ConnectionLike,
    *,
    workspace_fingerprint: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return request-level documents enriched with responses for recall pipelines."""

    conn, owns_connection = _ensure_connection(database)
    try:
        params: List[Any] = []
        where_clause = ""
        if workspace_fingerprint:
            where_clause = "WHERE r.workspace_fingerprint = ?"
            params.append(workspace_fingerprint)

        limit_clause = ""
        if isinstance(limit, int) and limit > 0:
            limit_clause = " LIMIT ?"
            params.append(limit)

        rows = conn.execute(
            f"""
            SELECT
                r.request_id,
                r.session_id,
                r.workspace_fingerprint,
                r.timestamp_ms,
                r.prompt_text,
                s.initial_location,
                s.last_message_date_ms,
                GROUP_CONCAT(resp.value, '\n\n') AS response_text
            FROM requests r
            JOIN chat_sessions s ON s.session_id = r.session_id
            LEFT JOIN responses resp ON resp.request_id = r.request_id
            {where_clause}
            GROUP BY r.request_id
            ORDER BY
                CASE WHEN r.timestamp_ms IS NULL THEN 1 ELSE 0 END,
                r.timestamp_ms,
                r.request_id
            {limit_clause}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if owns_connection:
            conn.close()


def fetch_tool_results(
    database: ConnectionLike,
    *,
    request_ids: Optional[Iterable[str]] = None,
    workspace_fingerprint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return tool output payloads joined with request metadata."""

    conn, owns_connection = _ensure_connection(database)
    try:
        clauses: List[str] = []
        params: List[Any] = []

        if request_ids:
            request_list = list(request_ids)
            placeholders = ",".join(["?"] * len(request_list))
            clauses.append(f"r.request_id IN ({placeholders})")
            params.extend(request_list)

        if workspace_fingerprint:
            clauses.append("r.workspace_fingerprint = ?")
            params.append(workspace_fingerprint)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        rows = conn.execute(
            f"""
            SELECT
                r.request_id,
                r.session_id,
                r.workspace_fingerprint,
                r.timestamp_ms,
                o.output_index,
                o.tool_kind,
                o.payload_json
            FROM tool_outputs o
            JOIN requests r ON r.request_id = o.request_id
            {where_clause}
            ORDER BY r.timestamp_ms, o.output_index
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if owns_connection:
            conn.close()


def fetch_tool_output_text(
    database: ConnectionLike,
    *,
    request_ids: Optional[Iterable[str]] = None,
    workspace_fingerprint: Optional[str] = None,
    source_kinds: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return flattened tool output fragments with request metadata."""

    conn, owns_connection = _ensure_connection(database)
    try:
        clauses: List[str] = []
        params: List[Any] = []

        if request_ids:
            request_list = list(request_ids)
            placeholders = ",".join(["?"] * len(request_list))
            clauses.append(f"r.request_id IN ({placeholders})")
            params.extend(request_list)

        if workspace_fingerprint:
            clauses.append("r.workspace_fingerprint = ?")
            params.append(workspace_fingerprint)

        if source_kinds:
            kinds_list = [kind for kind in source_kinds if isinstance(kind, str)]
            if kinds_list:
                placeholders = ",".join(["?"] * len(kinds_list))
                clauses.append(f"t.source_kind IN ({placeholders})")
                params.extend(kinds_list)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        limit_clause = ""
        if isinstance(limit, int) and limit > 0:
            limit_clause = " LIMIT ?"
            params.append(limit)

        rows = conn.execute(
            f"""
            SELECT
                t.fragment_id,
                r.request_id,
                r.session_id,
                r.workspace_fingerprint,
                r.timestamp_ms,
                t.source_kind,
                t.output_index,
                t.tool_call_id,
                t.tool_name,
                t.round_index,
                t.call_index,
                t.arguments_json,
                t.text_hash,
                t.text_length,
                t.plain_text
            FROM tool_output_text t
            JOIN requests r ON r.request_id = t.request_id
            {where_clause}
            ORDER BY r.timestamp_ms, t.fragment_id
            {limit_clause}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if owns_connection:
            conn.close()


__all__ = [
    "fetch_session_documents",
    "fetch_tool_results",
    "fetch_tool_output_text",
]
