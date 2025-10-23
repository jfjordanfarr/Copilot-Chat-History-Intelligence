# Workplan — Progress Census, Backlog, and Migration Readiness (2025-10-22)

This document organizes current progress against requirements, defines tangible work items with acceptance criteria, and outlines how we’ll migrate this workspace without losing learnings.

## 1) Progress census vs requirements

Status keys: Fulfilled ✓ · Partial △ · Missing ○

- R001 — Catalog ingestion: ✓
  - Done: Auto-scan VS Code storage; normalize to SQLite; helper views; manifest + README; schema version policy with migrations and change log.
  - Gaps: Add scoping filters (by date/workspace/session).

- R002 — Markdown export (UI-parity + signal): ✓/△
  - Done: UI-parity transcript; Actions blocks; per-turn counts; session Actions summary; raw mode; Apply Patch compaction.
  - Gaps: Cross-session motif counts inline; sequence motif n-grams; canceled/terminated markers belong to R003 but surface here.

- R003 — Failure visibility: △
  - Done: Exit code suffix; stderr-first tail with caps + “(truncated)”; interactive/prompt detection.
  - Gaps: Explicit canceled/terminated marker; warning tails when exit=0 but stderr present.

- R004 — Motif detection: △
  - Done: Within-session “Seen before (Nx)”; “Motifs (repeats)” section.
  - Gaps: Cross-session motif counts inline; n-gram sequence motifs (pairs/triples).

- R005 — Recall tooling: ✓/△
  - Done: TF-IDF recall with caching; motif recall CLI; export A/B analyzer.
  - Gaps: MCP endpoints; richer filters/scopes parity with ingestion/export.

- R006 — CLI ergonomics (Windows-first): △
  - Done: PowerShell-safe commands; helper scripts; guidance in instructions.
  - Gaps: Config-based path resolution for portability; simple bootstrap to rehydrate on new machine.

- NFR001 Performance: △ (indexes/cache exist; formal caps/tunables need doc)
- NFR002 Reliability: △ (resilient parsers; needs tests/CI)
- NFR003 Auditability: ✓ (compact, status-aware exports)
- NFR004 Privacy: ○ (redaction policy + toggle not implemented)
- NFR005 Portability: △ (Windows-first done; cross-platform guidance pending)

## 2) Backlog — actionable work items (WIDs)

Each item lists requirement mappings and acceptance criteria.

- W101 — Cross-session motif counts inline (R002, R004)
  - Implement exporter support to load/export a motif index across exports and annotate “Seen across N sessions (M× total)”.
  - Accept: Re-export current session → repeated commands show cross-session counts; compare export shows new annotations.

- W102 — Sequence motif n-grams (R004)
  - Detect frequent 2- and 3-action chains (e.g., Search→Read, Terminal→Terminal) and summarize at session end; optional inline tag “Repeated sequence (K×)”.
  - Accept: Export includes a “Sequence motifs” section with top-N sequences and counts.

- W103 — Canceled/terminated markers (R003)
  - Surface explicit “Canceled”/“Terminated” in Actions blocks when tool/status indicates it; include in per-turn/session summaries.
  - Accept: A known canceled turn renders an inline marker and increments a “Canceled” counter in the Actions summary.

- W104 — Warning tails on success (R003)
  - When exit=0 but stderr has content, render a small “Last stderr lines (warnings)” tail with caps.
  - Accept: Export of a success-with-stderr run shows a warnings tail without implying failure.

- W105 — Scoped ingestion/export flags (R001, R005)
  - Add `--since`, `--until`, `--workspace-key`, and `--session` filters to ingestor/exporter with consistent semantics.
  - Accept: Running with `--since` limits DB rows and export contents; verified via summarize_exports metrics.

✓ W106 — Schema versioning & migrations (R001)
  - Status: Completed 2025-10-22. Implemented catalog version 2 with migrations, manifest/README change log, and prompt `source_kind` classifier.

- W107 — Privacy redaction toggle (NFR004)
  - Add `--redact` flag to exporter; default policy to drop keys like `encrypted` and mask sensitive patterns; document policy.
  - Accept: Export in redact mode omits/obfuscates sensitive fields; policy is testable.

- W108 — MCP endpoints for recall/motifs (R005)
  - Expose `seen_before` and `recall_topk` as MCP tools; document request/response schemas.
  - Accept: From a minimal MCP client, both endpoints return expected payloads for a known query.

- W109 — Minimal tests & CI (NFR001, NFR002)
  - Add unit tests: exporter golden snapshot for a small fixture; recall TF-IDF returns known top result; wire GitHub Actions.
  - Accept: CI passes on PR; local tests green.

- W110 — Cross-platform notes & shell abstraction (NFR005)
  - Add macOS/Linux equivalents for quickstarts; note shell detection in Terminal summaries; doc-only initially.
  - Accept: Docs updated; a Linux quickstart section exists; no Windows-only instructions remain unflagged.

- W111 — Config-based paths for portability (R006)
  - Introduce an optional `AI-Agent-Workspace/recall_config.json` to centralize DB/exports/cache paths; CLIs accept `--config`.
  - Accept: Moving workspace and updating one config key is sufficient to run recall/export.

- W112 — Migration guide & helper checklist (R006, NFR003)
  - Author a precise guide with copy lists and verification steps; include a pre-flight checklist.
  - Accept: Following the guide reproduces exports/recall in a new workspace.

- W113 — Cancellation/timeout semantics doc (R003)
  - Document how canceled/timeout statuses are detected and reflected in counts and motifs.
  - Accept: Architecture doc updated; exporter behavior documented with examples.

Suggested milestone grouping
- M4 Now → Tonight: W101, W103, W112
- M5 Next: W104, W105
- M6 Then: W107, W108, W109, W110, W111, W113

## 3) How we get from here to there (organization of work)

Short sprint (today/tonight)
- Lock migration readiness: finalize MigrationGuide (W112).
- Add canceled marker and cross-session counts to exporter (W103, W101); re-export current session and capture before/after via summarize_exports.

Near term
- Add sequence motifs and warning tails (W102, W104); ship scoped flags (W105).

Foundational
- Schema versioning/migrations, redaction policy, tests/CI, MCP surface (W106–W109).

## 4) Links
- Requirements (with IDs): ./layer-2/requirements.mdmd.md
- Architecture (mapping to RIDs): ./layer-3/architecture.mdmd.md
- Consistency analysis: ./consistency-analysis.md
- User intent census: ./user-intent-census.md
