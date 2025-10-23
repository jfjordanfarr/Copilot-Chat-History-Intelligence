# Layer 2 — Requirements & Roadmap

Previous layer
- Back to Layer 1 (Vision): ../layer-1/vision.mdmd.md

Functional requirements

### <a id="R001"></a> R001 — Catalog ingestion
- Hydrate from VS Code Copilot storage (globalStorage and per-workspace storage) without manual exports.
- Write a normalized SQLite DB with helper views (`prompt_activity`, `tool_call_details`, `catalog_metadata`).
- Emit a `schema_manifest.json` and a README alongside the DB.

### <a id="R002"></a> R002 — Markdown export (UI-parity + signal)
- Render user/assistant text and a compact Actions section per turn.
- Action types: Terminal (exit/status + stderr tail), Apply Patch (file count, +/- counts), Read, Search, Inline Reference, Tool invocation.
- Suppress noise: `thinking` (optional cap), `mcpServersStarting`, `prepare/toolSerialized`, `textEditGroup` bulk, `codeblockUri` repetition.
- Add per-turn “Actions this turn” and a session-level “Actions summary”.

### <a id="R003"></a> R003 — Failure visibility
- For terminal/tool failures, show exit code and capture a capped stderr-first tail with “(truncated)” marker.
- Detect interactive hangs and annotate “Awaiting input (interactive)”.

### <a id="R004"></a> R004 — Motif detection
- Normalize action block text (lowercase, mask paths/URIs/UUIDs, collapse numbers/whitespace).
- Within-session: annotate repeated motifs with “Seen before (Nx)” and list top motifs.
- Across sessions: prepare counts and summaries (initially via CLI; later inline on export).

### <a id="R005"></a> R005 — Recall tooling
- `conversation_recall.py`: TF‑IDF with on-disk caching; keyword query returns top K snippets with provenance.
- `seen_before.py`: scan exports for repeated motifs (exact + near matches, e.g., Jaccard≥0.5).
- `summarize_exports.py`: quick A/B metrics (counts for Actions, Terminal, Apply Patch, statuses).

### <a id="R006"></a> R006 — CLI ergonomics (Windows‑first)
- Provide PowerShell-safe commands; avoid here-doc and multiline `python -c` with complex regex.
- One-liners prefer helper `.py` scripts under `AI-Agent-Workspace/`.

Non‑functional requirements

### <a id="NFR001"></a> NFR001 — Performance
- First recall build can be heavy; subsequent queries should be ~sub‑second.

### <a id="NFR002"></a> NFR002 — Reliability
- Tolerate format drift and missing fields; never crash on unknown events.

### <a id="NFR003"></a> NFR003 — Auditability
- Exported Markdown is readable and mirrors UI intent while preserving key tool outcomes.

### <a id="NFR004"></a> NFR004 — Privacy
- Prune sensitive keys (e.g., `encrypted`) and avoid leaking secrets.

### <a id="NFR005"></a> NFR005 — Portability
- Run on Windows first; keep code portable to macOS/Linux.

Interfaces & contracts (initial)
- Exporter: `render_session_markdown(session, include_status: bool, include_raw_actions: bool=False) -> str`.
- Ingestor: `chat_logs_to_sqlite.py --db <path> [--reset]` writes `live_chat.db` + `schema_manifest.json`.
- Normalization: fingerprint(text) → normalized motif key; segment(action_lines) → blocks.

Acceptance checks (representative)
- Export a known session → file contains: Actions blocks, per-turn counts, Actions summary, Motifs, and failure tails (when present).
- Run recall on a keyword from 10/21 → returns at least one relevant prior prompt with provenance.
- Run `seen_before.py` on exports → identifies repeated terminal command motif(s).

Roadmap (aligned with L1)
- M1–M5 milestones track ingestion → export → failure visibility → motifs → MCP.

Next layer
- Continue to Layer 3 (Architecture & Solution Components): ../layer-3/architecture.mdmd.md
