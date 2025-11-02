# Layer 4 — src/export/markdown.py

## Metadata
- Layer: 4
- Implementation ID: IMP-011
- Code Path: [src/export/markdown.py](../../../src/export/markdown.py)
- Exports: `render_session_markdown`, `_render_lod0_transcript`, `render_turn`, `_collapse_structured_blocks`

## Purpose
- Reconstruct VS Code chat transcripts with UI-faithful Actions, status badges, motif annotations, and LOD variants ready for audits.
- Surface repeat patterns (“Seen before/Seen across”) and per-turn action counts that inform migration and recall decisions.
- Provide a Copy-All surrogate (LOD-0) that trims fenced payloads for cheap storage while preserving actionable context.

## Public Symbols

### render_session_markdown(session, *, include_status, include_raw_actions=False, cross_session_dir=None, lod_level=None) -> str
- Primary entry used by `export.cli` and migration smoke tests.
- Emits headers, per-turn blocks, Actions summaries, motif sections, and optional LOD-0 transcript based on parameters.
- Coordinates action rendering, motif fingerprinting, and status inclusion.

### _render_lod0_transcript(session) -> str
- Generates Copy-All style output that collapses fenced/triple-quoted payloads to `...` while preserving turn order.
- Ensures exporters stay within the ±2× Copy-All length constraint for large sessions.

### render_turn(request, *, include_status, include_raw_actions, seen_state) -> str
- Builds the per-turn section (USER, Copilot, Actions, tool invocations, follow-ups).
- Annotates repeats via `seen_state` and threads status lines when failures or cancellations occur.

### _collapse_structured_blocks(text: str) -> str
- Shared helper for LOD-0 transcripts that replaces bulky fenced blocks while signaling truncated content.

## Collaborators
- [src/export/actions.py](../../../src/export/actions.py) — converts raw tool metadata into compact Actions blocks.
- [src/export/patterns.py](../../../src/export/patterns.py) — formats terminal, diff, and read/search motifs consistently.
- [src/export/response_parser.py](../../../src/export/response_parser.py) — rescues embedded tool JSON when metadata is missing.
- [src/export/utils.py](../../../src/export/utils.py) — path normalization, Markdown escaping, timestamp formatting.
- [AI-Agent-Workspace/Workspace-Helper-Scripts/seen_before.py](../../../AI-Agent-Workspace/Workspace-Helper-Scripts/seen_before.py) — shares motif fingerprinting rules for cross-session recall.

## Linked Components
- [Layer 3 — Architecture & Solution Components](../../layer-3/architecture.mdmd.md#key-components) (see “Exporter”).
- [Layer 2 — Requirements](../../layer-2/requirements.mdmd.md#r002--markdown-export-ui-parity--signal) and [R004](../../layer-2/requirements.mdmd.md#r004--repeat-detection--lod-cues).

## Evidence
- Golden export: [tests/integration/test_export_markdown.py](../../../tests/integration/test_export_markdown.py).
- Action rendering: [tests/unit/test_export_actions.py](../../../tests/unit/test_export_actions.py).
- Pattern formatting: [tests/unit/test_export_patterns.py](../../../tests/unit/test_export_patterns.py).
- Migration parity: [tests/regression/test_migration_sandbox.py](../../../tests/regression/test_migration_sandbox.py) (verifies exports regenerate during sandbox runs).

## Observability
- Export paths recorded in migration summaries via `migrate_sandbox.py`, enabling checksum comparison during relocations.
- Supports `include_raw_actions` debug mode for forensic runs without affecting standard audits.

## Follow-up
- Future LOD briefs can reuse motif fingerprints to summarize long sessions without generating full transcripts.
