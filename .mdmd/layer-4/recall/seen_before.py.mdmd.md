# Layer 4 — seen_before.py

Implementation
- File: [seen_before.py](../../../seen_before.py)

Purpose
- Search existing Markdown exports for repeated action motifs, answering “have I seen this before?” across sessions.

Public surface
- CLI: seen_before.py "<action line or command>" [--dir exports] [--top N]

Key functions
- normalize(text) -> str: lowercases; removes “Seen before (Nx)”; masks URIs/paths/UUIDs; collapses digits/whitespace.
- iter_action_title_lines(markdown) -> iter[str]: yields action title lines inside “#### Actions” sections.
- index_exports(paths) -> (counts: dict[fingerprint->count], where: dict[fingerprint->[(path,title)]])

Inputs
- Markdown exports under `AI-Agent-Workspace/ChatHistory/exports/`.

Outputs
- Exact fingerprint matches or near matches (Jaccard ≥ 0.5) with file names and exemplar lines.

Behavior
- Extracts only the first line of each action block (“**Title** — summary”) to fingerprint motifs.
- Offers fuzzy matching using token Jaccard to catch similar commands/summaries.

Edge cases
- Skips non-readable files; ignores compare files.

Contracts
- Non-destructive, read-only; complements within-session “Seen before (Nx)” annotations in the exporter.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R004
