from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

ActionHeader = re.compile(r"^#### Actions\s*$")
SessionHeader = re.compile(r"^# Copilot Chat Session — (?P<id>[a-f0-9\-]+)")
ActionLine = re.compile(r"^\*\*(?P<title>[^*]+)\*\*\s+—\s+(?P<summary>.*)$")
StatusLine = re.compile(r"^>\s*_Status_:\s*(?P<status>.*)$", re.IGNORECASE)

SUPPRESSED_TITLES = {"Raw thinking", "Raw mcpServersStarting", "Raw prepareToolInvocation", "Raw toolInvocationSerialized"}


def summarize_export(path: Path) -> Tuple[str, Dict[str, int]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    session_id = "unknown"
    metrics: Dict[str, int] = {
        "turns": 0,
        "actionsBlocks": 0,
        "Terminal": 0,
        "TerminalFailures": 0,
        "Apply Patch": 0,
        "Read": 0,
        "Search": 0,
        "Inline": 0,
        "StatusLines": 0,
        "StatusCanceled": 0,
    }

    lines = text.splitlines()
    for line in lines:
        m = SessionHeader.match(line)
        if m:
            session_id = m.group("id")
            break

    metrics["turns"] = sum(1 for l in lines if l.startswith("## Turn "))
    metrics["actionsBlocks"] = sum(1 for l in lines if ActionHeader.match(l))

    for line in lines:
        m = ActionLine.match(line)
        if m:
            title = m.group("title").strip()
            if title in SUPPRESSED_TITLES:
                continue
            if title == "Terminal":
                metrics["Terminal"] += 1
                if "→ exit" in m.group("summary"):
                    metrics["TerminalFailures"] += 1
            elif title == "Apply Patch":
                metrics["Apply Patch"] += 1
            elif title == "Read":
                metrics["Read"] += 1
            elif title == "Search":
                metrics["Search"] += 1
            elif title.lower().startswith("inline"):
                metrics["Inline"] += 1
        else:
            s = StatusLine.match(line)
            if s:
                metrics["StatusLines"] += 1
                status_text = s.group("status").lower()
                if "cancel" in status_text:
                    metrics["StatusCanceled"] += 1

    return session_id, metrics


def render_compare_md(a_id: str, a_metrics: Dict[str, int], b_id: str, b_metrics: Dict[str, int]) -> str:
    lines = [
        f"# Export Comparison — {a_id} vs {b_id}",
        "",
        "## Summary",
        "",
        "- Key counts per session (approximate, from Actions headers and lines)",
        "",
        "| Metric | " + a_id + " | " + b_id + " |",
        "|---|---:|---:|",
    ]
    keys = [
        ("turns", "Turns"),
        ("actionsBlocks", "Action sections"),
        ("Terminal", "Terminal calls"),
        ("TerminalFailures", "Terminal failures (exit≠0)"),
        ("Apply Patch", "Apply Patch"),
        ("Read", "Read"),
        ("Search", "Search"),
        ("Inline", "Inline refs"),
        ("StatusLines", "Status lines"),
        ("StatusCanceled", "Status: Canceled"),
    ]
    for key, label in keys:
        lines.append(f"| {label} | {a_metrics.get(key,0)} | {b_metrics.get(key,0)} |")

    lines.extend([
        "",
        "## Notes",
        "",
        "- Counts are derived from compact Actions lines (e.g., `**Terminal** — ...`).",
        "- Failures are approximated by `→ exit N` suffixes and status lines; stderr content is not parsed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Summarize and compare compact chat exports.")
    p.add_argument("first", help="First markdown export file")
    p.add_argument("second", nargs="?", help="Second markdown export file for comparison")
    p.add_argument("--output", "-o", help="Output markdown file (default: exports/compare-<a>-vs-<b>.md)")
    args = p.parse_args()

    a_id, a_metrics = summarize_export(Path(args.first))

    if args.second:
        b_id, b_metrics = summarize_export(Path(args.second))
        out = render_compare_md(a_id, a_metrics, b_id, b_metrics)
        out_path = Path("AI-Agent-Workspace/ChatHistory/exports") / f"compare-{a_id}-vs-{b_id}.md"
        if args.output:
            out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        # Single summary mode
        lines = [f"# Export Summary — {a_id}", "", "````", Path(args.first).read_text(encoding='utf-8', errors='ignore')[:0], "````"]
        print("\n".join(lines))


if __name__ == "__main__":
    main()
