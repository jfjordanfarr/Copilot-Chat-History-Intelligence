# Research Findings — Copilot Recall Vision

## Decision: Cross-shell command strategy for ingestion/export/recall
- **Decision**: Standardize on `python -m` invocations plus helper PowerShell (`.ps1`) and POSIX (`.sh`) wrappers so every CLI action has documented commands for PowerShell 5.1 and bash/zsh.
- **Rationale**: Python is already the runtime dependency, and `python -m package.module` avoids platform-specific shebang issues while keeping command syntax nearly identical across shells. Wrapper scripts let us embed execution-policy notes (PowerShell) and environment activation (POSIX devcontainers).
- **Alternatives considered**:
  - Direct `.py` script invocation (e.g., `python src/catalog/ingest.py`): workable but duplicates paths all over documentation and complicates packaging if modules move.
  - Creating a compiled CLI via `pipx` or `shiv`: heavier distribution footprint and unnecessary for a repo-scoped toolkit.

## Decision: Recall latency measurement methodology
- **Decision**: Build a `tests/regression/test_recall_latency.py` harness that warms the TF-IDF cache once, then issues representative queries captured from the user-intent census (terminal failure motifs, migration commands) while logging wall-clock timings.
- **Rationale**: The success criterion (≤2 s) must be validated continuously. Exercising real snippets preserves fidelity and guards against regression when catalog size grows.
- **Alternatives considered**:
  - Synthetic documents: faster to assemble but risk missing schema quirks and motif metadata.
  - Manual timing via ad-hoc scripts: non-repeatable and incompatible with the constitution’s evidence requirements.

## Decision: LOD-0 export implementation pattern
- **Decision**: Layer the existing exporter with a `lod0` renderer that collapses fenced blocks to `...`, reuses the normalized Actions pipeline, and writes outputs under `AI-Agent-Workspace/Project-Chat-History/lod0/` by workspace hash.
- **Rationale**: Reusing the normalized Actions pipeline keeps parity and avoids duplicating motif logic, while output partitioning by workspace hash prevents cross-repo bleed during migration.
- **Alternatives considered**:
  - Writing a separate minimal exporter: risks divergence from UI parity and doubles maintenance.
  - Post-processing Copy-All dumps: fails the Ground-Truth Telemetry principle because it bypasses the normalized catalog.

## Decision: Migration dry-run sandboxing
- **Decision**: Script `AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py` to clone the repo into a temp directory, rerun ingestion and exports, and compare manifests/checksums to the source workspace.
- **Rationale**: Automating the dry-run enforces the migration checklist and produces artifacts (checksums, logs) for checklist evidence, satisfying FR-006/SC-003.
- **Alternatives considered**:
  - Manual copy operations: error-prone and unverifiable.
  - Git submodules or bare clones: add complexity without guaranteeing catalog replication.
