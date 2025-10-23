# Layer 4 — script/chat_logs_to_sqlite.py

Implementation
- File: [vscode-copilot-chat-main/script/chat_logs_to_sqlite.py](../../../vscode-copilot-chat-main/script/chat_logs_to_sqlite.py)

Purpose
- Hydrate a normalized SQLite catalog from Copilot chat logs (VS Code storage or .chatreplay.json) for recall and analysis.

Public surface
- CLI: chat_logs_to_sqlite.py [path?] [--db file] [--output-dir dir] [--reset]

Key functions
- parse_args(argv) -> Namespace: parse flags.
- resolve_paths(args) -> (output_dir: Path, db_path: Path): resolves/pins output locations.
- gather_input_files(target: Optional[Path]) -> List[Path]: scans VS Code global/workspace storage by default or a user-provided target.
- load_prompts(path) -> (prompts: List[dict], metadata: dict): supports chatreplay and VS Code session JSON; annotates source kind.
- ensure_schema(conn): creates tables (prompts, prompt_logs, tool_results, catalog_metadata), views (tool_call_details, prompt_activity), and indexes.
- run_schema_migrations(conn) -> str: detects current schema version and applies forward migrations (v1→v2 adds `source_kind`).
- ingest_prompt(conn, prompt, metadata): writes prompt row + logs + tool parts; backfills `source_kind` when metadata lacked it.
- update_metadata(conn, *, source_files): stores schema_version, generated_at_utc, `schema_migrated_at_utc` (when present), and source_files list.
- write_support_files(output_dir, db_path) -> [manifest_path, readme_path]: writes `schema_manifest.json` + catalog README with sample queries and schema change log.

Inputs
- path: optional file or directory with .chatreplay.json or VS Code chatSessions/*.json
- When omitted, auto-scans default Copilot storage paths on this OS.

Outputs
- SQLite DB (`--db`, default `.vscode/CopilotChatHistory/copilot_chat_logs.db`) plus `schema_manifest.json` and a README alongside it; manifest embeds `schema_history` matching the README change log.

Behavior
- Idempotent imports; re-writes prompt_logs/tool_results for a prompt on re-ingest.
- Implements a readable `summary` per log row and captures `time`.
- Runs migrations (v1→v2) before ingesting prompts, recording migration timestamps in catalog metadata.

Edge cases
- Rejects unrecognized formats; tolerates partial/malformed entries.
- Windows paths handled appropriately; outputs directory created as needed.

Contracts
- Schema revisions use `CATALOG_VERSION`, with forward migrations and change logs emitted to both `schema_manifest.json` and the README.
- Views provide zero-shot-friendly joins for LLM tooling.

Related
- Markdown exporter CLI consumes this DB via `--database`.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R001, ../../layer-2/requirements.mdmd.md#R006
