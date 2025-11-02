"""Inspect repeat-failure telemetry captured by the catalog.

This helper script turns the `metrics_repeat_failures` table into a lightweight
report that can be archived alongside SC-004 evidence. It supports three modes:

* printing a ranked table to stdout;
* saving the table (plus run metadata) to a JSON file that can be reused as a
    baseline for future comparisons; and
* emitting a security manifest containing hashes and redaction counts so audits
    can prove no sensitive payloads leaked outside the workspace boundary.

Usage examples (PowerShell):

```powershell
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --top 10 --output AI-Agent-Workspace/_temp/repeat_failures.json
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --baseline AI-Agent-Workspace/_temp/repeat_failures.json
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --workspace ..\OtherWorkspace --output AI-Agent-Workspace/_temp/repeat_failures.json
```

Usage examples (bash/zsh):

```bash
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --db .vscode/CopilotChatHistory/copilot_chat_logs.db
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --baseline AI-Agent-Workspace/_temp/repeat_failures.json
python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --all-workspaces --output AI-Agent-Workspace/_temp/repeat_failures.json
```
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, asdict
import hashlib
import sys
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass
class BaselineData:
    entries: List[Mapping[str, object]]
    generated_at: Optional[str]

CATALOG_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"
AUDIT_PATH = Path("AI-Agent-Workspace") / "_temp" / "ingest_audit.json"


@dataclass
class FailureRow:
    workspace_fingerprint: str
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
            workspace_fingerprint=str(row.get("workspace_fingerprint") or ""),
            command_text=str(row.get("command_text") or ""),
            exit_code=int(row.get("exit_code") or 0),
            occurrence_count=int(row.get("occurrence_count") or 0),
            last_seen_ms=last_seen_ms if isinstance(last_seen_ms, int) else None,
            last_seen_iso=iso,
            sample_snippet=(row.get("sample_snippet") or None) if isinstance(row.get("sample_snippet"), str) else None,
            request_id=(row.get("request_id") or None) if isinstance(row.get("request_id"), str) else None,
        )


def fetch_failures(db_path: Path, *, workspace_filters: Optional[Sequence[str]] = None) -> List[FailureRow]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        base_query = (
            "SELECT workspace_fingerprint, command_text, exit_code, occurrence_count, "
            "last_seen_ms, sample_snippet, request_id FROM metrics_repeat_failures"
        )
        params: Tuple[object, ...] = ()
        if workspace_filters:
            placeholders = ",".join("?" for _ in workspace_filters)
            base_query += f" WHERE workspace_fingerprint IN ({placeholders})"
            params = tuple(workspace_filters)
        base_query += " ORDER BY occurrence_count DESC, last_seen_ms DESC, command_text ASC"
        rows = conn.execute(base_query, params).fetchall()
    return [FailureRow.from_row(dict(row)) for row in rows]


def load_audit(path: Path) -> Optional[Mapping[str, object]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_baseline(path: Optional[Path]) -> Optional[BaselineData]:
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
            generated_at = payload.get("generated_at")
            if not isinstance(generated_at, str):
                generated_at = None
            return BaselineData(entries=entries, generated_at=generated_at)
    if isinstance(payload, list):
        return BaselineData(entries=payload, generated_at=None)
    return None


def render_table(rows: Iterable[FailureRow], *, limit: int, show_workspace: bool) -> str:
    if show_workspace:
        header = f"{'#':>2}  {'Workspace':<16}  {'Command':<52}  {'Exit':>4}  {'Count':>5}  {'Last Seen':<20}"
    else:
        header = f"{'#':>2}  {'Command':<60}  {'Exit':>4}  {'Count':>5}  {'Last Seen':<20}"
    lines = [header, "-" * len(header)]
    for index, row in enumerate(rows, start=1):
        if index > limit:
            break
        command = row.command_text.replace("\n", " ")
        if show_workspace:
            if len(command) > 52:
                command = command[:49] + "..."
        elif len(command) > 60:
            command = command[:57] + "..."
        last_seen = row.last_seen_iso or ""  # already ISO
        if show_workspace:
            lines.append(
                f"{index:>2}  {row.workspace_fingerprint:<16}  {command:<52}  {row.exit_code:>4}  "
                f"{row.occurrence_count:>5}  {last_seen:<20}"
            )
        else:
            lines.append(
                f"{index:>2}  {command:<60}  {row.exit_code:>4}  {row.occurrence_count:>5}  {last_seen:<20}"
            )
    return "\n".join(lines)


def compute_delta(current: List[FailureRow], baseline: Optional[BaselineData]) -> List[Mapping[str, object]]:
    if not baseline:
        return []

    base_index: dict[Tuple[Optional[str], str, int], Mapping[str, object]] = {}
    for item in baseline.entries:
        if not isinstance(item, Mapping):
            continue
        command = str(item.get("command_text") or "")
        exit_code_raw = item.get("exit_code")
        try:
            exit_code = int(exit_code_raw if exit_code_raw is not None else 0)
        except (TypeError, ValueError):
            exit_code = 0
        fingerprint = item.get("workspace_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            key_fp: Optional[str] = fingerprint
        else:
            key_fp = None
        base_index[(key_fp, command, exit_code)] = item

    delta: List[Mapping[str, object]] = []
    current_index = {
        (row.workspace_fingerprint or None, row.command_text, row.exit_code): row for row in current
    }

    for row in current:
        key = (row.workspace_fingerprint or None, row.command_text, row.exit_code)
        baseline_item = base_index.get(key)
        if baseline_item is None:
            delta.append(
                {
                    "workspace_fingerprint": row.workspace_fingerprint or None,
                    "command_text": row.command_text,
                    "exit_code": row.exit_code,
                    "delta": row.occurrence_count,
                    "current_occurrence_count": row.occurrence_count,
                    "previous_occurrence_count": 0,
                    "status": "new",
                }
            )
            continue

        previous_raw = baseline_item.get("occurrence_count")
        try:
            previous = int(previous_raw if previous_raw is not None else 0)
        except (TypeError, ValueError):
            previous = 0

        if previous != row.occurrence_count:
            status = "regressed" if row.occurrence_count > previous else "improved"
            delta.append(
                {
                    "command_text": row.command_text,
                    "exit_code": row.exit_code,
                    "delta": row.occurrence_count - previous,
                    "current_occurrence_count": row.occurrence_count,
                    "previous_occurrence_count": previous,
                    "status": status,
                }
            )

    for key, baseline_item in base_index.items():
        if key in current_index:
            continue
        fingerprint, command, exit_code = key
        previous_raw = baseline_item.get("occurrence_count")
        try:
            previous = int(previous_raw if previous_raw is not None else 0)
        except (TypeError, ValueError):
            previous = 0
        delta.append(
            {
                    "workspace_fingerprint": fingerprint,
                "command_text": command,
                "exit_code": exit_code,
                "delta": -previous,
                "current_occurrence_count": 0,
                "previous_occurrence_count": previous,
                "status": "resolved",
            }
        )

    return delta


def summarise_rows(rows: List[FailureRow]) -> Mapping[str, object]:
    total_occurrences = sum(row.occurrence_count for row in rows)
    unique_failures = len({(row.command_text, row.exit_code) for row in rows})
    exit_counts = Counter()
    for row in rows:
        exit_counts[row.exit_code] += row.occurrence_count
    top_exit_codes = [
        {"exit_code": code, "occurrence_count": count}
        for code, count in exit_counts.most_common(3)
    ]
    window = None
    timestamps = [row.last_seen_iso for row in rows if row.last_seen_iso]
    if timestamps:
        window = {"earliest": min(timestamps), "latest": max(timestamps)}
    return {
        "total_occurrences": total_occurrences,
        "unique_failures": unique_failures,
        "top_exit_codes": top_exit_codes,
        "window": window,
        "workspace_fingerprints": sorted({row.workspace_fingerprint for row in rows}) if rows else [],
    }


def summarise_delta_entries(entries: List[Mapping[str, object]]) -> Mapping[str, int]:
    summary = {"new": 0, "regressed": 0, "improved": 0, "resolved": 0}
    for entry in entries:
        status = entry.get("status")
        if isinstance(status, str) and status in summary:
            summary[status] += 1
    return summary


def summarise_audit(audit: Optional[Mapping[str, object]]) -> Optional[Mapping[str, object]]:
    if not audit:
        return None
    requests = audit.get("requests_ingested")
    redactions = audit.get("secrets_redacted")
    if requests is None and redactions is None:
        return None
    return {"requests_ingested": requests, "secrets_redacted": redactions}


def save_report(
    path: Path,
    *,
    rows: List[FailureRow],
    db_path: Path,
    audit: Optional[Mapping[str, object]],
    baseline: Optional[BaselineData],
    deltas: List[Mapping[str, object]],
    summary: Mapping[str, object],
    delta_summary: Mapping[str, int],
    baseline_path: Optional[Path],
    workspace_filters: Optional[Sequence[str]],
) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalog_db": str(db_path.resolve()),
        "summary": summary,
        "audit": summarise_audit(audit),
        "workspace_filters": list(workspace_filters) if workspace_filters else None,
        "baseline": {
            "path": str(baseline_path) if baseline_path else None,
            "generated_at": baseline.generated_at if baseline else None,
            "delta_overview": delta_summary if deltas else None,
            "deltas": deltas if deltas else None,
        },
        "entries": [asdict(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_security_manifest(
    path: Path,
    *,
    rows: List[FailureRow],
    db_path: Path,
    summary: Mapping[str, object],
    delta_summary: Mapping[str, int],
    audit: Optional[Mapping[str, object]],
    report_path: Optional[Path],
    baseline_path: Optional[Path],
    workspace_filters: Optional[Sequence[str]],
) -> None:
    base_payload = {
        "entries": [asdict(row) for row in rows],
        "summary": summary,
        "delta_overview": delta_summary,
        "audit": summarise_audit(audit),
    }
    digest = hashlib.sha256(json.dumps(base_payload, sort_keys=True).encode("utf-8")).hexdigest()

    manifest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalog_db": str(db_path.resolve()),
        "report_path": str(report_path) if report_path else None,
        "baseline_path": str(baseline_path) if baseline_path else None,
        "digest_sha256": digest,
        "summary": summary,
        "delta_overview": delta_summary,
        "audit": summarise_audit(audit),
        "workspace_filters": list(workspace_filters) if workspace_filters else None,
    }

    if report_path and report_path.exists():
        manifest["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    if baseline_path and baseline_path.exists():
        manifest["baseline_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def safe_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def compute_workspace_fingerprint(workspace_root: Path) -> str:
    resolved = workspace_root.expanduser().resolve()
    return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16]


def normalize_workspace_selector(value: str, *, base_dir: Path) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Workspace selector cannot be empty.")

    path_like = Path(candidate)
    # Treat strings containing path separators or pointing to existing directories as paths.
    if path_like.exists() or any(sep in candidate for sep in ("/", "\\")):
        target = path_like if path_like.is_absolute() else (base_dir / path_like)
        return compute_workspace_fingerprint(target)

    lowered = candidate.lower()
    if len(lowered) == 16 and all(ch in "0123456789abcdef" for ch in lowered):
        return lowered

    raise ValueError(
        f"Unrecognised workspace selector '{value}'. Provide a 16-character fingerprint or a workspace path."
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarise repeat-failure metrics from the Copilot catalog.")
    parser.add_argument("--db", type=Path, default=CATALOG_PATH, help="Path to the normalized catalog database.")
    parser.add_argument("--top", type=int, default=15, help="Number of rows to display in the console table.")
    parser.add_argument("--output", type=Path, help="Optional JSON file to write the full table.")
    parser.add_argument("--baseline", type=Path, help="Optional previous JSON report to compute deltas against.")
    parser.add_argument(
        "--security-report",
        type=Path,
        help="Optional path for a security manifest containing hashes and audit metadata.",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        help="Restrict telemetry to specific workspaces (fingerprint or path). Option may repeat.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace root used to derive the default fingerprint filter (default: current working directory).",
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

    workspace_filters: Optional[List[str]]
    base_workspace = args.workspace_root.expanduser().resolve() if args.workspace_root else Path.cwd().resolve()
    if args.all_workspaces:
        workspace_filters = None
    else:
        if args.workspace:
            filters: List[str] = []
            for selector in args.workspace:
                try:
                    filters.append(normalize_workspace_selector(selector, base_dir=base_workspace))
                except ValueError as exc:
                    parser.error(str(exc))
            workspace_filters = sorted(set(filters)) or None
        else:
            workspace_filters = [compute_workspace_fingerprint(base_workspace)]

    rows = fetch_failures(db_path, workspace_filters=workspace_filters)
    audit = load_audit(AUDIT_PATH)
    baseline = load_baseline(args.baseline)
    deltas = compute_delta(rows, baseline)
    summary = summarise_rows(rows)
    delta_summary = summarise_delta_entries(deltas)

    unique_fingerprints = {row.workspace_fingerprint for row in rows if row.workspace_fingerprint}
    show_workspace = len(unique_fingerprints) > 1 or (workspace_filters is None and rows)
    print(safe_text(render_table(rows, limit=max(args.top, 0), show_workspace=show_workspace)))
    if audit:
        redactions = audit.get("secrets_redacted")
        requests = audit.get("requests_ingested")
        print()
        print(safe_text(f"Audit: requests_ingested={requests}, secrets_redacted={redactions}"))
    print()
    window = summary.get("window")
    window_text = ""
    if isinstance(window, Mapping):
        earliest = window.get("earliest")
        latest = window.get("latest")
        if earliest or latest:
            window_text = f" window=({earliest} -> {latest})"
    print(
        safe_text(
            "Summary: "
            f"unique_failures={summary['unique_failures']} "
            f"total_occurrences={summary['total_occurrences']}" + window_text
        )
    )
    top_exit_codes = summary.get("top_exit_codes")
    if isinstance(top_exit_codes, list) and top_exit_codes:
        formatted = ", ".join(
            f"exit {item['exit_code']}: {item['occurrence_count']}"
            for item in top_exit_codes
            if isinstance(item, Mapping)
        )
        if formatted:
            print(safe_text(f"Top exit codes: {formatted}"))
    if deltas:
        print()
        print(safe_text("Changes vs baseline:"))
        for entry in deltas:
            cmd = entry["command_text"]
            delta = entry["delta"]
            exit_code = entry["exit_code"]
            status = entry.get("status")
            status_suffix = f" [{status}]" if isinstance(status, str) else ""
            line = f"  {cmd} (exit {exit_code}): {'+' if delta > 0 else ''}{delta}{status_suffix}"
            print(safe_text(line))
        print(
            safe_text(
                "  Summary: "
                f"new={delta_summary['new']} "
                f"regressed={delta_summary['regressed']} "
                f"improved={delta_summary['improved']} "
                f"resolved={delta_summary['resolved']}"
            )
        )

    if args.output:
        save_report(
            args.output,
            rows=rows,
            db_path=db_path,
            audit=audit,
            baseline=baseline,
            deltas=deltas,
            summary=summary,
            delta_summary=delta_summary,
            baseline_path=args.baseline,
            workspace_filters=workspace_filters,
        )
        print()
        print(safe_text(f"Wrote report to {args.output}"))

    if args.security_report:
        write_security_manifest(
            args.security_report,
            rows=rows,
            db_path=db_path,
            summary=summary,
            delta_summary=delta_summary,
            audit=audit,
            report_path=args.output,
            baseline_path=args.baseline,
            workspace_filters=workspace_filters,
        )
        print()
        print(safe_text(f"Wrote security manifest to {args.security_report}"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
