# Layer 4 — src/export/cli.py

Implementation
- File: [src/export/cli.py](../../../src/export/cli.py)

What it does
- Renders Copilot chat sessions (from VS Code storage or SQLite) to Markdown that mirrors the chat UI plus compact Actions and motifs.

Why it exists
- **Richer than Copy-All**: VS Code's "Copy All" loses tool call details, status information, and failure context. This preserves them.
- **Auditable tool traces**: Surface which tool calls succeeded/failed/canceled so Copilot can learn from repeated mistakes.
- **Workspace organization**: Groups exports by workspace for multi-project navigation.
- **Within-session motifs**: "Seen before (Nx)" annotations reveal repeated patterns invisible in raw Copy-All.
- **Cross-session recall foundation**: Exports become the corpus for "have I encountered this before?" search tooling.

Public surface
- CLI: python -m export.cli [path?] [--session id | --all] [--output path] [--include-status] [--raw-actions] [--database db] [--workspace-directories] [--lod 0]

- parse_args(argv) -> Namespace: parses flags (now includes --lod for Copy-All style exports).
- collect_candidate_sessions(target: Optional[Path]) -> List[SessionRecord]: scans files (via chat_logs_to_sqlite.gather_input_files), filters, sorts.
- collect_sessions_from_database(db: Path) -> List[SessionRecord]: rebuilds sessions from SQLite `prompts` and `prompt_logs`.
- determine_output_path(base_output, session_id, exporting_multiple, *, workspace_key, group_by_workspace) -> Optional[Path]
- render_session_markdown(session, include_status, include_raw_actions, cross_session_dir, lod_level) -> str: imported from copilot_markdown.
- export_session(markdown, destination)

Inputs
- Either: raw session JSON files (VS Code chatSessions/…) or `--database` pointing at `live_chat.db` created by `catalog.ingest`.
- Optional `--session` to target a specific session; otherwise interactive selection.

Outputs
- Writes Markdown to file (if --output) or stdout; with `--workspace-directories`, groups files under workspace-derived subfolders.

Behavior
- Session reconstruction from DB: joins prompt logs to requests (`reconstruct_requests`) to approximate the original session structure.
- Output selection: single session → file path or stdout; `--all` → per-session files inside `--output` directory.
- Status: When `--include-status`, includes result.errorDetails as “> _Status_: …”.
- Raw mode: When `--raw-actions`, includes verbose JSON payloads within Actions blocks.
- LOD flag: `--lod 0` emits Copy-All style transcripts with fenced/triple-quoted blocks collapsed to `...`.

Edge cases
- Handles missing sessionId by falling back to filename; sorts by last activity.
- Skips invalid/malformed JSON files.

Contracts
- Delegates Markdown shaping to `copilot_markdown.render_session_markdown` to keep CLI thin.
- Normalizes workspace keys from source paths to group outputs.

Related
- Ingestor CLI: `src/catalog/ingest.py` generates the DB used by `--database`.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002, ../../layer-2/requirements.mdmd.md#R006

## Evidence
- 2025-11-04: `python -m export.cli --database .vscode/CopilotChatHistory/copilot_chat_logs.db --session 53b8f248-8887-4c93-9243-7e7f96d26560 --include-status --output AI-Agent-Workspace/_temp/export_scalability/53b8f248_full.md` generated a 157,509-line export with 11 "Exit code" entries and 65 "Actions this turn" markers; metrics logged in `AI-Agent-Workspace/_temp/export_scalability/summary.json` confirm Copy-All parity on a >150k-line session.
- 2025-11-04: `python -m export.cli --database .vscode/CopilotChatHistory/copilot_chat_logs.db --session 53b8f248-8887-4c93-9243-7e7f96d26560 --include-status --lod 0 --output AI-Agent-Workspace/_temp/export_scalability/53b8f248_lod0.md` produced the LOD-0 transcript with 273 collapsed `...` markers plus tool invocation JSON for actionable metadata; `summary.json` captures the delta versus the full export for follow-up on failure-tail presentation.
