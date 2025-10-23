# Layer 3 — Architecture & Solution Components

System overview
- Inputs: VS Code Copilot chat archives under globalStorage and per‑workspace `workspaceStorage/*/chatSessions`.
- Storage: SQLite catalog (`AI-Agent-Workspace/live_chat.db`) + `schema_manifest.json` (and README).
- Outputs: Action‑aware Markdown exports under `AI-Agent-Workspace/ChatHistory/exports/` and recall results via CLIs.

Key components
1) Ingestor — `script/chat_logs_to_sqlite.py`
- Scans storage; filters session JSON; reconstructs `requests[]` from logging rows.
- Writes normalized tables and helper views; records source provenance.

2) Exporter — `script/export_chat_sessions_to_markdown.py` + `script/copilot_markdown/*`
- `markdown.py`: builds transcript with USER/Copilot text, Actions blocks, per‑turn counts, session Actions summary, Motifs.
- `patterns.py`: formatters for Terminal (exit, stderr tail, interactive, shell/CWD/duration), Apply Patch (file counts, +/- deltas), Read/Search/Reference.
- `actions.py`: composes compact action lines from `metadata.messages` with noise suppression.
- `response_parser.py`: hydrates actions from response text when structured metadata is missing.

3) Recall & analysis — `conversation_recall.py`, `AI-Agent-Workspace/seen_before.py`, `AI-Agent-Workspace/summarize_exports.py`
- TF‑IDF vector cache under `AI-Agent-Workspace/.cache/conversation_recall/` (configurable, rebuildable).
- Motif recall over exports (exact and near matches) and A/B export metrics.

Core data flows
- Storage → Ingestor → SQLite (requests/logs/views/manifest)
- SQLite → Exporter → Markdown (UI‑parity + signals)
- Markdown + SQLite → Recall CLIs → “Have I done this before?” answers

Normalization & motifs
- Fingerprinting: lowercase, path/URI/UUID masking, number collapse, whitespace squeeze.
- Block segmentation: detect `**Title** — summary` blocks inside Actions; per‑turn and session‑level aggregation.
- Seen‑before annotations: maintain a session‑scoped map; append `— Seen before (Nx)` to repeats.

Performance & ergonomics
- Cache expensive recall vectors; cap terminal tails; avoid huge raw payloads unless `--raw-actions`.
- PowerShell‑first: avoid here‑docs and multi‑line `-c`; prefer helper scripts for anything complex.

Extensibility
- Pattern registry for action formatting; safe fallbacks to raw JSON (opt‑in) for new/unknown kinds.
- Future MCP endpoints for motif/recall queries backed by the same catalog.

Traceability
- Each exported action retains enough context (tool name, summary, status) to audit outcomes while keeping transcripts near UI size.

Next layer
- Continue to Layer 4 (Implementation Contracts):
	- Exporter: ../layer-4/exporter/markdown.py.mdmd.md, ../layer-4/exporter/patterns.py.mdmd.md, ../layer-4/exporter/actions.py.mdmd.md, ../layer-4/exporter/response_parser.py.mdmd.md
	- CLIs: ../layer-4/cli/export_chat_sessions_to_markdown.py.mdmd.md, ../layer-4/cli/chat_logs_to_sqlite.py.mdmd.md
	- Recall: ../layer-4/recall/conversation_recall.py.mdmd.md, ../layer-4/recall/seen_before.py.mdmd.md, ../layer-4/recall/summarize_exports.py.mdmd.md

Previous layer
- Back to Layer 2 (Requirements): ../layer-2/requirements.mdmd.md

Requirements mapping
- Ingestor (chat_logs_to_sqlite.py) → [R001](../layer-2/requirements.mdmd.md#R001)
- Exporter (markdown/actions/patterns/response_parser) → [R002](../layer-2/requirements.mdmd.md#R002), [R003](../layer-2/requirements.mdmd.md#R003), [R004](../layer-2/requirements.mdmd.md#R004)
- Recall (conversation_recall.py, seen_before.py) → [R005](../layer-2/requirements.mdmd.md#R005)
- CLI ergonomics (Windows-first) → [R006](../layer-2/requirements.mdmd.md#R006)
