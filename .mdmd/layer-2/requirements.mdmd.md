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
- Add per-turn “Actions this turn” and a session-level “Actions + Status summary”.
- Surface cross-session counts inline (“Seen across N sessions (M× total)”) when we have prior motif data.

### <a id="R003"></a> R003 — Failure & warning visibility
- For terminal/tool failures, show exit code and capture a capped stderr-first tail with “(truncated)” marker.
- When exit=0 but stderr exists, label as warnings and show a capped tail.
- Detect interactive hangs and annotate “Awaiting input (interactive)”.
- Highlight canceled/terminated turns inline and in session summaries.

### <a id="R004"></a> R004 — Repeat detection & LOD cues
- Normalize action block text (lowercase, mask paths/URIs/UUIDs, collapse numbers/whitespace) so lightweight similarity scoring is viable.
- Within-session: flag suspiciously similar action sequences with “Seen before (Nx)” and list the most repeated snippets when it materially informs next decisions.
- Across sessions: annotate “Seen across N sessions (M× total)” only when similarity crosses an actionable threshold; keep heuristics tunable so we can escalate from simple fingerprints to richer analysis if it sharpens tool-call guidance.
- Provide hooks for deriving higher-level LOD summaries from repeat/similarity data and expose just-enough APIs for future MCP integrations.
- Deliver a lowest-detail LOD (LOD-0) export that mirrors Copy All text but replaces the interior of every fenced/quoted code block with `...` to preserve structure while minimizing tokens.

### <a id="R005"></a> R005 — Recall tooling
- `conversation_recall.py`: TF‑IDF with on-disk caching; keyword query returns top K snippets with provenance.
- `seen_before.py`: scan exports for repeated motifs (exact + near matches, e.g., Jaccard≥0.5).
- `summarize_exports.py`: quick A/B metrics (counts for Actions, Terminal, Apply Patch, statuses, motif trends).
- Lightweight LOD summaries: derive per-session headline stats for quick skims.

### <a id="R006"></a> R006 — CLI ergonomics (Windows-first, portable)
- Provide PowerShell-safe commands; avoid here-doc and multiline `python -c` with complex regex.
- One-liners prefer helper `.py` scripts under `AI-Agent-Workspace/`.
- Allow optional config file to centralize DB/export/cache paths for portability.

### <a id="R007"></a> R007 — Migration readiness & traceability
- Maintain a living development progress census and workplan that map requirement IDs to completion state (per 2025-10-22.md L2492).
- Document the reverse-migration checklist and artifact triage so we can lift only Copilot-authored assets into new workspaces without losing history (2025-10-22.md L2492; 2025-10-23.md L69–1978).
- Keep the user-intent census updated in ~1200-line increments and link requirement updates back to the census so spec-kit branches inherit an authoritative vision ledger (2025-11-01.md L1–648).

Non‑functional requirements

### <a id="NFR001"></a> NFR001 — Performance
- First recall build can be heavy; subsequent queries should be ~sub‑second.

### <a id="NFR002"></a> NFR002 — Reliability
- Tolerate format drift and missing fields; never crash on unknown events.

### <a id="NFR003"></a> NFR003 — Auditability
- Exported Markdown is readable and mirrors UI intent while preserving key tool outcomes.

### <a id="NFR004"></a> NFR004 — Privacy
- Prune sensitive keys (e.g., `encrypted`) and avoid leaking secrets.
- Provide a configurable redaction mode for exports.

### <a id="NFR005"></a> NFR005 — Portability
- Run on Windows first; keep code portable to macOS/Linux.
- Document shell differences (PowerShell vs bash/zsh) for commands and detection heuristics.

Interfaces & contracts (initial)
- Exporter: `render_session_markdown(session, include_status: bool, include_raw_actions: bool=False) -> str`.
- Ingestor: `chat_logs_to_sqlite.py --db <path> [--reset]` writes `live_chat.db` + `schema_manifest.json`.
- Normalization: fingerprint(text) → normalized motif key; segment(action_lines) → blocks.
- LOD summary: derive headline metrics from motif/action data (spec to follow).
- MCP (future): placeholder endpoints for recall_topk and seen_before summaries.

Acceptance checks (representative)
- Export a known session → file contains: Actions blocks, per-turn counts, Actions + Status summary, Motifs, sequence motifs, cross-session annotations, and failure/warning tails as applicable.
- Run recall on a keyword from 10/21 → returns at least one relevant prior prompt with provenance.
- Run `seen_before.py` on exports → identifies repeated terminal command motif(s) and reports cross-session counts.
- Generate a lightweight LOD summary → matches headline counts in detailed export.

Roadmap (aligned with L1)
- M1–M5 milestones track ingestion → export → failure visibility → motifs → LOD/MCP.

Next layer
- Continue to Layer 3 (Architecture & Solution Components): ../layer-3/architecture.mdmd.md
