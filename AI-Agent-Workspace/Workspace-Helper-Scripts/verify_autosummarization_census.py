"""Cross-check autosummarization prompts against user-intent census coverage.

This helper scans the normalized Copilot catalog for prompts referencing
autosummarization rehydrate commands (keywords default to "autosummarization"
/ "lossy autosummarization"). For every `#file:<transcript>:<start>-<end>` range
mentioned in those prompts, the script verifies that the user-intent census
contains a chunk for the same transcript whose bounds fully cover the
referenced span and do not exceed the configured line limit (default 1200).

The goal is to prove that autosummarization checkpoints created during
ingestion always have durable census coverage, satisfying FR-005/CHK-004.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_DB = Path(".vscode/CopilotChatHistory/copilot_chat_logs.db")
DEFAULT_CENSUS = Path(".mdmd") / "user-intent-census.md"
DEFAULT_LIMIT = 1200
DEFAULT_KEYWORDS = ("autosummarization", "lossy autosummarization")

CHUNK_PATTERN = re.compile(
    r"^####\s+(?:\[(?P<label>[^\]]+)\]\s*)?Lines\s+(?P<start>\d+)\s*-\s*(?P<end>\d+)\b.*$"
)
FILE_REFERENCE_PATTERN = re.compile(
    r"#file:(?P<path>[^:\s]+):(?P<start>\d+)-(?P<end>\d+)",
    re.IGNORECASE,
)
FINGERPRINT_PATTERN = re.compile(r"fingerprint=([0-9a-f]{8,40})", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    label: str
    start: int
    end: int


@dataclass
class Prompt:
    request_id: str
    prompt_text: str
    workspace_fingerprint: Optional[str]
    session_id: Optional[str]


@dataclass
class Reference:
    label: str
    start: int
    end: int
    prompt_text: str
    request_id: str
    workspace_fingerprint: Optional[str] = None
    origin_fingerprint: Optional[str] = None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify autosummarization prompts have census coverage."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Catalog SQLite database path (default: .vscode/CopilotChatHistory/copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--census",
        type=Path,
        default=DEFAULT_CENSUS,
        help="Path to user-intent census markdown (default: .mdmd/user-intent-census.md).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum allowed gap/span in census coverage (default: 1200).",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        dest="keywords",
        default=[],
        help="Keyword to search for in prompts (repeatable, defaults to autosummarization phrases).",
    )
    parser.add_argument(
        "--workspace-fingerprint",
        action="append",
        dest="workspace_fingerprints",
        default=[],
        help="Limit verification to prompts captured for the given workspace fingerprint (repeatable).",
    )
    parser.add_argument(
        "--workspace-root",
        action="append",
        dest="workspace_roots",
        default=[],
        type=Path,
        help="Compute a fingerprint from this workspace root and restrict prompts to it (repeatable).",
    )
    parser.add_argument(
        "--ignore-label",
        action="append",
        dest="ignore_labels",
        default=[],
        help="Skip census verification for the given transcript label (repeatable).",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Optional JSON summary output path.",
    )
    return parser.parse_args(argv)


def load_chunks(census_path: Path) -> Dict[str, List[Chunk]]:
    if not census_path.exists():
        raise FileNotFoundError(f"Census file not found: {census_path}")
    by_label: Dict[str, List[Chunk]] = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        match = CHUNK_PATTERN.match(line.strip())
        if not match:
            continue
        label = (match.group("label") or "").strip()
        start = int(match.group("start"))
        end = int(match.group("end"))
        by_label.setdefault(label, []).append(Chunk(label=label, start=start, end=end))
    if not by_label:
        raise ValueError(f"No census chunk headings found in {census_path}")
    for chunks in by_label.values():
        chunks.sort(key=lambda chunk: (chunk.start, chunk.end))
    return by_label


def compute_workspace_fingerprint(workspace_root: Path) -> str:
    resolved = workspace_root.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()
    return digest[:16]


def fetch_autosummarization_prompts(
    db_path: Path,
    keywords: Iterable[str],
    fingerprints: Optional[Sequence[str]] = None,
) -> List[Prompt]:
    if not db_path.exists():
        raise FileNotFoundError(f"Catalog database not found: {db_path}")
    terms = tuple({kw for kw in keywords if kw}) or DEFAULT_KEYWORDS
    clauses: List[str] = []
    params: List[str] = []
    if terms:
        placeholders = " OR ".join("prompt_text LIKE ?" for _ in terms)
        clauses.append(f"({placeholders})")
        params.extend([f"%{kw}%" for kw in terms])
    if fingerprints:
        fp_placeholders = ",".join("?" for _ in fingerprints)
        clauses.append(f"workspace_fingerprint IN ({fp_placeholders})")
        params.extend(list(fingerprints))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT request_id, prompt_text, workspace_fingerprint, session_id "
        f"FROM requests{where}"
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    prompts: List[Prompt] = []
    for row in rows:
        prompts.append(
            Prompt(
                request_id=row["request_id"],
                prompt_text=row["prompt_text"] or "",
                workspace_fingerprint=row["workspace_fingerprint"],
                session_id=row["session_id"],
            )
        )
    return prompts


def extract_references(prompts: Iterable[Prompt]) -> List[Reference]:
    references: List[Reference] = []
    for prompt in prompts:
        for match in FILE_REFERENCE_PATTERN.finditer(prompt.prompt_text):
            path = match.group("path")
            start = int(match.group("start"))
            end = int(match.group("end"))
            label = Path(path).stem
            origin_fp: Optional[str] = None
            for fp_match in FINGERPRINT_PATTERN.finditer(prompt.prompt_text[: match.start()]):
                origin_fp = fp_match.group(1).lower()[:16]
            references.append(
                Reference(
                    label=label,
                    start=start,
                    end=end,
                    prompt_text=prompt.prompt_text,
                    request_id=prompt.request_id,
                    workspace_fingerprint=(prompt.workspace_fingerprint or None),
                    origin_fingerprint=origin_fp,
                )
            )
    return references


@dataclass
class VerificationResult:
    covered: List[Tuple[Reference, List[Chunk]]]
    uncovered: List[Reference]
    exceeded: List[Tuple[Reference, Chunk]]
    ignored: List[Reference]

    def to_summary(self) -> Dict[str, object]:
        def ref_payload(ref: Reference) -> Dict[str, object]:
            return {
                "label": ref.label,
                "start": ref.start,
                "end": ref.end,
                "request_id": ref.request_id,
                "workspace_fingerprint": ref.workspace_fingerprint,
                "origin_fingerprint": ref.origin_fingerprint,
            }

        return {
            "covered": [
                {
                    "reference": ref_payload(ref),
                    "chunks": [
                        {
                            "label": chunk.label,
                            "start": chunk.start,
                            "end": chunk.end,
                        }
                        for chunk in chunks
                    ],
                }
                for ref, chunks in self.covered
            ],
            "uncovered": [ref_payload(ref) for ref in self.uncovered],
            "exceeded": [
                {
                    "reference": ref_payload(ref),
                    "chunk": {
                        "label": chunk.label,
                        "start": chunk.start,
                        "end": chunk.end,
                    },
                }
                for ref, chunk in self.exceeded
            ],
            "ignored": [ref_payload(ref) for ref in self.ignored],
        }


def verify_references(
    references: Sequence[Reference],
    chunks_by_label: Dict[str, List[Chunk]],
    limit: int,
    ignore_labels: Sequence[str],
) -> VerificationResult:
    ignore_set = {label.strip() for label in ignore_labels if label}
    covered: List[Tuple[Reference, List[Chunk]]] = []
    uncovered: List[Reference] = []
    exceeded: List[Tuple[Reference, Chunk]] = []
    ignored: List[Reference] = []
    for ref in references:
        if ref.label in ignore_set:
            ignored.append(ref)
            continue
        chunks = chunks_by_label.get(ref.label, [])
        coverage: List[Chunk] = []
        coverage_end = ref.start - 1
        status: str = "gap"
        violating_chunk: Optional[Chunk] = None
        for chunk in chunks:
            if chunk.end < ref.start:
                continue
            if chunk.start > ref.end:
                break
            if chunk.start > coverage_end + 1:
                status = "gap"
                break
            if coverage and chunk.start <= coverage[-1].start and chunk.end <= coverage[-1].end:
                continue
            coverage.append(chunk)
            if (chunk.end - chunk.start + 1) > limit:
                status = "exceeded"
                violating_chunk = chunk
                break
            coverage_end = max(coverage_end, chunk.end)
            if coverage_end >= ref.end:
                status = "covered"
                break
        else:
            if coverage_end >= ref.end:
                status = "covered"
        if status == "covered":
            if coverage:
                covered.append((ref, coverage))
            else:
                uncovered.append(ref)
        elif status == "exceeded" and violating_chunk is not None:
            exceeded.append((ref, violating_chunk))
        else:
            uncovered.append(ref)
    return VerificationResult(
        covered=covered,
        uncovered=uncovered,
        exceeded=exceeded,
        ignored=ignored,
    )


def _reference_key(ref: Reference) -> Tuple[str, int, int, str]:
    return (ref.label, ref.start, ref.end, ref.request_id)


def print_report(
    result: VerificationResult,
    *,
    total_prompts: int,
    prompts_with_refs_total: int,
    prompts_evaluated: int,
    references_total: int,
    references_considered: int,
    references_all: Sequence[Reference],
    foreign_references: Sequence[Reference],
    foreign_prompts: int,
) -> None:
    evaluated_count = len(result.covered) + len(result.uncovered) + len(result.exceeded)
    uncovered_prompts = len({ref.request_id for ref in result.uncovered})
    print(f"Total prompts scanned: {total_prompts}")
    print(f"Prompts with #file ranges: {prompts_with_refs_total}")
    if foreign_prompts:
        print(f"Prompts skipped via workspace filter: {foreign_prompts}")
    print(f"Prompts evaluated: {prompts_evaluated}")
    print(f"Total references extracted: {references_total}")
    print(f"References considered: {references_considered}")
    print(f"References ignored via label filter: {len(result.ignored)}")
    print(f"References skipped via workspace filter: {len(foreign_references)}")
    print(f"References evaluated: {evaluated_count}")
    print(f"Covered within limit: {len(result.covered)}")
    print(f"Exceeded limit: {len(result.exceeded)}")
    print(f"Missing coverage: {len(result.uncovered)}")
    print(f"Prompts without coverage: {uncovered_prompts}")
    if result.exceeded:
        print("Chunks exceeding limit:")
        for ref, chunk in result.exceeded:
            span = chunk.end - chunk.start + 1
            print(
                f"  - {ref.label} lines {chunk.start}-{chunk.end} (span {span}) covers {ref.start}-{ref.end} from request {ref.request_id}"
            )
    if result.uncovered:
        print("Missing coverage for:")
        for ref in result.uncovered:
            print(
                f"  - {ref.label} lines {ref.start}-{ref.end} referenced in request {ref.request_id}"
            )
    status_lookup: Dict[Tuple[str, int, int, str], str] = {}
    for ref in result.uncovered:
        status_lookup[_reference_key(ref)] = "uncovered"
    for ref, _ in result.exceeded:
        status_lookup[_reference_key(ref)] = "exceeded"
    for ref, _ in result.covered:
        status_lookup[_reference_key(ref)] = "covered"
    for ref in result.ignored:
        status_lookup[_reference_key(ref)] = "ignored"
    for ref in foreign_references:
        status_lookup[_reference_key(ref)] = "foreign"
    label_stats: Dict[str, Counter[str]] = defaultdict(Counter)
    for ref in references_all:
        status = status_lookup.get(_reference_key(ref), "unknown")
        label_stats[ref.label][status] += 1
    if label_stats:
        print("Per-transcript status:")
        for label, counts in sorted(label_stats.items()):
            pieces = ", ".join(
                f"{status}={count}" for status, count in sorted(counts.items())
            )
            print(f"  - {label}: {pieces}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    limit = max(1, args.limit)
    chunks_by_label = load_chunks(args.census)
    fingerprints: List[str] = []
    fingerprints.extend(label.lower() for label in args.workspace_fingerprints if label)
    for root in args.workspace_roots:
        fingerprints.append(compute_workspace_fingerprint(root))
    fingerprints = [fp for fp in fingerprints if fp]
    seen_fingerprints = set()
    unique_fingerprints: List[str] = []
    for fp in fingerprints:
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        unique_fingerprints.append(fp)
    fingerprints = unique_fingerprints

    prompts = fetch_autosummarization_prompts(
        args.db,
        args.keywords,
        fingerprints=fingerprints or None,
    )
    references_all = extract_references(prompts)

    def reference_fingerprint(ref: Reference) -> str:
        if ref.origin_fingerprint:
            return ref.origin_fingerprint.lower()
        if ref.workspace_fingerprint:
            return ref.workspace_fingerprint.lower()
        return ""

    fingerprint_counts = Counter(reference_fingerprint(ref) for ref in references_all)
    allowed_fingerprints = {fp.lower() for fp in fingerprints}
    if not allowed_fingerprints and fingerprint_counts:
        nonempty_counts = {fp: count for fp, count in fingerprint_counts.items() if fp}
        if nonempty_counts:
            dominant = max(nonempty_counts.items(), key=lambda item: item[1])[0]
            allowed_fingerprints = {dominant}

    if allowed_fingerprints:
        filtered_references = [
            ref for ref in references_all if reference_fingerprint(ref) in allowed_fingerprints
        ]
        foreign_references = [
            ref for ref in references_all if reference_fingerprint(ref) not in allowed_fingerprints
        ]
    else:
        filtered_references = references_all
        foreign_references = []

    result = verify_references(
        filtered_references,
        chunks_by_label,
        limit,
        ignore_labels=args.ignore_labels,
    )

    prompts_with_refs_total = len({ref.request_id for ref in references_all})
    prompts_with_refs_evaluated = len({ref.request_id for ref in filtered_references})
    foreign_prompts = len({ref.request_id for ref in foreign_references})
    prompts_without_coverage = len({ref.request_id for ref in result.uncovered})

    print_report(
        result,
        total_prompts=len(prompts),
        prompts_with_refs_total=prompts_with_refs_total,
        prompts_evaluated=prompts_with_refs_evaluated,
        references_total=len(references_all),
        references_considered=len(filtered_references),
        references_all=references_all,
        foreign_references=foreign_references,
        foreign_prompts=foreign_prompts,
    )

    fingerprint_summary = dict(
        sorted((fp or "", count) for fp, count in fingerprint_counts.items())
    )
    summary = result.to_summary()
    summary.update(
        {
            "limit": limit,
            "census": str(args.census),
            "database": str(args.db),
            "total_prompts": len(prompts),
            "prompts_with_references_total": prompts_with_refs_total,
            "prompts_with_references": prompts_with_refs_evaluated,
            "prompts_without_coverage": prompts_without_coverage,
            "prompts_skipped_via_workspace_filter": foreign_prompts,
            "references_extracted_total": len(references_all),
            "references_extracted": len(filtered_references),
            "references_skipped_via_workspace_filter": len(foreign_references),
            "references_evaluated": len(result.covered)
            + len(result.uncovered)
            + len(result.exceeded),
            "fingerprint_counts": fingerprint_summary,
            "fingerprints": sorted(fp for fp in allowed_fingerprints),
            "foreign_references": [
                {
                    "label": ref.label,
                    "start": ref.start,
                    "end": ref.end,
                    "request_id": ref.request_id,
                    "workspace_fingerprint": ref.workspace_fingerprint,
                    "origin_fingerprint": ref.origin_fingerprint,
                }
                for ref in foreign_references
            ],
            "foreign_fingerprints": sorted(
                {reference_fingerprint(ref) for ref in foreign_references}
            ),
            "workspace_filter_applied": bool(allowed_fingerprints),
            "ignored_labels": args.ignore_labels,
        }
    )
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if not result.uncovered and not result.exceeded else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
