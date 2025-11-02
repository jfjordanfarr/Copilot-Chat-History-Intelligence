# Implementation Plan: Copilot Recall Vision

**Branch**: `001-vision-spec` | **Date**: 2025-11-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-vision-spec/spec.md`

## Summary

Implement a Copilot-first recall system that:

1. Ingests VS Code Copilot telemetry directly from on-disk storage into a
   normalized SQLite catalog with provenance.
2. Generates UI-faithful Markdown exports that surface Actions, warnings, motifs,
   and LOD variants while staying within 2× Copy-All length.
3. Answers "Have I done this before?" in ≤2 seconds using TF-IDF recall and
  similarity fingerprints, while preserving migration-readiness and strict
  workspace-scoped privacy controls across environments.

## Technical Context

**Language/Version**: Python 3.13 (`.venv`), committed to backwards compatibility
with Python 3.9+ for portability  
**Primary Dependencies**: Python standard library (`sqlite3`, `json`, `argparse`,
`pathlib`, `math`, `collections`, `textwrap`); `pytest` + `pytest-cov` for tests  
**Storage**: SQLite catalog at `.vscode/CopilotChatHistory/copilot_chat_logs.db`
with companion `schema_manifest.json` and `README_CopilotChatHistory.md`  
**Testing**: `pytest` suites for ingestion/export/recall, golden markdown fixtures,
recall latency harness with cached TF-IDF indices, migration smoke tests, and
module-adjacent unit tests stored alongside source files (e.g., `src/export/tests/`)  
**Target Platform**: Windows 10/PowerShell 5.1 and Ubuntu-based devcontainers
(bash/zsh); CLI wrappers must document both shells per constitution principle V  
**Project Type**: Single-project CLI + library toolkit rooted in `src/` with helper
scripts in `AI-Agent-Workspace/`  
**Performance Goals**: Recall latency ≤2 s post warm-up; exports within 2× Copy-All
size; ingestion idempotent across reruns; exporter resilient to ≥150k-line sessions  
**Constraints**: Shell-agnostic commands (PowerShell + POSIX documented) validated
via CLI parity checks, autosum census checkpoints every ≤1200 lines, redaction of
sensitive payloads, catalog writes confined to the workspace boundary, similarity
thresholds must avoid false positives, manifest regeneration mandated each ingest,
ingest-time population of the `metrics_repeat_failures` table, and telemetry
capture for SC-004 repeat-failure tracking during regression passes. External
network calls are prohibited unless routed through the configured
LLM provider; adapters must present explicit opt-in toggles.  
**Scale/Scope**: Expected 50+ sessions per workspace, hundreds of tool calls per
session, catalog footprint ≤500 MB with ability to migrate between machines

## Constitution Check

- **I. Intent-Led Planning**: Plan, research, and quickstart reference the
  user-intent census and MDMD links; tasks will map requirements to code paths.
- **II. Ground-Truth Telemetry**: Ingestion work relies solely on Copilot storage
  directories and regenerates manifest + README artifacts.
- **III. UI-Faithful Exports and Failure Signals**: Export tasks cover Actions,
  diff counts, warning tails, cancellations, LOD-0 rendering, and motif badges.
- **IV. Recall and Similarity Rigor**: Recall plan enforces TF-IDF caching,
  similarity threshold recording, and regression metrics for repeated failures.
- **V. Environment-Aware Operational Safety**: Quickstart documents PowerShell and
  POSIX command variants; migration guidance surfaces environment prerequisites.

Gate evaluation: All principles satisfied. No waivers required.

## Project Structure

### Documentation (this feature)

```text
specs/001-vision-spec/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── copilot-recall.yaml
└── tasks.md  (generated later by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── catalog/
│   ├── ingest.py
│   ├── __init__.py
│   └── tests/
│       └── test_*.py
├── export/
│   ├── cli.py
│   ├── markdown.py
│   ├── patterns.py
│   ├── response_parser.py
│   ├── utils.py
│   └── tests/
│       └── test_*.py
├── recall/
│   ├── conversation_recall.py
│   ├── seen_before.py
│   ├── summarize_exports.py
│   └── tests/
│       └── test_*.py
└── chat_logs_to_sqlite.py

AI-Agent-Workspace/
├── Workspace-Helper-Scripts/
└── Project-Chat-History/

tests/
├── integration/
└── regression/
```

**Structure Decision**: Retain the single-project Python layout. Unit tests live
adjacent to their modules under `src/**/tests/`, while cross-module integration
and regression suites remain in `tests/`. CLI entry-points stay under `src/` with
PowerShell and POSIX usage documented (and parity-checked) in the quickstart.

## Failure Modes & External Dependencies

- **VS Code storage access**: If `%APPDATA%/Code/User/globalStorage` is missing or
  locked, ingestion must surface a friendly error and direct the user to rerun VS
  Code once; devcontainers should mount the host directory read-only for safety.
- **File permissions**: Catalog writes fail when `.vscode/CopilotChatHistory/`
  is read-only. Plan includes a preflight check to bail out early with guidance.
- **Devcontainer mounts**: Paths differ under `/workspaces/...`; quickstart calls
  out environment variables (`WORKSPACE_ROOT`) to keep scripts portable.
- **Telemetry egress**: No background HTTP calls beyond the configured LLM
  provider. Optional adapters (Agent Lightning, AgentOps) ship disabled; enabling
  them requires an explicit flag plus documentation of what data flows outward.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _None_ | _N/A_ | _N/A_ |
