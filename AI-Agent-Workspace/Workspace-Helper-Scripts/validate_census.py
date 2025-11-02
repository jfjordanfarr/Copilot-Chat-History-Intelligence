"""Validate user-intent census coverage against transcript line ranges."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

CHUNK_PATTERN = re.compile(
    r"^####\s+(?:\[(?P<label>[^\]]+)\]\s*)?Lines\s+(?P<start>\d+)\s*-\s*(?P<end>\d+)\b.*$"
)
DEFAULT_CENSUS = Path(".mdmd") / "user-intent-census.md"
DEFAULT_LIMIT = 1200


class CensusError(RuntimeError):
    pass


class Chunk:
    __slots__ = ("label", "start", "end", "line_no", "heading")

    def __init__(self, label: str, start: int, end: int, line_no: int, heading: str) -> None:
        self.label = label
        self.start = start
        self.end = end
        self.line_no = line_no
        self.heading = heading


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check census chunk coverage and transcript tails.")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS, help="Path to the user-intent census markdown file.")
    parser.add_argument("--transcript", action="append", dest="transcripts", type=Path, default=[], help="Conversation transcript to validate (may be repeated).")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum allowed gap between census chunks.")
    parser.add_argument("--summary", type=Path, help="Optional JSON summary output path.")
    return parser.parse_args(argv)


def load_chunks(census_path: Path) -> List[Chunk]:
    if not census_path.exists():
        raise CensusError(f"Census file not found: {census_path}")
    chunks: List[Chunk] = []
    for idx, line in enumerate(census_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        match = CHUNK_PATTERN.match(stripped)
        if not match:
            continue
        label = (match.group("label") or "").strip()
        start = int(match.group("start"))
        end = int(match.group("end"))
        chunks.append(Chunk(label=label, start=start, end=end, line_no=idx, heading=stripped))
    if not chunks:
        raise CensusError(f"No chunk headings found in {census_path}")
    return chunks


def hash_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def count_lines(path: Path) -> int:
    if not path.exists():
        raise CensusError(f"Transcript not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def validate(chunks: List[Chunk], *, limit: int) -> Dict[str, object]:
    chunks_sorted = sorted(chunks, key=lambda chunk: (chunk.label, chunk.start, chunk.end))
    errors: List[str] = []
    warnings: List[str] = []
    label_stats: Dict[str, Dict[str, object]] = {}

    def get_stats(label: str) -> Dict[str, object]:
        if label not in label_stats:
            label_stats[label] = {
                "previous_end": 0,
                "max_span": 0,
                "max_gap": 0,
                "max_end": 0,
                "chunk_count": 0,
                "errors": [],
                "warnings": [],
                "first_heading": "",
            }
        return label_stats[label]

    for chunk in chunks_sorted:
        label = chunk.label
        stats = get_stats(label)
        stats["chunk_count"] = int(stats["chunk_count"]) + 1
        if not stats["first_heading"]:
            stats["first_heading"] = chunk.heading
        label_display = label if label else "(default)"

        def add_error(message: str) -> None:
            prefixed = f"[{label_display}] {message}"
            errors.append(prefixed)
            stats["errors"].append(prefixed)

        def add_warning(message: str) -> None:
            prefixed = f"[{label_display}] {message}"
            warnings.append(prefixed)
            stats["warnings"].append(prefixed)

        if chunk.start <= 0 or chunk.end <= 0:
            add_error(f"Invalid chunk bounds at line {chunk.line_no}: {chunk.heading}")
            continue
        if chunk.end < chunk.start:
            add_error(f"Descending range at line {chunk.line_no}: {chunk.heading}")
            continue

        span = chunk.end - chunk.start + 1
        stats["max_span"] = max(int(stats["max_span"]), span)
        if span > limit:
            add_error(f"Chunk exceeds {limit} lines at line {chunk.line_no}: {chunk.heading}")

        previous_end = int(stats["previous_end"])
        if chunk.start > previous_end + 1:
            gap = chunk.start - previous_end - 1
            stats["max_gap"] = max(int(stats["max_gap"]), gap)
            if gap > limit:
                add_error(
                    f"Gap of {gap} lines before chunk at line {chunk.line_no} exceeds limit {limit}: {chunk.heading}"
                )
            else:
                add_warning(
                    f"Gap of {gap} lines before chunk at line {chunk.line_no}: {chunk.heading}"
                )
        if chunk.start <= previous_end:
            overlap = previous_end - chunk.start + 1
            add_warning(
                f"Overlap of {overlap} lines at line {chunk.line_no}: {chunk.heading}"
            )

        stats["previous_end"] = max(previous_end, chunk.end)
        stats["max_end"] = max(int(stats["max_end"]), chunk.end)

    total_chunks = sum(int(stat["chunk_count"]) for stat in label_stats.values())
    overall_max_span = max((int(stat["max_span"]) for stat in label_stats.values()), default=0)
    overall_max_gap = max((int(stat["max_gap"]) for stat in label_stats.values()), default=0)
    overall_max_end = max((int(stat["max_end"]) for stat in label_stats.values()), default=0)

    return {
        "errors": errors,
        "warnings": warnings,
        "labels": label_stats,
        "total_chunks": total_chunks,
        "max_span": overall_max_span,
        "max_gap": overall_max_gap,
        "max_end": overall_max_end,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    chunks = load_chunks(args.census)
    limit = max(1, args.limit)
    stats = validate(chunks, limit=limit)
    errors: List[str] = list(stats["errors"])
    warnings: List[str] = list(stats["warnings"])
    label_stats: Dict[str, Dict[str, object]] = stats["labels"]

    transcripts_by_label: Dict[str, Dict[str, object]] = {}
    for transcript in args.transcripts:
        label = transcript.stem
        line_count = count_lines(transcript)
        digest = hash_file(transcript)
        entry = {
            "label": label,
            "path": str(transcript),
            "lines": line_count,
            "sha1": digest,
            "tail_gap": None,
            "max_end": None,
        }
        if label in transcripts_by_label:
            errors.append(f"[{label}] Duplicate transcript label provided: {transcript}")
            continue
        transcripts_by_label[label] = entry

    def add_label_error(label: str, message: str) -> None:
        label_display = label if label else "(default)"
        prefixed = f"[{label_display}] {message}"
        errors.append(prefixed)
        if label in label_stats:
            label_stats[label]["errors"].append(prefixed)

    def add_label_warning(label: str, message: str) -> None:
        label_display = label if label else "(default)"
        prefixed = f"[{label_display}] {message}"
        warnings.append(prefixed)
        if label in label_stats:
            label_stats[label]["warnings"].append(prefixed)

    table_rows: List[Sequence[str]] = []
    matched_labels = set()
    for label in sorted(label_stats.keys(), key=lambda value: value or ""):
        label_data = label_stats[label]
        label_display = label if label else "(default)"
        chunk_count = int(label_data["chunk_count"])
        max_end = int(label_data["max_end"])
        coverage = "—"
        headline = label_data.get("first_heading") or ""
        transcript_entry = transcripts_by_label.get(label)
        if transcript_entry is not None:
            matched_labels.add(label)
            line_count = int(transcript_entry["lines"])
            transcript_entry["max_end"] = max_end
            if line_count < max_end:
                add_label_error(label, f"Transcript has {line_count} lines but census references line {max_end}")
            else:
                tail_gap = line_count - max_end
                transcript_entry["tail_gap"] = tail_gap
                if tail_gap > limit:
                    add_label_error(label, f"Tail gap of {tail_gap} lines exceeds limit {limit}")
                elif tail_gap > 0:
                    add_label_warning(label, f"Tail gap of {tail_gap} lines within limit {limit}")
            coverage = f"{max_end}/{line_count}" if line_count > 0 else f"{max_end}/0"
        else:
            add_label_error(label, "No transcript provided for census label")
        table_rows.append((label_display, str(chunk_count), coverage, headline))

    unmatched_labels = sorted(set(transcripts_by_label.keys()) - matched_labels)
    for leftover_label in unmatched_labels:
        entry = transcripts_by_label[leftover_label]
        label_display = leftover_label if leftover_label else "(default)"
        errors.append(f"[{label_display}] Transcript {entry['path']} has no census coverage")

    def print_table(title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        print(title)
        widths = [len(header) for header in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(str(cell)))
        header_line = " | ".join(str(header).ljust(widths[idx]) for idx, header in enumerate(headers))
        divider = "-+-".join("-" * width for width in widths)
        print(header_line)
        print(divider)
        for row in rows:
            line = " | ".join(str(cell).ljust(widths[idx]) for idx, cell in enumerate(row))
            print(line)
        print()

    print_table(
        "Census coverage by label:",
        ("Label", "Chunks", "Coverage", "Headline"),
        table_rows,
    )

    if warnings:
        warning_rows = [(message,) for message in warnings]
        print_table("Warnings:", ("Message",), warning_rows)
    else:
        print("Warnings: none\n")

    if errors:
        error_rows = [(message,) for message in errors]
        print_table("Errors:", ("Message",), error_rows)
    else:
        print("Errors: none\n")

    summary_labels: Dict[str, Dict[str, object]] = {}
    for label, label_data in label_stats.items():
        summary_labels[label] = {
            "chunks": int(label_data["chunk_count"]),
            "max_span": int(label_data["max_span"]),
            "max_gap": int(label_data["max_gap"]),
            "max_end": int(label_data["max_end"]),
            "first_heading": label_data.get("first_heading") or "",
            "errors": list(label_data["errors"]),
            "warnings": list(label_data["warnings"]),
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "census": str(args.census),
        "chunks": len(chunks),
        "limit": limit,
        "totals": {
            "max_span": stats["max_span"],
            "max_gap": stats["max_gap"],
            "max_end": stats["max_end"],
            "total_chunks": stats["total_chunks"],
        },
        "warnings": warnings,
        "errors": errors,
        "labels": summary_labels,
        "transcripts": [transcripts_by_label[label] for label in sorted(transcripts_by_label.keys())],
    }
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
