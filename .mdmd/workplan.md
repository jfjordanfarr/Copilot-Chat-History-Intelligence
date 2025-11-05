# Workplan — Progress Census, Backlog, and Migration Readiness (2025-10-31)

This document organizes current progress against requirements, defines tangible work items with acceptance criteria, and outlines how we’ll migrate this workspace without losing learnings.

## 1) Progress census vs requirements

Status keys: Fulfilled ✓ · Partial △ · Missing ○

- R001 — Catalog ingestion: ✓
  - Done: Auto-scan VS Code storage; normalize to SQLite; helper views; manifest + README; schema version policy with migrations and change log.
  - Gaps: Config-driven path overrides (portability) and friendly CLI scoping UX.

- R002 — Markdown export (UI-parity + signal): ✓
  - Done: UI-parity transcript; Actions blocks; per-turn counts; session Actions + Status summary; raw mode; Apply Patch compaction; cross-session annotations; sequence motifs; scoped export filters.
  - Gaps: LOD summary extraction (headline stats + quick context).

- R003 — Failure & warning visibility: ✓
  - Done: Exit code suffix; stderr-first tail with caps + “(truncated)”; interactive/prompt detection; canceled/terminated markers; warning tails.
  - Gaps: Ensure warning tails are tunable via config.

- R004 — Motif detection & LOD cues: ✓/△
  - Done: Within-session “Seen before (Nx)”; “Motifs (repeats)” section; cross-session annotations; sequence motif n-grams.
  - Gaps: LOD summaries that distill motif/action stats into ultra-compact briefs and a LOD-0 export that mirrors Copy All text with code blocks collapsed to `...`.

- R005 — Recall tooling: ✓/△
  - Done: TF-IDF recall with caching; motif recall CLI; export A/B analyzer; scoped CLI filters.
  - Gaps: MCP endpoints; LOD summary generation; config-based paths.

- R006 — CLI ergonomics (Windows-first, portable): △
  - Done: PowerShell-safe commands; helper scripts; guidance in instructions.
  - Gaps: Config-based path resolution for portability; simple bootstrap to rehydrate on new machine.

- NFR001 Performance: △ (indexes/cache exist; formal caps/tunables need doc)
- NFR002 Reliability: △ (resilient parsers; needs tests/CI)
- NFR003 Auditability: ✓ (compact, status-aware exports)
- NFR004 Privacy: ○ (redaction policy + toggle pending)
- NFR005 Portability: △ (Windows-first done; cross-platform guidance pending)

## 2) Backlog — actionable work items (WIDs)

Each item lists requirement mappings and acceptance criteria.

- W101 — Cross-session motif counts inline (R002, R004) — ✓
  - Implemented annotations and reuse of motif index; re-export confirmed.

- W102 — Sequence motif n-grams (R004) — ✓
  - Implemented bigram/trigram counts surfaced under “Sequence motifs”.

- W103 — Canceled/terminated markers (R003) — ✓
  - Inline markers and session summaries updated.

- W104 — Warning tails on success (R003) — ✓
  - Export now surfaces warning tails; pending tunable caps.

- W105 — Scoped ingestion/export flags (R001, R005) — ✓
  - Export CLI supports `--since/--until/--workspace-key`; ingestion scoping next iteration.

- ✓ W106 — Schema versioning & migrations (R001)
  - Implemented catalog version 2 with migrations, manifest/README change log, and prompt `source_kind` classifier.

- W107 — Privacy redaction toggle (NFR004)
  - Pending implementation.

- W108 — MCP endpoints for recall/motifs (R005)
  - Pending design/prototype.

- W109 — Minimal tests & CI (NFR001, NFR002)
  - Pending.

- W110 — Cross-platform notes & shell abstraction (NFR005)
  - Pending documentation.

- W111 — Config-based paths for portability (R006)
  - Pending implementation.

- ✓ W112 — Migration guide & helper checklist (R006, NFR003)
  - MigrationGuide.md authored; verification steps recorded.

- W113 — Cancellation/timeout semantics doc (R003)
  - Incorporated into updated requirements/architecture; dedicated doc optional.

- W114 — LOD-0 Copy-All surrogate export (R004) — Pending
  - Produce a lowest-detail transcript that preserves message order but replaces the contents of every fenced/quoted code block with `...`.
  - Accept: Running the export with `--lod 0` yields output where each code/terminal block retains its fences and language hints yet contains only `...` markers.

- W115 — Command lineage & transition detector (R009)
  - Stitch terminal calls, pylance snippets, and helper scripts by `request_id`/timestamp; emit lineage records plus daily transition counts under `_temp/transition_metrics/`.
  - Accept: A helper script prints top “A → B” replacements for a chosen date range, demonstrating the drop in inline `python -c` vs helper usage captured this week.

- W116 — Statistical deltas & instruction synthesis (R009)
  - Run chi-square/Fisher and trend tests across daily transition metrics to flag significant shifts; generate templated instruction snippets referencing evidence.
  - Accept: A report file lists statistically significant replacements with suggested `.instructions.md` guidance, and at least one guidance snippet is reviewed for inclusion in `.github/copilot-instructions.md`.

Suggested milestone grouping (post-2025-10-31)
- M4 (Complete): W101, W103, W104, W105, W112
- M5 (Next): W107, W108, W109, W110, W111
- M6 (Then): LOD summaries, MCP endpoint hardening, performance tunables, config rollout, privacy testing.

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
