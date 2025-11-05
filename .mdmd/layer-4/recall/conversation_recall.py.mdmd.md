# Layer 4 — src/recall/conversation_recall.py

## Metadata
- Layer: 4
- Implementation ID: IMP-010
- Code Path: [src/recall/conversation_recall.py](../../../src/recall/conversation_recall.py)
- Exports: `main`, `build_argument_parser`, `query_catalog`, `load_documents`, `Document`

## Purpose
- Serve fast, provenance-rich answers to "Have I done this before?" by scanning the normalized catalog with TF-IDF.
- Provide a cache-aware CLI that stays Windows-first while remaining portable to POSIX shells.
- Capture repeat-failure telemetry context (command, exit code, snippets) to reinforce SC-004 remediation work.

## Public Symbols

### main(argv: Optional[Sequence[str]] = None) -> int
- Entry point for `python -m recall.conversation_recall` and helper scripts.
- Validates catalog presence, dispatches `query_catalog`, formats results, and optionally prints latency via `--print-latency`.
- Honors cache toggles (`--cache-dir`, `--no-cache`) and filters (`--agent`, `--session`, `--workspace`).

### build_argument_parser() -> argparse.ArgumentParser
- Defines CLI arguments shared across Windows and POSIX docs, ensuring PowerShell-friendly defaults.
- Keeps the help text synchronized with quickstart commands and regression parity tests.

### query_catalog(query, *, db_path, limit, agent=None, sessions=None, workspaces=None, cache_dir=None, workspace_root=None, use_cache=True) -> Tuple[List[Tuple[float, Document]], float]
- Loads (or reuses cached) TF-IDF vectors, executes cosine similarity search, and returns scored documents plus latency.
- Computes cache keys from catalog path, mtime, size, and filters so sandbox migrations produce distinct cache entries.

### load_documents(db_path, *, sessions=None, agent=None, workspaces=None) -> List[Document]
- Hydrates `Document` dataclasses from catalog rows while enriching tool outcomes via `catalog.fetch_tool_results`.
- Normalizes command text, exit codes, prompts, responses, and tool snippets into a search-ready string.

### Document
- Dataclass capturing request/session metadata, workspace fingerprint, cached timestamp, tool summaries, and formatted text for indexing.

## Collaborators
- [catalog.fetch_tool_results](../../../src/catalog/__init__.py) — collects per-request tool metadata for enrichment.
- [tests/regression/test_conversation_recall.py](../../../tests/regression/test_conversation_recall.py) — guards recall accuracy.
- [tests/regression/test_recall_latency.py](../../../tests/regression/test_recall_latency.py) — enforces latency budget and cache behavior.
- [AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py](../../../AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py) — exercises recall inside migration sandboxes and records telemetry in summaries.

## Linked Components
- [Layer 3 — Architecture & Solution Components](../../layer-3/architecture.mdmd.md#key-components) (see “Recall & analysis”).
- [Layer 2 — Requirements](../../layer-2/requirements.mdmd.md#r005--recall-tooling).

## Evidence
- Regression: [tests/regression/test_conversation_recall.py](../../../tests/regression/test_conversation_recall.py).
- Latency harness: [tests/regression/test_recall_latency.py](../../../tests/regression/test_recall_latency.py).
- Migration parity: [tests/regression/test_migration_sandbox.py](../../../tests/regression/test_migration_sandbox.py) (recall invoked during sandbox dry runs).
- CLI parity: [tests/regression/test_cli_parity.py](../../../tests/regression/test_cli_parity.py) validates Windows/POSIX help entry consistency.
- Latency telemetry: [AI-Agent-Workspace/_temp/recall_latency.json](../../../AI-Agent-Workspace/_temp/recall_latency.json) (2025-11-04T21:02Z) captures cold vs warmed cache latencies (~1.20 ms → ~1.05 ms), workspace-filtered results, and zero-return wrong-workspace guardrails for CHK-005/CHK-007 evidence.

## Observability
- Cache directory defaults to `AI-Agent-Workspace/.cache/conversation_recall`; configurable via `--cache-dir` and `--workspace-root` for sandbox runs.
- `--print-latency` surfaces query duration to stdout for SC-001 verification and migration summaries.

## Follow-up
- Future embedding-backed search can reuse `Document` preparation and cache orchestration while swapping vectorization.
