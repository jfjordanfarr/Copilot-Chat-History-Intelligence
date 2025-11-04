"""Inspect and classify `run_in_terminal` tool invocations from the catalog."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "TerminalCall",
    "CommandStats",
    "load_terminal_calls",
    "classify_terminal_call",
    "aggregate_command_stats",
    "summarise_overall",
]


EXIT_CODE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"exit\s+code\s*[:=]?\s*(-?\d+)", re.IGNORECASE),
    re.compile(r"\(exit\s+(-?\d+)\)", re.IGNORECASE),
    re.compile(r"exited\s+with\s+(?:status|code)\s*(-?\d+)", re.IGNORECASE),
)

FAILURE_KEYWORDS: Tuple[str, ...] = (
    "is not recognized as the name of a cmdlet",
    "commandnotfoundexception",
    "npm err!",
    "fatal:",
    "traceback (most recent call last)",
    "error: unable to",
    "error: cannot",
    "error: command failed",
)

SUCCESS_KEYWORDS: Tuple[str, ...] = (
    "build succeeded",
    "tests passed",
    "0 failed",
    "completed successfully",
    "all files linted successfully",
)


def _repair_invalid_backslashes(text: str) -> str:
    allowed = set('"\\/bfnrtu')
    result: List[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\":
            if index + 1 >= length:
                result.extend(["\\", "\\"])
                index += 1
                continue
            nxt = text[index + 1]
            if nxt in allowed:
                result.extend(["\\", nxt])
            else:
                result.extend(["\\", "\\", nxt])
            index += 2
        else:
            result.append(char)
            index += 1
    return "".join(result)


def _loads_maybe_repair(payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return json.loads(_repair_invalid_backslashes(payload))


def _parse_exit_code(payload: Any, *, _seen: Optional[set[int]] = None) -> Optional[int]:
    if _seen is None:
        _seen = set()
    obj_id = id(payload)
    if obj_id in _seen:
        return None
    _seen.add(obj_id)

    if isinstance(payload, Mapping):
        for key in ("exitCode", "exit_code", "code"):
            if key in payload:
                try:
                    value = payload[key]
                    if value is None:
                        continue
                    return int(value)
                except (TypeError, ValueError):
                    continue
        for value in payload.values():
            code = _parse_exit_code(value, _seen=_seen)
            if code is not None:
                return code
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in payload:
            code = _parse_exit_code(item, _seen=_seen)
            if code is not None:
                return code
    elif isinstance(payload, str):
        for pattern in EXIT_CODE_PATTERNS:
            matched = pattern.search(payload)
            if matched:
                try:
                    return int(matched.group(1))
                except (TypeError, ValueError):
                    continue
    return None


def _extract_result_text(payload: Any) -> str:
    fragments: List[str] = []
    if isinstance(payload, Mapping):
        if "content" in payload and isinstance(payload["content"], list):
            for item in payload["content"]:
                fragments.append(_extract_result_text(item))
        elif "value" in payload and isinstance(payload["value"], str):
            fragments.append(payload["value"])
        elif "text" in payload and isinstance(payload["text"], str):
            fragments.append(payload["text"])
        else:
            for value in payload.values():
                fragments.append(_extract_result_text(value))
    elif isinstance(payload, list):
        for item in payload:
            fragments.append(_extract_result_text(item))
    elif isinstance(payload, str):
        fragments.append(payload)
    elif payload is not None:
        fragments.append(str(payload))
    return "\n".join(fragment for fragment in fragments if fragment)


def _normalise_command(arguments: Mapping[str, Any]) -> str:
    for key in ("command", "original", "toolCommand", "fullCommand"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(arguments.get("argv"), Sequence):
        parts = [str(item) for item in arguments["argv"] if isinstance(item, str)]
        if parts:
            return " ".join(parts)
    if isinstance(arguments.get("args"), Sequence):
        parts = [str(item) for item in arguments["args"] if isinstance(item, str)]
        if parts:
            return " ".join(parts)
    return ""


@dataclass
class TerminalCall:
    """Representation of a single `run_in_terminal` invocation."""

    request_id: str
    call_id: str
    command: str
    workspace_fingerprint: Optional[str]
    timestamp_ms: Optional[int]
    transcript: str
    exit_code: Optional[int]
    error_flag: bool
    result_payload: Optional[Mapping[str, Any]]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "call_id": self.call_id,
            "command": self.command,
            "workspace_fingerprint": self.workspace_fingerprint,
            "timestamp_ms": self.timestamp_ms,
            "transcript": self.transcript,
            "exit_code": self.exit_code,
            "error_flag": self.error_flag,
        }


@dataclass
class CommandStats:
    """Aggregated success metrics for a unique command string."""

    command: str
    total: int
    successes: int
    failures: int
    unknown: int

    @property
    def failure_rate(self) -> Optional[float]:
        considered = self.successes + self.failures
        if considered == 0:
            return None
        return self.failures / considered


def _collect_transcripts(conn: sqlite3.Connection) -> Dict[str, List[Tuple[int, str]]]:
    rows = conn.execute(
        """
        SELECT tool_call_id, fragment_id, plain_text
        FROM tool_output_text
        WHERE tool_name = 'run_in_terminal'
        ORDER BY tool_call_id, fragment_id
        """
    ).fetchall()
    collected: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    for row in rows:
        call_id = row["tool_call_id"]
        text = row["plain_text"]
        if not call_id or not isinstance(call_id, str) or not text:
            continue
        index = row["fragment_id"] if isinstance(row["fragment_id"], int) else 0
        collected[call_id].append((index, text))
    return collected


def _assemble_transcript(fragments: List[Tuple[int, str]]) -> str:
    if not fragments:
        return ""
    parts = [text for _, text in sorted(fragments, key=lambda item: item[0]) if text]
    return "\n".join(parts)


def _iter_terminal_calls(
    rows: Iterable[sqlite3.Row],
    transcripts: Mapping[str, List[Tuple[int, str]]],
) -> Iterable[TerminalCall]:
    for row in rows:
        metadata_raw = row["result_metadata_json"]
        if not isinstance(metadata_raw, str) or "run_in_terminal" not in metadata_raw:
            continue
        try:
            metadata = _loads_maybe_repair(metadata_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, Mapping):
            continue
        rounds = metadata.get("toolCallRounds")
        if not isinstance(rounds, list):
            continue
        results_map: Mapping[str, Any] = {}
        tool_results = metadata.get("toolCallResults")
        if isinstance(tool_results, Mapping):
            results_map = tool_results

        for round_entry in rounds:
            if not isinstance(round_entry, Mapping):
                continue
            tool_calls = round_entry.get("toolCalls")
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    continue
                if call.get("name") != "run_in_terminal":
                    continue
                call_id_raw = call.get("id")
                if not isinstance(call_id_raw, str) or not call_id_raw:
                    continue
                arguments_raw = call.get("arguments")
                arguments: Mapping[str, Any]
                if isinstance(arguments_raw, str):
                    try:
                        arguments = _loads_maybe_repair(arguments_raw)
                    except json.JSONDecodeError:
                        arguments = {}
                elif isinstance(arguments_raw, Mapping):
                    arguments = arguments_raw
                else:
                    arguments = {}
                command = _normalise_command(arguments)
                result_payload = results_map.get(call_id_raw)
                transcript_fragments = transcripts.get(call_id_raw, [])
                transcript_text = _assemble_transcript(transcript_fragments)
                if not transcript_text and result_payload is not None:
                    transcript_text = _extract_result_text(result_payload)

                exit_code = None
                if result_payload is not None:
                    exit_code = _parse_exit_code(result_payload)
                if exit_code is None and transcript_text:
                    exit_code = _parse_exit_code(transcript_text)

                error_flag = bool(call.get("error"))
                if not error_flag and isinstance(result_payload, Mapping):
                    error_flag = bool(result_payload.get("error"))

                yield TerminalCall(
                    request_id=str(row["request_id"]),
                    call_id=call_id_raw,
                    command=command,
                    workspace_fingerprint=(row["workspace_fingerprint"] or None),
                    timestamp_ms=row["timestamp_ms"] if isinstance(row["timestamp_ms"], int) else None,
                    transcript=transcript_text,
                    exit_code=exit_code,
                    error_flag=error_flag,
                    result_payload=result_payload if isinstance(result_payload, Mapping) else None,
                )


def load_terminal_calls(
    db_path: Path,
    *,
    workspace_fingerprints: Optional[Sequence[str]] = None,
    since_ms: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[TerminalCall]:
    """Load terminal tool calls from the normalized catalog."""

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        transcripts = _collect_transcripts(conn)
        query = (
            "SELECT request_id, workspace_fingerprint, timestamp_ms, result_metadata_json "
            "FROM requests WHERE result_metadata_json LIKE '%run_in_terminal%'"
        )
        params: List[Any] = []
        filters: List[str] = []
        if workspace_fingerprints:
            placeholders = ",".join("?" for _ in workspace_fingerprints)
            filters.append(f"workspace_fingerprint IN ({placeholders})")
            params.extend(workspace_fingerprints)
        if since_ms is not None:
            filters.append("timestamp_ms >= ?")
            params.append(int(since_ms))
        if filters:
            query += " AND " + " AND ".join(filters)
        query += " ORDER BY timestamp_ms DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(query, params)
        calls = list(_iter_terminal_calls(rows, transcripts))
    return calls


def classify_terminal_call(call: TerminalCall) -> str:
    """Classify a terminal call as success, failure, or unknown."""

    if call.error_flag:
        return "failure"
    if call.exit_code is not None:
        return "failure" if call.exit_code != 0 else "success"
    transcript_lower = call.transcript.lower()
    for keyword in FAILURE_KEYWORDS:
        if keyword in transcript_lower:
            return "failure"
    for keyword in SUCCESS_KEYWORDS:
        if keyword in transcript_lower:
            return "success"
    return "unknown"


def aggregate_command_stats(calls: Iterable[TerminalCall]) -> List[CommandStats]:
    """Aggregate classification counts per normalized command string."""

    buckets: Dict[str, Counter] = defaultdict(Counter)
    for call in calls:
        command = call.command or ""
        status = classify_terminal_call(call)
        buckets[command][status] += 1
        buckets[command]["total"] += 1

    stats: List[CommandStats] = []
    for command, counter in buckets.items():
        stats.append(
            CommandStats(
                command=command,
                total=counter["total"],
                successes=counter.get("success", 0),
                failures=counter.get("failure", 0),
                unknown=counter.get("unknown", 0),
            )
        )
    stats.sort(key=lambda item: (item.failure_rate or -1.0, item.failures, item.command), reverse=True)
    return stats


def summarise_overall(calls: Iterable[TerminalCall]) -> Mapping[str, Any]:
    """Provide overall counts across all terminal calls."""

    total = 0
    successes = 0
    failures = 0
    unknown = 0
    seen = Counter()
    for call in calls:
        total += 1
        status = classify_terminal_call(call)
        seen[status] += 1
        if status == "success":
            successes += 1
        elif status == "failure":
            failures += 1
        else:
            unknown += 1
    considered = successes + failures
    failure_rate = failures / considered if considered else None
    return {
        "total_calls": total,
        "successes": successes,
        "failures": failures,
        "unknown": unknown,
        "failure_rate": failure_rate,
        "status_breakdown": dict(seen),
    }
