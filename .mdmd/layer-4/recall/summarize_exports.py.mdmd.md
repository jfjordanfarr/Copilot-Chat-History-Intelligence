# Layer 4 — AI-Agent-Workspace/summarize_exports.py

Implementation
- File: [AI-Agent-Workspace/summarize_exports.py](../../../AI-Agent-Workspace/summarize_exports.py)

Purpose
- Quick counts from compact exports and an optional A/B comparison report to track exporter changes.

Public surface
- CLI: summarize_exports.py <first.md> [second.md] [--output path]

Key functions
- summarize_export(path) -> (session_id, metrics)
  - Counts turns, Actions sections, and action lines by title; approximates terminal failures via “→ exit N” suffix and status lines.
- render_compare_md(a_id, a_metrics, b_id, b_metrics) -> str
  - Renders a small Markdown table and notes.

Inputs/Outputs
- Reads export Markdown; writes `exports/compare-<a>-vs-<b>.md` unless output path provided; prints summaries in single-file mode.

Edge cases
- Suppresses noisy Raw* titles from earlier formats.

Contracts
- Works over compact Actions output produced by the exporter; does not parse raw JSON payloads.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002
