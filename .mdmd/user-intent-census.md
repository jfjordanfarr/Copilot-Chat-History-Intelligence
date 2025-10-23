# User Intent Census — Dev Days 2025-10-21 and 2025-10-22

Date: 2025-10-22

Canonical location: .mdmd/

Purpose: Establish a durable index of user intent across the last two dev-day conversations to seed MDMD documentation (top-down Layer 1–3) and guide a bottom-up refinement pass (Layer 4).

Sources
- 2025-10-21: AI-Agent-Workspace/ChatHistory/2025-10-21.md (Copy-All transcript)
- 2025-10-22: AI-Agent-Workspace/ChatHistory/2025-10-22.md (Copy-All transcript)

High-level counts
- 2025-10-21: 76 jfjordanfarr: prompts (per in-session summary reference)
- 2025-10-22: ≥ 40 jfjordanfarr: prompts observed so far (file is live-updating)

Note: Subsequent direct searches have also returned 62 matches for 2025-10-21 depending on search parameters (line-start vs anywhere on line). The intent categories and examples below remain representative either way.

Top themes and representative intents (with rough anchors)

1) Build a Copilot-first recall system (“Have I done this before?”)
- Establish SQLite catalog from Copilot storage (chat_logs_to_sqlite.py)
- Enable TF-IDF recall over prompts/responses/tool calls (conversation_recall.py)
- Cross-session recall for command motifs and failure patterns
Refs: 2025-10-21.md 589–2696; 2025-10-22.md lines ~1330–1415

2) Enhanced markdown exports that inform tool outcomes
- Export per-session transcripts with Actions sections and status annotations
- Suppress low-value noise; compact Apply Patch, Terminal, Read, Search
- Add per-turn “Actions this turn,” session-level Actions summary, Motifs (repeats)
Refs: 2025-10-22.md lines ~1018, ~1105, ~1415

3) Terminal failure-tail tuning (PowerShell-centric)
- On exit≠0, show last stderr lines (capped, labeled “(truncated)”) and exit code
- Detect interactive prompts (“Awaiting input”) distinct from hard errors
- Include context when available: shell (pwsh), cwd, duration
Refs: 2025-10-22.md line 1526 (explicit requirement)

4) Motif “colocation” and repeats
- Inline “— Seen before (Nx)” per repeated action motif
- Top “## Motifs (repeats)” section summarizing frequent motifs
- Future: n-gram sequences (e.g., Search→Read→Terminal), cross-session counts
Refs: 2025-10-22.md lines ~1249 (bioinformatics analogy), repeated motif markers throughout

5) DB freshness and targeting
- Rebuild DB; constrain to today’s chats; export latest and second-latest for A/B
Refs: 2025-10-22.md lines ~544, ~914, ~1018, subsequent export confirmations

6) Documentation and guardrails
- Windows/PowerShell guidance (no here-docs; prefer -c or helper scripts)
- Quickstarts for DB+export and “Have I seen this before?” tools
Refs: 2025-10-22.md lines ~161 (instructions update), ongoing references

7) Documentation crystallization (MDMD)
- Top-down pass: vision, requirements, architecture
- Bottom-up pass: L4 docs per module (refinement, not duplication)
Refs: 2025-10-22.md lines ~1633–1648

Observed prompt categories (2025-10-22; sample anchors)
- Summarize prior dev day and hydrate with rich data: lines 1–37, 38–160
- Instructions and failure lessons: line 161 onward
- Next steps/plan and “clear to proceed”: lines 194–198, 267
- Option A (parser) decisions: line 476
- Correct workspace targeting and DB rebuild: lines 544, 914, 1018
- Export second-most-recent; comparison: lines 1087, 1105
- Motif colocation design: line 1249
- Improvement brainstorming: line 1415
- Failure-tail tuning: line 1526
- MDMD documentation: line 1633

Cross-links
- Layer 1 (Vision): .mdmd/layer-1/vision.mdmd.md
- Layer 2 (Requirements): .mdmd/layer-2/requirements.mdmd.md
- Layer 3 (Architecture): .mdmd/layer-3/architecture.mdmd.md

Notes
- This census is intentionally concise; it seeds Layer 1–3 MDMD. As the bottom-up Layer 4 pass uncovers additional details or edge cases, we will iterate this census and Layer 1–3 accordingly (closing the MDMD loop).
