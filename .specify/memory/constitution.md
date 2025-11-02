<!--
Sync Impact Report
Version: 1.1.0 -> 1.2.0
Modified Principles:
- I. Intent-Led Planning
- V. Environment-Aware Operational Safety (wording aligned with multi-shell guidance)
Added Sections: None
Removed Sections: None
Templates requiring updates:
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/tasks-template.md
- ✅ .specify/templates/commands/plan.md
- ✅ .specify/templates/commands/tasks.md
- ✅ .specify/templates/commands/analyze.md
Follow-up TODOs: None
-->

# Copilot-Chat-History-Intelligence Constitution

## Core Principles

### I. Intent-Led Planning
The user-intent census is the authoritative ledger for product scope. Specs, plans,
and tasks MUST remain consistent with census directives and MUST update the census
after every <=1200 lines of new conversation so autosummarization never erases
directives. When a document diverges from or refines prior intent it MUST record
that delta (e.g., via MDMD notes or checklist evidence). Citing census excerpts
(with line references) is strongly encouraged whenever it clarifies scope changes,
but is no longer mandatory if the MDMD layers already provide an explicit link.
MDMD documents MUST remain in lock-step with census updates, linking Layer-1 vision
to Layer-2 requirements and Layer-4 implementation guides.

### II. Ground-Truth Telemetry
All ingestion MUST originate from VS Code's on-disk Copilot storage; manual Copy-All
artifacts are for validation only. Catalog runs MUST regenerate the SQLite database,
`schema_manifest.json`, and README, preserving provenance (workspace fingerprint,
prompt identifiers, timestamps, tool metadata). Ingestion pipelines MUST survive
schema drift by quarantining malformed records without aborting runs.

### III. UI-Faithful Exports and Failure Signals
Markdown exports MUST mirror the VS Code chat UI while staying within twice the
Copy-All length. Every turn MUST surface Actions, status badges, diff counts,
warning/failure tails, cancellations, and workspace filters to prevent cross-repo
bleed. LOD-0 exports MUST collapse fenced payloads to `...` while preserving turn
order and actionable metadata for downstream recall.

### IV. Recall and Similarity Rigor
Recall interfaces MUST answer "Have I done this before?" within two seconds of
catalog warm-up, returning snippets that include tool outcomes, timestamps, and
workspace fingerprints. Similarity detection MUST flag only actionable repeats,
document thresholds, and expose metrics that track repeated tool failures and
similar sequences across sessions.

### V. Environment-Aware Operational Safety
The current workspace runs on Windows with PowerShell 5.1, but the feature set MUST
remain portable. Commands and scripts MUST either be shell-agnostic or provide
documented equivalents for PowerShell and at least one POSIX shell (bash/zsh). When
PowerShell-specific flags are required, the plan MUST explain the rationale and the
fallback for devcontainers or non-Windows hosts. Tool invocations MUST capture CWD,
exit codes, stderr tails, and timing metadata so exporters and recall tooling can
surface failures regardless of environment. Migration guides MUST call out any
environment-specific prerequisites and how to reproduce them elsewhere.

## Operational Constraints

- MDMD documentation MUST remain the permanent knowledge base and retain
  bidirectional links between layers and implementation files.
- The SQLite catalog and support artifacts MUST live under
  `.vscode/CopilotChatHistory/` unless the plan explicitly documents an override.
- Migration checklists MUST ensure catalog, exports, census, and instructions can be
  reconstructed without manual tweaks in a clean workspace.
- Redaction policies MUST prevent sensitive payloads from resurfacing in recall or
  exports; any new data sources MUST include redaction steps before ingestion.
- Plans MUST cite `.github/copilot-instructions.md` when documenting environment
  setup and MUST update that file if the supported shells or platforms change.

## Development Workflow

- Follow the spec-kit sequence: `/speckit.specify` -> `/speckit.plan` ->
  `/speckit.tasks` -> `/speckit.analyze` -> `/speckit.implement`. Advancing to the
  next command without closing findings from the prior phase is prohibited.
- Every requirement in the spec MUST map to at least one plan milestone and one task;
  tasks MUST state file paths and testing obligations derived from recall/export
  success criteria.
- Research, data models, contracts, and quickstart guides produced in `/speckit.plan`
  MUST resolve all "NEEDS CLARIFICATION" markers before tasks are authored.
- Tests and verification scripts MUST capture evidence for checklist items (e.g.,
  recall latency, export parity, migration dry runs) and store artefacts where future
  agents can replay them.

## Governance

- This constitution supersedes conflicting instructions in feature branches; edits to
  specs, plans, or tasks MUST document compliance with the principles above.
- Amendments require updating this document, incrementing the semantic version, and
  recording rationale in a commit message. Minor additions increment MINOR; wording
  clarifications increment PATCH.
- Constitutional compliance MUST be reviewed during `/speckit.analyze` and before
  `/speckit.implement`. Unjustified violations are CRITICAL findings and block
  advancement until resolved.

**Version**: 1.2.0 | **Ratified**: 2025-11-01 | **Last Amended**: 2025-11-01
