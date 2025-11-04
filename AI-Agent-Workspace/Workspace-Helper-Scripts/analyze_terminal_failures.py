"""Summarise terminal command outcomes recorded in the Copilot catalog."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from analysis import terminal_failures, workspace_filters

CATALOG_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"


def safe_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def classify_calls(
    db_path: Path,
    *,
    workspace_fingerprints: Optional[Sequence[str]],
) -> tuple[List[terminal_failures.TerminalCall], List[terminal_failures.CommandStats]]:
    calls = terminal_failures.load_terminal_calls(db_path, workspace_fingerprints=workspace_fingerprints)
    stats = terminal_failures.aggregate_command_stats(calls)
    return calls, stats


def format_table(stats: Iterable[terminal_failures.CommandStats], *, limit: int) -> str:
    header = f"{'Command':<52}  {'Failures':>8}  {'Successes':>9}  {'Unknown':>7}  {'Failure%':>9}  {'Total':>7}"
    lines = [header, "-" * len(header)]
    for index, item in enumerate(stats, start=1):
        if index > limit:
            break
        command = item.command.replace("\n", " ")
        if len(command) > 52:
            command = command[:49] + "..."
        failure_rate = item.failure_rate * 100 if item.failure_rate is not None else None
        rate_text = f"{failure_rate:>8.1f}%" if failure_rate is not None else "   n/a  "
        lines.append(
            f"{command:<52}  {item.failures:>8}  {item.successes:>9}  {item.unknown:>7}  {rate_text}  {item.total:>7}"
        )
    return "\n".join(lines)


def build_payload(
    *,
    db_path: Path,
    summary: Mapping[str, object],
    stats: Sequence[terminal_failures.CommandStats],
    calls: Sequence[terminal_failures.TerminalCall],
    workspace_filters: Optional[Sequence[str]],
    limit: int,
    sample_limit: int,
) -> Mapping[str, object]:
    grouped_calls: Dict[str, List[terminal_failures.TerminalCall]] = defaultdict(list)
    for call in calls:
        grouped_calls[call.command].append(call)

    commands_payload: List[Mapping[str, object]] = []
    for item in stats[:limit]:
        command_entry = {
            "command": item.command,
            "total": item.total,
            "successes": item.successes,
            "failures": item.failures,
            "unknown": item.unknown,
            "failure_rate": item.failure_rate,
        }
        if sample_limit > 0:
            samples: List[Mapping[str, object]] = []
            for call in grouped_calls.get(item.command, [])[:sample_limit]:
                samples.append(
                    {
                        "request_id": call.request_id,
                        "call_id": call.call_id,
                        "exit_code": call.exit_code,
                        "timestamp_ms": call.timestamp_ms,
                        "workspace_fingerprint": call.workspace_fingerprint,
                        "transcript": call.transcript,
                    }
                )
            command_entry["samples"] = samples
        commands_payload.append(command_entry)

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalog_db": str(db_path.resolve()),
        "workspace_filters": list(workspace_filters) if workspace_filters else None,
        "summary": summary,
        "commands": commands_payload,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect run_in_terminal outcomes, highlighting the most failure-prone commands.",
    )
    parser.add_argument("--db", type=Path, default=CATALOG_PATH, help="Path to the catalog database.")
    parser.add_argument("--limit", type=int, default=10, help="Number of commands to display (default: 10).")
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=0,
        help="Number of terminal call transcripts to include per command in JSON output (default: 0).",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON file for structured output.")
    parser.add_argument(
        "--workspace",
        action="append",
        help="Restrict telemetry to specific workspaces (fingerprint or path). Option may repeat.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace root used to derive the default fingerprint filter (default: current directory).",
    )
    parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Include telemetry from all workspaces without filtering.",
    )
    args = parser.parse_args(argv)

    db_path = args.db
    if not db_path.exists():
        parser.error(f"Catalog not found at {db_path}")

    try:
        filters = workspace_filters.resolve_workspace_filters(
            selectors=args.workspace,
            all_workspaces=args.all_workspaces,
            workspace_root=args.workspace_root,
            cwd=Path.cwd(),
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        calls, stats_list = classify_calls(db_path, workspace_fingerprints=filters)
    except sqlite3.OperationalError as exc:
        parser.error(f"Failed to query catalog: {exc}")
    except sqlite3.DatabaseError as exc:
        parser.error(f"Catalog error: {exc}")

    stats_sorted = list(stats_list)
    stats_sorted.sort(key=lambda item: (item.failure_rate or -1.0, item.failures, item.command), reverse=True)

    summary = terminal_failures.summarise_overall(calls)
    total_calls = summary.get("total_calls", 0)
    if not total_calls:
        print(safe_text("No run_in_terminal telemetry found for the selected scope."))
        if args.output:
            payload = build_payload(
                db_path=db_path,
                summary=summary,
                stats=[],
                calls=[],
                workspace_filters=filters,
                limit=args.limit,
                sample_limit=args.sample_limit,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0

    failure_rate_value = summary.get("failure_rate")
    if isinstance(failure_rate_value, (int, float)):
        failure_rate_text = f"{failure_rate_value * 100:.1f}%"
    else:
        failure_rate_text = "n/a"

    print(
        safe_text(
            "Terminal summary: "
            f"total={summary['total_calls']} successes={summary['successes']} "
            f"failures={summary['failures']} unknown={summary['unknown']} "
            f"failure_rate={failure_rate_text}"
        )
    )
    print()
    print(safe_text(format_table(stats_sorted, limit=max(args.limit, 0))))

    if args.output:
        payload = build_payload(
            db_path=db_path,
            summary=summary,
            stats=stats_sorted,
            calls=calls,
            workspace_filters=filters,
            limit=max(args.limit, 0),
            sample_limit=max(args.sample_limit, 0),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print()
        print(safe_text(f"Wrote report to {args.output}"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
