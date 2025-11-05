# Layer 4 — src/analysis/terminal_failures.py

Implementation
- File: [src/analysis/terminal_failures.py](../../../src/analysis/terminal_failures.py)

What it does
- Parses `run_in_terminal` tool invocations stored inside the normalized Copilot catalog, reconstructing command transcripts, exit codes, and summary stats.
- Classifies each call as success/failure/unknown and aggregates per-command failure rates to feed telemetry and helper CLIs.

Why it exists
- **SC-004 telemetry feed**: Repeat-failure manifests need structured terminal analytics that work across workspaces.
- **Copy-All blind spot**: The chat UI omits exit codes and long transcripts; this module rebuilds them from catalog tables.
- **Shared analysis layer**: Enables helper scripts (`measure_repeat_failures.py`, `analyze_terminal_failures.py`) and future services to reuse the same normalization logic.

Public surface
- `load_terminal_calls(db_path, *, workspace_fingerprints=None, since_ms=None, limit=None) -> List[TerminalCall]`: Pulls catalog rows, reconstructs transcripts from `tool_output_text`, and returns typed records.
- `classify_terminal_call(TerminalCall) -> str`: Signals `success`, `failure`, or `unknown` based on exit codes, metadata, and transcript heuristics.
- `aggregate_command_stats(calls) -> List[CommandStats]`: Groups calls by normalized command string and counts successes/failures/unknowns.
- `summarise_overall(calls) -> Mapping[str, Any]`: Produces totals and failure-rate aggregates for quick console summaries.
- Dataclasses `TerminalCall` and `CommandStats` so helpers can serialize or display structured payloads.

Inputs
- SQLite catalog produced by `catalog.ingest` with populated `requests` and `tool_output_text` tables.
- Optional workspace fingerprint filters (either direct fingerprints or resolved via `analysis.workspace_filters`).

Outputs
- Python dataclasses and counters summarizing terminal activity.
- Raw transcripts with normalized exit codes suitable for JSON reports or console tables.
- (Planned) Transition lineages that relate terminal calls to subsequent helper or pylance executions for command replacement analytics.

Behavior
- Repairs malformed JSON escape sequences inside `result_metadata_json` blobs before parsing tool call payloads.
- Reassembles terminal transcripts by concatenating ordered fragments captured in `tool_output_text`.
- Extracts exit codes from structured payloads, fallbacks, or textual patterns; flags implicit failures when transcripts mention known error strings.
- Sorts aggregated command stats by failure rate, then failure count, to highlight the noisiest commands first.

Edge cases
- Ignores requests whose metadata cannot be parsed into `toolCallRounds` or `toolCallResults`.
- Handles missing transcripts by falling back to formatted result payloads.
- Returns `unknown` classification when neither exit codes nor keywords indicate outcome, keeping failure-rate math honest.

Next steps
- Extend loaders to emit per-request lineage groupings so downstream analytics can observe “command A → command B” replacements.
- Provide aggregation helpers (e.g., `compute_transition_matrix`, `summarise_command_trends`) that return counts ready for chi-square/trend tests feeding instruction synthesis.

Related
- Helper CLI: [AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py](../../../AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py)
- Repeat-failure reporter: `AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py`

Backlinks
- Requirements: ../../layer-2/requirements.mdmd.md#R003, ../../layer-2/requirements.mdmd.md#R006
- Architecture: ../../layer-3/architecture.mdmd.md
