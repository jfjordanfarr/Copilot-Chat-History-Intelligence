# Tasks: Copilot Recall Vision

**Input**: Design documents from `/specs/001-vision-spec/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Regression-focused tests are included where the specification or research explicitly calls for measurement or golden verification (e.g., TF-IDF latency harness, export parity fixtures, migration sandbox validation).

**Organization**: Tasks are grouped by user story so each slice remains independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish shared fixtures and helpers for the ingestion, export, and recall test suites.

- [x] T001 Create pytest fixtures for `workspace_root` and `sample_catalog_path` in `tests/conftest.py`
- [x] T002 [P] Implement catalog fixture builder utilities in `tests/helpers/catalog_builder.py`
- [x] T003 [P] Document test fixture usage and sample data expectations in `tests/README.md`
- [x] T031 [P] Establish centralized unit-test scaffolding under `tests/unit/` (README, discovery notes) that reuses the shared fixtures in `tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Normalize Copilot telemetry into the schema described in data-model.md, enforce workspace-scoped privacy guardrails, and expose shared catalog helpers. **No user story work may begin until these tasks complete.**

- [x] T004 Populate normalized tables (`requests`, `request_parts`, `tool_outputs`) in `src/catalog/ingest.py`
- [x] T005 [P] Regenerate `schema_manifest.json` + `README_CopilotChatHistory.md` with new schema metadata in `src/catalog/ingest.py`
- [x] T006 [P] Add catalog query helpers (`fetch_session_documents`, `fetch_tool_results`) in `src/catalog/__init__.py`
- [x] T007 Create ingestion integration test validating tables and manifest outputs in `tests/integration/test_catalog_ingest.py`
- [x] T026 [P] Enforce workspace-scoped storage and configurable redaction toggles in `src/catalog/ingest.py` with audit logging saved to `AI-Agent-Workspace/_temp/ingest_audit.json`
- [x] T027 Add regression check `tests/regression/test_redaction_guardrails.py` that simulates secrets in telemetry and asserts no export/recall surface raw values
- [x] T029 Persist repeat-failure aggregates to `metrics_repeat_failures` during ingest (including backfill logic) in `src/catalog/ingest.py`
- [x] T030 Add integration test `tests/integration/test_metrics_repeat_failures.py` to validate repeat-failure counts, timestamps, and redaction

---

## Phase 3: User Story 1 — Rehydrate Context On Demand (Priority: P1) 🎯 MVP

**Goal**: Serve “Have I done this before?” queries within ≤2 seconds using TF-IDF recall enriched with tool outcomes and provenance.

**Independent Test**: Run `python -m recall.conversation_recall "retry pytest after autosummarization" --db .vscode/CopilotChatHistory/copilot_chat_logs.db` against the fixture catalog (default normalized database path) and confirm a relevant snippet (with exit code, stderr tail, timestamp, workspace fingerprint) returns within 2 seconds after cache warm-up.

### Implementation for User Story 1

- [x] T008 [US1] Enrich TF-IDF documents with tool outcomes, timestamps, and session metadata in `src/recall/conversation_recall.py`
- [x] T009 [US1] Add CLI filters, cache key computation, and provenance formatting in `src/recall/conversation_recall.py`
- [x] T010 [P] [US1] Author top-k recall regression test in `tests/regression/test_conversation_recall.py`
- [x] T011 [P] [US1] Implement latency measurement harness in `tests/regression/test_recall_latency.py`

**Checkpoint**: Recall CLI returns actionable snippets (with provenance) inside ≤2 seconds after warm cache.

---

## Phase 4: User Story 2 — Audit Conversations Via UI-Faithful Exports (Priority: P2)

**Goal**: Produce Markdown exports that mirror the VS Code chat UI while surfacing Actions, diff counts, failure tails, motif summaries, and workspace scoping.

**Independent Test**: Export a catalogued session to `AI-Agent-Workspace/Project-Chat-History/CopyAll-Paste/<session-id>.md`, verify Actions + Status summary, failure tails, “Seen before/Seen across” annotations, and ensure output length stays within ±2× the Copy-All artifact.

### Implementation for User Story 2

- [x] T012 [US2] Normalize per-turn Actions with counts and noise suppression in `src/export/actions.py`
- [x] T013 [US2] Render Actions + Status summary, motif sections, and LOD-0 hooks in `src/export/markdown.py`
- [x] T014 [P] [US2] Format failure tails, warning annotations, and interactive states in `src/export/patterns.py`
- [x] T015 [P] [US2] Extend motif analysis pipeline in `AI-Agent-Workspace/Workspace-Helper-Scripts/seen_before.py`
- [x] T016 [US2] Add golden export integration test in `tests/integration/test_export_markdown.py`

**Checkpoint**: Exporter outputs UI-faithful transcripts with actionable status and motif cues ready for audits.

---

## Phase 5: User Story 3 — Migrate Without Losing Lessons (Priority: P3)

**Goal**: Relocate or clone the workspace using scripted checklists while preserving catalog, exports, instructions, and the ≤1200-line census cadence.

**Independent Test**: Run the migration sandbox script to clone into a temp directory, rerun ingestion/export, validate census checkpoints, and compare manifests/logs without manual edits.

### Implementation for User Story 3

- [ ] T017 [P] [US3] Automate migration sandbox flow in `AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py`
- [ ] T018 [US3] Publish migration checklist with evidence slots in `specs/001-vision-spec/checklists/migration.md`
- [ ] T019 [P] [US3] Validate sandbox behavior via `tests/regression/test_migration_sandbox.py`
- [ ] T020 [US3] Implement census checkpoint validator in `AI-Agent-Workspace/Workspace-Helper-Scripts/validate_census.py`

**Checkpoint**: Migration dry run reproduces catalog, exports, instructions, and census without manual intervention.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align documentation and instructions with the implemented behavior while capturing telemetry for SC-004, validating CLI parity across shells, and preserving privacy/security evidence.

- [ ] T021 [P] Update `.mdmd/layer-4/recall/conversation_recall.py.mdmd.md` with new CLI options, caching, and regression evidence
- [ ] T022 [P] Update `.mdmd/layer-4/exporter/markdown.py.mdmd.md` to describe Actions summary, motif integration, and LOD-0 rendering
- [ ] T023 Refresh `.github/copilot-instructions.md` to reference new scripts, guardrails, and validation flows
- [ ] T024 [P] Capture repeat-failure telemetry baseline and post-rollout metrics in `AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py` (feeds SC-004)
- [ ] T025 Validate Windows vs POSIX CLI parity via `tests/regression/test_cli_parity.py` using quickstart commands and helper scripts
- [ ] T028 Publish privacy/security audit notes (workspace boundary, consented adapters) in `specs/001-vision-spec/checklists/requirements.md` and archive evidence hashes under `AI-Agent-Workspace/_temp/security`

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1 – Setup**: No dependencies; runs immediately.
2. **Phase 2 – Foundational**: Depends on Phase 1; blocks all user stories until normalized catalog + helpers exist.
3. **Phase 3 – User Story 1 (P1)**: Depends on Phase 2; delivers MVP.
4. **Phase 4 – User Story 2 (P2)**: Depends on Phase 2; may run after or alongside Phase 3 once catalog helpers exist.
5. **Phase 5 – User Story 3 (P3)**: Depends on Phase 2 and on outputs of Phases 3–4 for verification artifacts.
6. **Phase 6 – Polish**: Depends on completion of the user stories it documents.

### User Story Dependencies

- **US1 (P1)**: Depends on normalized catalog access (Phase 2).
- **US2 (P2)**: Depends on normalized catalog access and motif helpers (Phase 2, partial outputs from US1 optional).
- **US3 (P3)**: Depends on ingestion/export artifacts (Phases 2–4) and census tooling readiness.

### Parallel Opportunities

- Setup fixtures (T002, T003) can run parallel after T001.
- Foundational helpers T005–T007 can run in parallel once T004 establishes schema changes.
- Within US1, regression and latency tests (T010, T011) can proceed in parallel after T008/T009 finalize interfaces.
- US2 motif pipeline (T015) can proceed in parallel with formatting updates (T014).
- US3 sandbox automation (T017) and test (T019) can iterate in parallel once the script stub exists.
- Polish tasks T021–T023 can proceed concurrently after their respective features stabilize.

---

## Parallel Execution Examples

### User Story 1

```bash
# After T008 & T009 land, run recall-focused tests in parallel
pytest tests/regression/test_conversation_recall.py
pytest tests/regression/test_recall_latency.py
```

### User Story 2

```bash
# Motif analysis and formatter refinements can advance concurrently
python -m black src/export/patterns.py
python AI-Agent-Workspace/Workspace-Helper-Scripts/seen_before.py --dry-run
```

### User Story 3

```powershell
# Run sandbox automation and validator side by side once scripts exist
python AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py --temp-dir _temp/migrate
python AI-Agent-Workspace/Workspace-Helper-Scripts/validate_census.py --report _temp/census-report.json
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Execute Phase 3 (US1) to deliver TF-IDF recall with latency harness.
3. Validate recall CLI against the fixture catalog before proceeding.

### Incremental Delivery

1. Ship MVP (US1) for immediate recall benefit.
2. Layer UI-faithful exports (US2) to enrich audits and motif insights.
3. Finalize migration readiness (US3) to preserve lessons across workspaces.
4. Close with Polish tasks to synchronize documentation and instructions.

### Linear Execution Strategy

- Advance sequentially through phases: complete Setup → Foundational → US1 → US2 → US3 → Polish.
- Treat each phase as blocking the next; only move forward once checklists and independent tests pass.
- Use parallel opportunity notes above merely as guidance for future scaling—keep current implementation single-threaded for auditability.
