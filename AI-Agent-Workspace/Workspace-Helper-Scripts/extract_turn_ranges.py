"""Utility to list turn boundaries in a Copilot chat export.

The script prints a JSON array describing each prompt/response turn with
its speaker label and inclusive line range. Use this to build turn-by-turn
summaries without manually scanning thousands of lines.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List, MutableMapping

TURN_HEADER = re.compile(r"^(\w[\w-]*):\s")


def extract_turns(text_lines: Iterable[str]) -> List[MutableMapping[str, object]]:
    """Return ordered turn metadata for the provided markdown transcript."""
    entries: List[MutableMapping[str, object]] = []
    speaker: str | None = None
    start: int | None = None

    for idx, line in enumerate(text_lines, start=1):
        match = TURN_HEADER.match(line)
        if match:
            if speaker is not None and start is not None:
                entries.append({"speaker": speaker, "start": start, "end": idx - 1})
            speaker = match.group(1)
            start = idx

    if speaker is not None and start is not None:
        entries.append({"speaker": speaker, "start": start, "end": idx})

    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path, help="Path to Copy-All markdown export")
    parser.add_argument(
        "--with-snippet",
        action="store_true",
        help="Include the first non-empty content line as a snippet field.",
    )
    args = parser.parse_args()

    lines = args.transcript.read_text(encoding="utf-8").splitlines()
    turns = extract_turns(lines)

    if args.with_snippet:
        for turn in turns:
            span = lines[turn["start"] - 1 : turn["end"]]
            snippet = ""
            for raw_line in span[1:]:  # skip the speaker header itself
                stripped = raw_line.strip()
                if stripped:
                    snippet = stripped[:160]
                    break
            turn["snippet"] = snippet

    json.dump(turns, fp=sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    import sys

    main()
