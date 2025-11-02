from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_`./:-]+")
ACTIONS_TITLE = re.compile(r"^\*\*[^*]+\*\*\s+—\s+.*$")
SEEN_SUFFIX = re.compile(r"\s+—\s+seen before \(\d+×\)$", re.IGNORECASE)


def normalize(text: str) -> str:
    t = text.lower().strip()
    t = SEEN_SUFFIX.sub("", t)
    t = re.sub(r"file:\/\/[^\s)]+", "<uri>", t)
    t = re.sub(r"[a-z]:[\\/][^\s\"]+", "<path>", t)
    t = re.sub(r"\b\/[\w\-\.\/]+", "<path>", t)
    t = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", t)
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"\s+", " ", t)
    return t


def tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalize(text)))


def iter_action_title_lines(markdown: str) -> Iterable[str]:
    within_actions = False
    for line in markdown.splitlines():
        if line.strip() == "#### Actions":
            within_actions = True
            continue
        if within_actions and line.startswith("### "):
            within_actions = False
        if within_actions and ACTIONS_TITLE.match(line):
            yield line


def index_exports(paths: List[Path]) -> Tuple[Dict[str, int], Dict[str, List[Tuple[Path, str]]]]:
    counts: Dict[str, int] = {}
    where: Dict[str, List[Tuple[Path, str]]] = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for title in iter_action_title_lines(text):
            fp = normalize(title)
            counts[fp] = counts.get(fp, 0) + 1
            where.setdefault(fp, []).append((p, title))
    return counts, where


def main() -> None:
    ap = argparse.ArgumentParser(description="Query exports for repeated action motifs (Have I seen this before?)")
    ap.add_argument("query", help="Action line or terminal command to search for (approximate match)")
    ap.add_argument("--dir", default="AI-Agent-Workspace/ChatHistory/exports", help="Directory of exports to scan")
    ap.add_argument("--top", type=int, default=10, help="Show top N matches")
    args = ap.parse_args()

    root = Path(args.dir)
    files = [p for p in root.glob("*.md") if p.is_file() and not p.name.startswith("compare-")]

    counts, where = index_exports(files)

    q_fp = normalize(args.query)

    # Exact fingerprint match first
    exact = where.get(q_fp, [])

    # Fuzzy: Jaccard over token sets for near matches
    q_tok = tokens(args.query)
    scored: List[Tuple[float, str]] = []
    for fp, items in where.items():
        t = tokens(items[0][1])
        if not t or not q_tok:
            continue
        inter = len(q_tok & t)
        union = len(q_tok | t)
        if union == 0:
            continue
        j = inter / union
        if j >= 0.5 and fp != q_fp:
            scored.append((j, items[0][1]))
    scored.sort(reverse=True)

    if exact:
        print(f"Exact motif match found in {len(exact)} export(s):")
        for (p, title) in exact[: args.top]:
            print(f"- {p.name}: {title}")
    else:
        print("No exact motif match; showing near matches (Jaccard ≥ 0.5):")
        for j, title in scored[: args.top]:
            print(f"- {title}  (score {j:.2f})")


if __name__ == "__main__":
    main()
