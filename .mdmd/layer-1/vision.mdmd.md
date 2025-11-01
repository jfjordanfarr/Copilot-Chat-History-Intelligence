# Layer 1 — Vision & User Stories

Purpose
- Build a Copilot-first recall system that can reliably answer: “Have I done this before?” across any workspace Copilot has touched.
- Produce action-aware Markdown exports that mirror the VS Code chat UI while layering in the missing context Copilot needs to improve its own behavior (failures, motifs, summaries, provenance).
- Generate progressive “levels of detail” (LOD) artifacts—from high-level session synopses down to full tool traces—so agents can pick the smallest representation that still preserves the lesson.

Grounding (sources)
- Derived from a census of 62+ `jfjordanfarr:` prompts in `AI-Agent-Workspace/ChatHistory/2025-10-21.md` and deltas in `2025-10-22.md`.
- Core themes across the prompts: zero manual exports; SQLite catalog as the durable audit trail; compact, UI-parity Markdown; failure visibility; motif (“seen before”) signals; Windows PowerShell guardrails; fast mid-conversation recall.

Vision
- Losslessly ingest Copilot chat histories from VS Code global storage and normalize them into a queryable SQLite catalog with explicit provenance and schema history.
- Render compact “Actions” blocks for tools (Terminal, Apply Patch, Search, Read, etc.) with outcomes, statuses, failure tails, and cross-session counts so transcripts stay readable yet decision-ready.
- Detect repeats (“motifs”) within and across sessions, including recurring action sequences, and annotate them inline (“Seen before (Nx)” / “Seen across N sessions”), enabling Copilot to learn from prior attempts mid-flight.
- Produce layered outputs: session exports, motif indexes, and future ultra-compact LOD summaries that an agent can skim before drilling into full transcripts.
- Expose a small set of CLIs (and later MCP hooks) to power “have I done this before?” queries that are fast enough to use during a chat.

Why this matters
- Copy-All is great for user intent but omits structured tool outcomes; Copilot forgets which commands failed or which patches repeated.
- A case-corpus over your own work lets Copilot avoid replaying failures, suggest proven fixes, and tune instructions to the quirks of the current workspace.

- As a Copilot agent, I can ask “have I done this before?” and get the top similar snippets with tool outcomes (exit codes, error tails, status badges) in <1–2s.
- As a developer, I can export any session to Markdown that mirrors the chat UI plus: Actions sections, per-turn counts, a session Actions + Status summary, Motifs (within and across sessions), and failure tails.
- As a developer needing quick context, I can skim a higher-level LOD summary before opening the full export.
- As a developer on Windows, I get PowerShell-safe commands and no hanging here-doc patterns.
- As an ops/debugger, I can spot repeated terminal failures across days via inline “Seen before / Seen across” badges and motif summaries.

Scope
- In-scope: SQLite catalog from on-disk VS Code Copilot storage; Markdown exporter with compact action renderers; TF‑IDF recall with caching; motif fingerprinting (single + cross-session); incremental LOD summaries; simple CLIs.
- Out of scope (for now): general-purpose knowledge graphs, remote vector services, secret/PII handling beyond current pruning, and modifying the Copilot extension itself.

Success criteria
- Exported sessions contain Actions + per-turn counts + session summary + Motifs + sequence motifs + cross-session counts and render failure/warning tails for non-zero exits (and warn-on-success cases).
- “Have I done this before?” returns relevant prior contexts within ~1–2 seconds after first cache build and can elevate the matching LOD artifact.
- Docs live in `.mdmd/` and stay consistent with code via small L4 contracts per module and an up-to-date workplan.

Risks & mitigations
- Windows PowerShell hangs on multi-line Python → use `-c` or helper scripts; avoid here-docs.
- Large JSON and long transcripts → cap tails, summarize patches, and cache TF‑IDF vectors.
- Format drift across Copilot versions → keep a pattern registry with safe fallbacks to raw JSON (behind a verbose switch).

Roadmap sketch
- M1 ingestion to SQLite with schema manifest and README; basic export parity with UI. (Complete)
- M2 compact action renderers, per-turn counts, Actions summary; failure tails. (Complete)
- M3 motif fingerprints + “Seen before (Nx)” + Motifs section. (Complete)
- M4 cross-session motif counts + sequence motifs + scoped filters + warning tails. (Complete)
- M5 LOD summary generation + MCP surface for recall/motif queries + privacy toggle + test/CI harness.

Next layer
- Continue to Layer 2 (Requirements & Roadmap): ../layer-2/requirements.mdmd.md
