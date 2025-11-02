# Migration Checklist: Copilot Recall Vision

**Purpose**: Prove the workspace can be relocated (or cloned) without losing catalog, exports, or census evidence.
**Created**: 2025-11-02
**Feature**: [spec.md](../spec.md)

## Sandbox Automation

- [x] MIG-001 Run `python AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py` and capture the generated summary JSON at `AI-Agent-Workspace/_temp/migration_summary.json`.
	> Evidence: `_temp/migration_summary.json` (2025-11-02T17:48Z) captures 15 sessions, 508 requests, export listings, and recall command metadata.
- [x] MIG-002 Confirm the sandbox regenerates `.vscode/CopilotChatHistory/copilot_chat_logs.db`, `schema_manifest.json`, and `README_CopilotChatHistory.md` with the cloned workspace fingerprint.
	> Evidence: `AI-Agent-Workspace/_temp/migration_sandbox/.vscode/CopilotChatHistory/` holds regenerated DB+manifests stamped 2025-11-02 and rooted to the sandbox path.
- [x] MIG-003 Verify the sandbox exports land under `AI-Agent-Workspace/_temp/migration_exports/` with per-session Markdown that mirrors the original workspace output.
	> Evidence: Sandbox `AI-Agent-Workspace/_temp/migration_exports/` contains per-session directories with fresh LOD0 markdown (see sandbox listing 2025-11-02).
- [x] MIG-004 Validate the recall CLI succeeds inside the sandbox by re-running the recorded query from `migration_summary.json` and confirming a non-empty result with latency output.
	> Evidence: `migration_summary.json` reports recall query `"npm run fixtures:verify"` exited 0 with three matches and latency 7 ms.

## Census & Traceability

- [x] MIG-005 Execute `python AI-Agent-Workspace/Workspace-Helper-Scripts/validate_census.py --summary AI-Agent-Workspace/_temp/census_validation.json` and ensure the report lists zero errors and tail gaps ≤ 1200 lines for all transcripts.
	> Evidence: `_temp/census_validation.json` regenerated 2025-11-02T18:41Z with 0 warnings/errors; each labeled transcript (2025-10-21 through 2025-11-01) reports max tail gap 0 and per-label coverage within the 1,200-line cadence.
- [x] MIG-006 Confirm sandbox `.mdmd/` documents and `.github/copilot-instructions.md` retain their links and timestamps after relocation.
	> Evidence: Sandbox `.mdmd/layer-2/requirements.mdmd.md` still links to `../layer-1/vision.mdmd.md`, and `.github/copilot-instructions.md` preserves the 2025-10-22 timestamp inside `AI-Agent-Workspace/_temp/migration_sandbox`.
- [x] MIG-007 Record the SHA-1 hashes of exported transcripts and census files in `_temp/census_validation.json` for traceability during audits.
	> Evidence: `_temp/census_validation.json` lists per-transcript SHA-1 digests alongside census metadata.

## Cleanup & Hygiene

- [x] MIG-008 Remove `AI-Agent-Workspace/Project-Chat-History/Raw-JSON/` (or other heavyweight caches) after evidence capture and document regeneration commands in `README_CopilotChatHistory.md`.
	> Evidence: Workspace tree now omits `Project-Chat-History/Raw-JSON/`; README_CopilotChatHistory.md documents how to recreate then prune the cache post-run.
- [x] MIG-009 Document the sandbox workflow in `specs/001-vision-spec/quickstart.md` or the migration checklist so future agents can repeat the process without prompting.
	> Evidence: Quickstart §8 updated 2025-11-02 with `--repeat-failures-output` guidance and baseline/diff notes for `migrate_sandbox.py`.
- [x] MIG-010 Track follow-up deltas (ingest audit deltas, repeat-failure telemetry) by storing baseline metrics with each sandbox run.
	> Evidence: `_temp/repeat_failures.json` regenerated 2025-11-02T19:47Z via sandbox automation, logging 117 rows and delta output in `_temp/migration_summary.json`.
