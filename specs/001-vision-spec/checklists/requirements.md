# Requirements Checklist: Copilot Recall Vision

**Purpose**: Confirm the feature satisfies all functional requirements, edge cases, and success criteria before advancing to `/speckit.plan`.
**Created**: 2025-11-01
**Feature**: [spec.md](../spec.md)

## Catalog Ingestion & Provenance

- [x] CHK-001 Confirm the ingestion pipeline automatically discovers the VS Code chat telemetry location, rebuilds the normalized catalog without manual Copy-All steps, and emits the refreshed `schema_manifest.json` plus catalog README (FR-001).
	> Evidence: `D:/.venv/.../python.exe src/chat_logs_to_sqlite.py` (2025-11-01  🚀) refreshed `.vscode/CopilotChatHistory/copilot_chat_logs.db`, regenerated `schema_manifest.json` and `README_CopilotChatHistory.md`.
- [ ] CHK-002 Verify every catalog row stores provenance (workspace fingerprint, turn id, timestamp, tool metadata) and survives catalog reruns without duplicating entries (FR-001).
	> Evidence status: Manifest regenerated; need to inspect `copilot_chat_logs.db` for duplicate prompts and confirm provenance fields populated.
- [ ] CHK-003 Exercise ingestion against partial/corrupt JSON to ensure bad records are skipped or quarantined without terminating the run (Edge Case: schema drift/corruption).
	> Evidence status: Pending fault-injection run with truncated `.chatreplay.json` sample.
- [ ] CHK-004 Run autosummarization-era ingestion to confirm census checkpoints persist every ≤1200 new lines and back-link to catalog entries (FR-005, Edge Case: autosummarization).
	> Evidence status: Pending census chunk verification post-ingestion.

## Recall Experience & Similarity Signals

- [ ] CHK-005 Measure recall latency across a warmed catalog and confirm relevant snippets with tool outcomes, timestamps, and workspace fingerprints return in ≤2 seconds for representative queries (FR-003, SC-001).
	> Evidence status: Pending latency measurement for `conversation_recall.py` warm cache.
- [ ] CHK-006 Validate similarity detection only flags actionable repetitions and includes inline annotations with supporting metadata; document the threshold logic (FR-004).
	> Evidence status: Pending motif report vs exemplar exports.
- [ ] CHK-007 Confirm recall respects workspace fingerprints so cross-repo conversations never surface in results (Edge Case: cross-workspace bleed).
	> Evidence status: Pending multi-workspace regression test.

## Exports & Census Surface

- [ ] CHK-008 Generate Markdown exports for sessions containing diffs, terminal failures, cancellations, and success runs; ensure Actions + Status, per-turn "Actions this turn" counters, exit codes, warning tails, and session summaries appear within ±2× Copy-All length (FR-002, SC-002).
	> Evidence status: Pending export comparison against Copy-All transcript for 2025-10-21 session.
- [ ] CHK-009 Stress-test exports on >150k-line conversations to ensure graceful degradation (collapsing, pagination, or streaming) while preserving required signals (Edge Case: large conversations).
	> Evidence status: Pending large-session export run (124k-line reference).
- [ ] CHK-010 Confirm sensitive or redacted payloads remain redacted through recall and export paths, including downstream caches (Edge Case: redaction).
	> Evidence status: Pending inspection of redacted prompts across export + recall outputs.
- [ ] CHK-011 Ensure census updates cite source line numbers and tie back to FR-00x identifiers, enabling traceability for each requirement (FR-005).
	> Evidence status: `.mdmd/user-intent-census.md` updated 2025-11-01 with line-ranged quotes; add FR tag sweeps in next census chunk.
- [ ] CHK-012 Validate the LOD-0 export variant collapses fenced payloads to `...` while preserving turn order and actionable metadata (FR-004).
	> Evidence status: Pending diff between LOD-0 output and Copy-All excerpt.

## Migration & Platform Readiness

- [ ] CHK-013 Execute the migration checklist in a sandbox, verifying catalog, exports, instructions, and census replicate without manual tweaks and produce checksum/line-count parity (FR-006, SC-003).
	> Evidence status: Pending dry-run migration into scratch workspace.
- [ ] CHK-014 Document recovery steps for migrating between machines or VS Code profiles, including handling different telemetry paths and reverse-migration scenarios (FR-006).
	> Evidence status: New migration quickstart in `.github/copilot-instructions.md`; expand with telemetry path matrix.
- [ ] CHK-015 Provide Windows-first CLI entry points (single command) for recall/export/migration plus documented alternatives for non-PowerShell shells; confirm they bypass execution-policy blockers (FR-007).
	> Evidence status: CLI docs pending; note execution-policy bypass approach in future README update.
- [ ] CHK-016 Track repeated-tool-failure metrics after rollout and confirm ≥60% reduction within one week, updating documentation with measurement method (SC-004).
	> Evidence status: Pending exporter metric capture once recall tooling live.
- [ ] CHK-017 Validate autosummarization never leaves more than 1200 uncatalogued lines and that checkpoints are replayable within 15 minutes (SC-005).
	> Evidence status: Pending log review of census checkpoint timestamps.

## Traceability & Documentation

- [x] CHK-018 Confirm `spec.md` and `.mdmd/layer-2/requirements.mdmd.md` share a synchronized catalog of requirement identifiers (R00x ↔ FR-00x) with working Markdown links (FR-001 – FR-007).
	> Evidence: `spec.md` FR anchors (`#fr-00x`) link to Layer 2 requirements; each R00x section now cites the matching FR in `requirements.mdmd.md`.
- [x] CHK-019 Ensure `.mdmd/user-intent-census.md` quotes cited in spec annotations remain line-anchored and updated after each census chunk so spec-kit artifacts always reference the latest vision ledger (FR-005, FR-006).
	> Evidence: Census refreshed 2025-11-01 with line-ranged block quotes across dev days; spec Traceability references `.mdmd/user-intent-census.md` as intent ledger.
- [x] CHK-020 Verify `.github/copilot-instructions.md` captures the PowerShell-first conventions and migration guidance reflected in the spec so future agents inherit the same guardrails (FR-007).
	> Evidence: New "Windows & Shell Guardrails" and "Migration Quickstart" sections document PowerShell practices and migration steps consistent with FR-007/FR-006.
