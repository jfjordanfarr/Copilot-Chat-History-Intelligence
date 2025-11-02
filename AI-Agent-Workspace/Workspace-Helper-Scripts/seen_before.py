"""Inspect exported markdown for repeated action motifs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from recall.seen_before import index_exports, normalize, tokens  # noqa: E402

Fingerprint = str


def _export_paths(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.md") if p.is_file() and not p.name.startswith("compare-"))


def _summaries(where: Dict[Fingerprint, List[Tuple[Path, str]]]) -> List[Tuple[int, int, str, List[str]]]:
    rows: List[Tuple[int, int, str, List[str]]] = []
    for fp, entries in where.items():
        sample_path, sample_line = entries[0]
        count = len(entries)
        session_ids = sorted({path.stem for path, _ in entries})
        rows.append((count, len(session_ids), sample_line, session_ids))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return rows


def _print_list(rows: List[Tuple[int, int, str, List[str]]], limit: int) -> None:
    if not rows:
        print("No motifs detected in exports.")
        return
    for count, sess_count, sample, sessions in rows[:limit]:
        session_label = ", ".join(sessions[:6])
        if len(sessions) > 6:
            session_label += f", +{len(sessions) - 6} more"
        print(f"{count}× ({sess_count} sessions) | {sample}")
        if session_label:
            print(f"  Sessions: {session_label}")


def _json_list(rows: List[Tuple[int, int, str, List[str]]], limit: int) -> str:
    payload = [
        {
            "occurrences": count,
            "sessions": session_ids,
            "unique_sessions": session_count,
            "sample": sample,
        }
        for count, session_count, sample, session_ids in rows[:limit]
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _search(query: str, where: Dict[Fingerprint, List[Tuple[Path, str]]], top: int) -> Tuple[List[Tuple[Path, str]], List[Tuple[float, str]]]:
    q_fp = normalize(query)
    exact = where.get(q_fp, [])
    if exact:
        return exact, []
    q_tokens = tokens(query)
    if not q_tokens:
        return [], []
    scored: List[Tuple[float, str]] = []
    for entries in where.values():
        sample = entries[0][1]
        sample_tokens = tokens(sample)
        if not sample_tokens:
            continue
        inter = len(q_tokens & sample_tokens)
        union = len(q_tokens | sample_tokens)
        if union == 0:
            continue
        score = inter / union
        if score >= 0.5:
            scored.append((score, sample))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [], scored[:top]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query Copilot markdown exports for repeated actions.")
    parser.add_argument("query", nargs="?", help="Action line or command to search for.")
    parser.add_argument("--dir", default="AI-Agent-Workspace/ChatHistory/exports", dest="directory", help="Directory containing markdown exports.")
    parser.add_argument("--top", type=int, default=10, help="Number of results to show for listing or search.")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON (for scripting).")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.directory)
    exports = _export_paths(root)
    if not exports:
        print("No export files found.", file=sys.stderr)
        return 1

    counts, where = index_exports(exports)
    if not counts:
        print("No Actions sections detected in exports.")
        return 0

    if args.query:
        exact, fuzzy = _search(args.query, where, args.top)
        if exact:
            print(f"Exact motif match for '{args.query}' ({len(exact)} occurrence(s)):")
            for path, line in exact[: args.top]:
                print(f"- {path.name}: {line}")
            return 0
        if fuzzy:
            print(f"No exact match for '{args.query}'. Showing fuzzy matches (Jaccard ≥ 0.5):")
            for score, line in fuzzy[: args.top]:
                print(f"- {line}  (score {score:.2f})")
            return 0
        print(f"No motifs similar to '{args.query}' found.")
        return 0

    rows = _summaries(where)
    if args.json:
        print(_json_list(rows, args.top))
    else:
        _print_list(rows, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
