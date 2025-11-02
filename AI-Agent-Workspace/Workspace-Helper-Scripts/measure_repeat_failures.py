"""Inspect repeat-failure telemetry captured by the catalog.

This helper script turns the `metrics_repeat_failures` table into a lightweight
report that can be archived alongside SC-004 evidence. It supports two modes:

* printing a ranked table to stdout; and
* saving the table (plus a timestamp) to a JSON file that can be used as a
  baseline for future comparisons.

Usage examples (PowerShell):

```powershell
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --top 10 --output AI-Agent-Workspace/_temp/repeat_failures.json
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --baseline AI-Agent-Workspace/_temp/repeat_failures.json
```

Usage examples (bash/zsh):

```bash
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --db .vscode/CopilotChatHistory/copilot_chat_logs.db
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --baseline AI-Agent-Workspace/_temp/repeat_failures.json
```
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

CATALOG_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"
AUDIT_PATH = Path("AI-Agent-Workspace") / "_temp" / "ingest_audit.json"


@dataclass
class FailureRow:
    command_text: str
    exit_code: int
    occurrence_count: int
    last_seen_ms: Optional[int]
    last_seen_iso: Optional[str]
    sample_snippet: Optional[str]
    request_id: Optional[str]

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "FailureRow":
        last_seen_ms = row.get("last_seen_ms")
        iso: Optional[str] = None
        if isinstance(last_seen_ms, int):
            iso = dt.datetime.fromtimestamp(last_seen_ms / 1000, tz=dt.timezone.utc).isoformat()
        return cls(
            command_text=str(row.get("command_text") or ""),
            exit_code=int(row.get("exit_code") or 0),
            occurrence_count=int(row.get("occurrence_count") or 0),
            last_seen_ms=last_seen_ms if isinstance(last_seen_ms, int) else None,
            last_seen_iso=iso,
            sample_snippet=(row.get("sample_snippet") or None) if isinstance(row.get("sample_snippet"), str) else None,
            request_id=(row.get("request_id") or None) if isinstance(row.get("request_id"), str) else None,
        )


def fetch_failures(db_path: Path) -> List[FailureRow]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT command_text, exit_code, occurrence_count, last_seen_ms, sample_snippet, request_id
            FROM metrics_repeat_failures
            ORDER BY occurrence_count DESC, last_seen_ms DESC, command_text ASC
            """
        ).fetchall()
    return [FailureRow.from_row(dict(row)) for row in rows]


def load_audit(path: Path) -> Optional[Mapping[str, object]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_baseline(path: Optional[Path]) -> Optional[List[Mapping[str, object]]]:
    if not path:
        return None
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, Mapping) and "entries" in payload:
        entries = payload.get("entries")
        if isinstance(entries, list):
            return entries  # type: ignore[return-value]
    if isinstance(payload, list):
        return payload  # legacy shape
    return None


def render_table(rows: Iterable[FailureRow], *, limit: int) -> str:
    header = f"{'#':>2}  {'Command':<60}  {'Exit':>4}  {'Count':>5}  {'Last Seen':<20}"
    lines = [header, "-" * len(header)]
    for index, row in enumerate(rows, start=1):
        if index > limit:
            break
        command = row.command_text.replace("\n", " ")
        if len(command) > 60:
            command = command[:57] + "..."
        last_seen = row.last_seen_iso or ""  # already ISO
        lines.append(f"{index:>2}  {command:<60}  {row.exit_code:>4}  {row.occurrence_count:>5}  {last_seen:<20}")
    return "\n".join(lines)


def compute_delta(current: List[FailureRow], baseline: Optional[List[Mapping[str, object]]]) -> List[Mapping[str, object]]:
    if not baseline:
        return []
    base_index = {
        (str(item.get("command_text")), int(item.get("exit_code") or 0)): int(item.get("occurrence_count") or 0)
        for item in baseline
        if isinstance(item, Mapping)
    }
    delta: List[Mapping[str, object]] = []
    for row in current:
        key = (row.command_text, row.exit_code)
        previous = base_index.get(key)
        if previous is None:
            delta.append({"command_text": row.command_text, "exit_code": row.exit_code, "delta": row.occurrence_count})
        elif previous != row.occurrence_count:
            delta.append(
                {
                    "command_text": row.command_text,
                    "exit_code": row.exit_code,
                    "delta": row.occurrence_count - previous,
                }
            )
    return delta


def save_report(path: Path, rows: List[FailureRow]) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "entries": [asdict(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise repeat-failure metrics from the Copilot catalog.")
    parser.add_argument("--db", type=Path, default=CATALOG_PATH, help="Path to the normalized catalog database.")
    parser.add_argument("--top", type=int, default=15, help="Number of rows to display in the console table.")
    parser.add_argument("--output", type=Path, help="Optional JSON file to write the full table.")
    parser.add_argument("--baseline", type=Path, help="Optional previous JSON report to compute deltas against.")
    args = parser.parse_args(argv)

    db_path = args.db
    if not db_path.exists():
        parser.error(f"Catalog not found at {db_path}")

    rows = fetch_failures(db_path)
    audit = load_audit(AUDIT_PATH)
    baseline = load_baseline(args.baseline)
    deltas = compute_delta(rows, baseline)

    print(render_table(rows, limit=max(args.top, 0)))
    if audit:
        redactions = audit.get("secrets_redacted")
        requests = audit.get("requests_ingested")
        print()
        print(f"Audit: requests_ingested={requests}, secrets_redacted={redactions}")
    if deltas:
        print()
        print("Changes vs baseline:")
        for entry in deltas:
            cmd = entry["command_text"]
            delta = entry["delta"]
            exit_code = entry["exit_code"]
            print(f"  {cmd} (exit {exit_code}): {'+' if delta > 0 else ''}{delta}")

    if args.output:
        save_report(args.output, rows)
        print()
        print(f"Wrote report to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
