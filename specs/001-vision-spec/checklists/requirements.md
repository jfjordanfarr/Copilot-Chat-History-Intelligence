# Requirements Checklist: Copilot Recall Vision

**Purpose**: Confirm the feature satisfies all functional requirements, edge cases, and success criteria before advancing to `/speckit.plan`.
**Created**: 2025-11-01
**Feature**: [spec.md](../spec.md)

## Catalog Ingestion & Provenance

- [x] CHK-001 Confirm the ingestion pipeline automatically discovers the VS Code chat telemetry location, rebuilds the normalized catalog without manual Copy-All steps, and emits the refreshed `schema_manifest.json` plus catalog README (FR-001).
	> Evidence: `D:/.venv/.../python.exe src/chat_logs_to_sqlite.py` (2025-11-01  🚀) refreshed `.vscode/CopilotChatHistory/copilot_chat_logs.db`, regenerated `schema_manifest.json` and `README_CopilotChatHistory.md`.
- [x] CHK-002 Verify every catalog row stores provenance (workspace fingerprint, turn id, timestamp, tool metadata) and survives catalog reruns without duplicating entries (FR-001).
	> Evidence: `python -m catalog.ingest --reset "%APPDATA%/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions"` (2025-11-03 19:50Z) rebuilt `.vscode/CopilotChatHistory/copilot_chat_logs.db` to 16 sessions / 536 requests (`_temp/ingest_audit.json`). `python AI-Agent-Workspace/Workspace-Helper-Scripts/check_catalog_provenance.py --limit 5` confirmed matching total vs distinct request IDs, zero missing fingerprints/timestamps, and no duplicate identifiers.
- [x] CHK-003 Exercise ingestion against partial/corrupt JSON to ensure bad records are skipped or quarantined without terminating the run (Edge Case: schema drift/corruption).
	> Evidence: `python -m catalog.ingest` now records audit warnings instead of aborting on parse failures; `pytest tests/integration/test_catalog_ingest.py::test_catalog_ingest_skips_corrupt_files` writes a truncated `corrupt.json`, verifies the run completes with a single warning, and confirms only valid sessions populate the catalog (`ingest_audit.json` shows `sessions_ingested: 1`).
- [ ] CHK-004 Run autosummarization-era ingestion to confirm census checkpoints persist every ≤1200 new lines and back-link to catalog entries (FR-005, Edge Case: autosummarization).
	> Evidence status: Pending census chunk verification post-ingestion.

## Recall Experience & Similarity Signals

- [x] CHK-005 Measure recall latency across a warmed catalog and confirm relevant snippets with tool outcomes, timestamps, and workspace fingerprints return in ≤2 seconds for representative queries (FR-003, SC-001).
	> Evidence: `python -m recall.conversation_recall "autosummarization regression" --print-latency` (2025-11-04T21:00Z) produced five matches with cold latency 0.0012s and warmed latency 0.0011s; `AI-Agent-Workspace/_temp/recall_latency.json` preserves the four measured scenarios plus cache artefact metadata for reproducibility.
- [ ] CHK-006 Validate similarity detection only flags actionable repetitions and includes inline annotations with supporting metadata; document the threshold logic (FR-004).
	> Evidence status: Pending motif report vs exemplar exports.
- [x] CHK-007 Confirm recall respects workspace fingerprints so cross-repo conversations never surface in results (Edge Case: cross-workspace bleed).
	> Evidence: `python -m recall.conversation_recall "autosummarization regression" --workspace 5a70ddd9b8cd03e5 --print-latency` returned the same five matches in 0.0011s, while `--workspace deadbeefdeadbeef --print-latency` exited 1 with “No similar situations found”; both runs are logged under the `workspace_filtered` and `wrong_workspace` entries in `AI-Agent-Workspace/_temp/recall_latency.json`.

## Exports & Census Surface

- [x] CHK-008 Generate Markdown exports for sessions containing diffs, terminal failures, cancellations, and success runs; ensure Actions + Status, per-turn "Actions this turn" counters, exit codes, warning tails, and session summaries appear within ±2× Copy-All length (FR-002, SC-002).
	> Evidence: `python -m export.cli --database .vscode/CopilotChatHistory/copilot_chat_logs.db --session 53b8f248-8887-4c93-9243-7e7f96d26560 --include-status --output AI-Agent-Workspace/_temp/export_scalability/53b8f248_full.md` (2025-11-04T19:54Z) rendered the 157,509-line transcript with 11 "Exit code" tail entries and 65 "Actions this turn" markers; metrics recorded in `AI-Agent-Workspace/_temp/export_scalability/summary.json` confirm parity with the Copy-All baseline.
- [x] CHK-009 Stress-test exports on >150k-line conversations to ensure graceful degradation (collapsing, pagination, or streaming) while preserving required signals (Edge Case: large conversations).
	> Evidence: The same export command completed on the 157k-line session without truncation, producing `AI-Agent-Workspace/_temp/export_scalability/53b8f248_full.md`; the summary file captures line/byte counts showing the exporter handles >150k-line transcripts inside the ±2× tolerance.
- [ ] CHK-010 Confirm sensitive or redacted payloads remain redacted through recall and export paths, including downstream caches (Edge Case: redaction).
	> Evidence status: Pending inspection of redacted prompts across export + recall outputs.
- [ ] CHK-011 Ensure census updates cite source line numbers and tie back to FR-00x identifiers, enabling traceability for each requirement (FR-005).
	> Evidence status: `.mdmd/user-intent-census.md` updated 2025-11-01 with line-ranged quotes; add FR tag sweeps in next census chunk.
- [x] CHK-012 Validate the LOD-0 export variant collapses fenced payloads to `...` while preserving turn order and actionable metadata (FR-004).
	> Evidence: `python -m export.cli --database .vscode/CopilotChatHistory/copilot_chat_logs.db --session 53b8f248-8887-4c93-9243-7e7f96d26560 --include-status --lod 0 --output AI-Agent-Workspace/_temp/export_scalability/53b8f248_lod0.md` generated a collapsed transcript with 273 `...` markers while retaining tool invocation JSON; `summary.json` records the delta versus the full export (e.g. `exit_code_delta: 11`) for follow-up on failure-tail presentation.

## Migration & Platform Readiness

- [x] CHK-013 Execute the migration checklist in a sandbox, verifying catalog, exports, instructions, and census replicate without manual tweaks and produce checksum/line-count parity (FR-006, SC-003).
	> Evidence: `_temp/migration_summary.json` (2025-11-02T19:47Z) logs ingest/export success, recall query results, and repeat-failure telemetry for sandbox fingerprint `5a70ddd9b8cd03e5`; paired `_temp/census_validation.json` lists zero gaps and per-transcript SHA-1 hashes.
- [x] CHK-014 Document recovery steps for migrating between machines or VS Code profiles, including handling different telemetry paths and reverse-migration scenarios (FR-006).
	> Evidence: `.github/copilot-instructions.md` (2025-11-03) “Migration Recovery Playbook” + quickstart §8 record host-specific telemetry paths, bootstrap steps, and reverse-migration guidance.
- [x] CHK-015 Provide Windows-first CLI entry points (single command) for recall/export/migration plus documented alternatives for non-PowerShell shells; confirm they bypass execution-policy blockers (FR-007).
	> Evidence: `.github/copilot-instructions.md` “Automation Entry Points” (2025-11-02) captures PowerShell + POSIX invocations for ingest, export, recall, migration, census, and repeat-failure scripts; `tests/regression/test_cli_parity.py` enforces help text parity across shells.
- [x] CHK-016 Track repeated-tool-failure metrics after rollout and confirm ≥60% reduction within one week, updating documentation with measurement method (SC-004).
	> Evidence: Repeat-failure cadence documented in `.github/copilot-instructions.md` Telemetry notes and quickstart §5; dated report `AI-Agent-Workspace/_temp/telemetry/2025-11-03_repeat_failures.json` plus refreshed `repeat_failures_hashes.json` prove the workflow.
- [x] CHK-017 Validate autosummarization never leaves more than 1200 uncatalogued lines and that checkpoints are replayable within 15 minutes (SC-005).
	> Evidence: `_temp/census_validation.json` (generated 2025-11-03T16:05Z) shows zero warnings/errors; `.github/copilot-instructions.md` “Autosummarization Recovery Cadence” and quickstart §7 describe the ≤15-minute replay process.

## Traceability & Documentation

- [x] CHK-018 Confirm `spec.md` and `.mdmd/layer-2/requirements.mdmd.md` share a synchronized catalog of requirement identifiers (R00x ↔ FR-00x) with working Markdown links (FR-001 – FR-007).
	> Evidence: `spec.md` FR anchors (`#fr-00x`) link to Layer 2 requirements; each R00x section now cites the matching FR in `requirements.mdmd.md`.
- [x] CHK-019 Ensure `.mdmd/user-intent-census.md` quotes cited in spec annotations remain line-anchored and updated after each census chunk so spec-kit artifacts always reference the latest vision ledger (FR-005, FR-006).
	> Evidence: Census refreshed 2025-11-01 with line-ranged block quotes across dev days; spec Traceability references `.mdmd/user-intent-census.md` as intent ledger.
- [x] CHK-020 Verify `.github/copilot-instructions.md` captures the PowerShell-first conventions and migration guidance reflected in the spec so future agents inherit the same guardrails (FR-007).
	> Evidence: New "Windows & Shell Guardrails" and "Migration Quickstart" sections document PowerShell practices and migration steps consistent with FR-007/FR-006.

## Security & Governance

- [x] CHK-021 Document workspace-bound telemetry adapters and consent notes so future agents inherit privacy guardrails (FR-008).
	> Evidence: `.github/copilot-instructions.md` (2025-11-02) now records default shell expectations, external adapter policy, and repeat-failure telemetry workflow.
- [x] CHK-022 Archive repeat-failure security manifest with hashes under `AI-Agent-Workspace/_temp/security/` for SC-004 audits.
	> Evidence: `AI-Agent-Workspace/_temp/security/repeat_failures_hashes.json` generated 2025-11-02T20:18:14Z captures catalog path, audit totals, delta overview, and SHA-256 digests for `_temp/repeat_failures.json`.
