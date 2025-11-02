# Feature Specification: Copilot Recall Vision

**Feature Branch**: `001-vision-spec`  
**Created**: 2025-11-01  
**Status**: Draft  
**Input**: User description: "Document Copilot-first recall system vision and requirements for spec-kit specify phase"

## Clarifications

### Session 2025-11-01

- Q: Where should repeat-failure telemetry for SC-004 be persisted? → A: Store metrics in a new `metrics_repeat_failures` table inside the catalog SQLite database.
- Q: What defines the baseline for SC-004 repeat-failure reduction? → A: Use the 7-day pre-rollout average captured from cataloged `metrics_repeat_failures` entries.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Rehydrate Context On Demand (Priority: P1)

As the active Copilot agent, I can rehydrate rich context from prior chats—tools, failures, approvals—so I know whether we have “done this before” before attempting a new action.

**Why this priority**: Without fast self-recall the agent keeps repeating mistakes after autosummarization resets; this ability unlocks the entire product vision.

**Independent Test**: Trigger a recall query from the current conversation (using the default catalog path `.vscode/CopilotChatHistory/copilot_chat_logs.db`) and confirm a relevant prior snippet with tool outcome and workspace metadata returns in time to change the next decision.

**Acceptance Scenarios**:

1. **Given** historical chat telemetry in the catalog, **When** the agent queries “Have I done this before?” for a terminal command, **Then** the system returns a prior snippet with exit code, stderr tail, and timestamp within 2 seconds of catalog warm-up.
2. **Given** an autosummarization boundary was crossed, **When** the agent reruns the last query after chunked census updates, **Then** the same snippet remains discoverable with the same provenance details.

---

### User Story 2 - Audit Conversations Via UI-Faithful Exports (Priority: P2)

As a developer auditing the work, I can open a Markdown export that mirrors the VS Code chat UI, including Actions, diff counts, cancellations, and warning tails, so I can trust the agent’s history without touching raw JSON.

**Why this priority**: Stakeholders need a durable, human-readable ledger; it is the anchor for recall tuning, migration, and onboarding future agents.

**Independent Test**: Generate an export for any session and confirm it contains all turn-level status markers and the session summary while staying within ±2× Copy-All length.

**Acceptance Scenarios**:

1. **Given** a catalogued session that includes terminal failures and Apply Patch edits, **When** the export is generated, **Then** the Markdown shows exit codes, capped stderr tails, edit file counts, and “Seen before” annotations inline.
2. **Given** the developer filters exports by workspace hash, **When** they view the session summary, **Then** no foreign workspace content appears and the “Actions + Status” section lists every non-success turn.

---

### User Story 3 - Migrate Without Losing Lessons (Priority: P3)

As the project steward, I can relocate the workspace (or spin up a clean branch) by following the documented migration checklist, knowing that the catalog, exports, and instructions stay intact and the user-intent census still reflects the latest chunks.

**Why this priority**: The spec-kit workflow and future agents depend on a reproducible knowledge base; losing it would erase the cumulative learning we are investing in today.

**Independent Test**: Execute the migration checklist into a sandbox workspace and verify recall queries, exports, and census updates still operate without manual hotfixes.

**Acceptance Scenarios**:

1. **Given** a cloned workspace without historical context, **When** the migration checklist is followed, **Then** the SQLite catalog, exports, and `.mdmd/` docs reproduce with correct paths and version manifests.
2. **Given** the census was updated in 1200-line increments before the move, **When** the new workspace runs the recall scripts, **Then** it surfaces the same “Have I done this before?” answers and points to identical line numbers.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- Autosummarization fires mid-ingestion: chunked census updates must already be persisted so no intent is lost.
- VS Code storage schema drifts or contains partial/corrupt conversations: ingestion must skip or quarantine bad records without crashing.
- Cross-workspace bleed (multiple repos on same machine): exports and recall views must filter by workspace fingerprint to avoid contaminating guidance.
- Extremely large conversations (>150k lines): exporter must degrade gracefully (e.g., collapse sections) while keeping required signals.
- Redacted or sensitive payloads: recall and exports must respect redaction rules so secrets never reappear.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- <a id="fr-001"></a> **FR-001** _(aligns with [R001 – Catalog ingestion](/.mdmd/layer-2/requirements.mdmd.md#r001--catalog-ingestion))_: System MUST automatically ingest Copilot chat telemetry from disk (no manual Copy-All) into a normalized, versioned catalog with provenance for each record, and emit the companion `schema_manifest.json` plus catalog README every run.
- <a id="fr-002"></a> **FR-002** _(aligns with [R002 – Markdown export (UI-parity + signal)](/.mdmd/layer-2/requirements.mdmd.md#r002--markdown-export-ui-parity--signal))_: System MUST generate UI-faithful Markdown exports that include turn-level Actions, diff counts, exit codes, warning tails, cancellations, per-turn "Actions this turn" counters, and session summaries within ±2× the Copy-All length.
- <a id="fr-003"></a> **FR-003** _(aligns with [R005 – Recall tooling](/.mdmd/layer-2/requirements.mdmd.md#r005--recall-tooling))_: System MUST provide a recall interface that answers “Have I done this before?” with a relevant snippet (including tool outcomes and timestamps) in ≤2 seconds after catalog warm-up and surfaces provenance (workspace fingerprint, turn id, timestamps).
- <a id="fr-004"></a> **FR-004** _(aligns with [R004 – Repeat detection & LOD cues](/.mdmd/layer-2/requirements.mdmd.md#r004--repeat-detection--lod-cues))_: System MUST highlight materially similar action sequences within and across sessions with inline annotations only when the similarity threshold indicates actionable repetition, while producing a baseline LOD-0 export variant that collapses fenced payloads and records similarity fingerprints for richer LODs. The similarity threshold MUST be exposed as a configurable parameter (including Copilot tool-call usage), and MUST default to the 90th percentile similarity score observed across the latest seven-day window of `metrics_repeat_failures` telemetry so annotations stay trustworthy without manual recalibration.
- <a id="fr-005"></a> **FR-005** _(aligns with [R007 – Migration readiness & traceability](/.mdmd/layer-2/requirements.mdmd.md#r007--migration-readiness--traceability))_: System MUST maintain a user-intent census with line-referenced quotes, updated at least every 1200 lines of new conversation, linking requirements back to those entries and capturing chunk provenance for post-migration audits.
- <a id="fr-006"></a> **FR-006** _(aligns with [R007 – Migration readiness & traceability](/.mdmd/layer-2/requirements.mdmd.md#r007--migration-readiness--traceability))_: System MUST supply a migration checklist and workplan that reproduce the catalog, exports, instructions, and census in a fresh workspace without manual tweaks, including reverse-migration guidance when lifting artifacts into a clean repo.
- <a id="fr-007"></a> **FR-007** _(aligns with [R006 – CLI ergonomics (Windows-first, portable)](/.mdmd/layer-2/requirements.mdmd.md#r006--cli-ergonomics-windows-first-portable))_: System MUST expose Windows-first, portable CLI entry points (single-command recall/export/migration routines) that avoid PowerShell execution pitfalls, document shell differences, and offer helper script fallbacks for macOS/Linux.
- <a id="fr-008"></a> **FR-008** _(aligns with [R008 – Workspace-scoped privacy & telemetry governance](/.mdmd/layer-2/requirements.mdmd.md#r008--workspace-scoped-privacy--telemetry-governance))_: Catalog storage, exports, and telemetry MUST remain confined to the active workspace boundary, redact secrets by default, and only transmit chat history to the user-configured LLM provider (e.g., GitHub Copilot cloud, Ollama) when explicitly invoked; any optional external adapters MUST ship as opt-in modules with documented consent checkpoints.

### Key Entities *(include if feature involves data)*

- **Chat Session**: Structured record of a Copilot conversation including turns, tool invocations, timestamps, status outcomes, and workspace fingerprint.
- **Conversation Export**: UI-faithful Markdown artifact derived from a session; contains Actions, summaries, similarity annotations, and links back to raw catalog rows.
- **Recall Result**: Aggregated response to a “Have I done this before?” query; includes snippet text, associated actions, session metadata, and similarity score.
- **Intent Census Entry**: Curated quote with line references capturing user directives; maps requirements and work items to authoritative source lines.
- **Migration Checklist**: Ordered steps and verification points ensuring catalog, exports, census, and instructions replicate correctly in a new environment.
- **Security Boundary Policy**: Configuration describing workspace-scoped storage paths, opt-in telemetry adapters, redaction rules, and audit evidence proving no unintended egress occurred during cataloging or recall.
- **Repeat Failure Metric**: Row stored in the catalog's `metrics_repeat_failures` table, aggregating repeated command failures (command text, exit code, count, time window) to power SC-004 telemetry analysis.

### Assumptions & Dependencies

- VS Code continues to persist chat telemetry in accessible JSON files under the global storage path.
- Project workplan (W101–W105 and successors) remains the source of truth for sequencing implementation tasks derived from this vision.
- Privacy redaction policies will be defined alongside future MCP integrations but follow current workspace conventions in the interim.
- External intelligence helpers MUST respect the user's configured provider; no chat history leaves the machine except through that provider's sanctioned endpoint (GitHub Copilot cloud by default, Ollama or other local LLMs when configured).
- Daily development continues to update the user-intent census in ≤1200-line chunks so spec-kit artifacts always point to a fresh vision ledger.
- PowerShell remains the default shell, so helper commands must respect Windows execution policies unless the migration guides indicate otherwise.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: 95% of recall queries return a relevant prior snippet (matching intent and tool outcome) within 2 seconds after the initial catalog warm-up.
- **SC-002**: 100% of generated exports include complete Actions + Status summaries, exit-code annotations, and warning tails for every non-success tool invocation.
- **SC-003**: During migration dry runs, all critical assets (catalog, exports, census, instructions) reconstruct in a fresh workspace with zero manual edits and pass a checksum or line-count verification within 30 minutes.
- **SC-004**: After rolling out the system, repeated tool-failure incidents (same command, same exit code) drop by at least 60% within one week of usage compared to the 7-day pre-rollout average captured from `metrics_repeat_failures`.
- **SC-005**: Autosummarization events never result in more than 1200 lines of uncatalogued intent; census checkpoints always exist for replay within 15 minutes of new directives.
- **SC-006**: 100% of ingestion, export, and recall runs execute without writing outside the workspace boundary or invoking non-consented network calls, confirmed via audit logs and redaction scans.

## Traceability & References

- **Vision**: [Layer 1 — Vision & User Stories](/.mdmd/layer-1/vision.mdmd.md)
- **Requirements Backbone**: [Layer 2 — Requirements & Roadmap](/.mdmd/layer-2/requirements.mdmd.md)
- **Intent Ledger**: [User Intent Census](/.mdmd/user-intent-census.md)
- **Workspace Conventions**: [.github/copilot-instructions.md](/.github/copilot-instructions.md)
