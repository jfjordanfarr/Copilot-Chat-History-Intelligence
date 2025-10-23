# Layer 4 — script/export_chat_sessions_to_markdown.py

Implementation
- File: [vscode-copilot-chat-main/script/export_chat_sessions_to_markdown.py](../../../vscode-copilot-chat-main/script/export_chat_sessions_to_markdown.py)

Purpose
- Render Copilot chat sessions (from VS Code storage or SQLite) to Markdown that mirrors the chat UI plus compact Actions and motifs.

Public surface
- CLI: export_chat_sessions_to_markdown.py [path?] [--session id | --all] [--output path] [--include-status] [--raw-actions] [--database db] [--workspace-directories]

Key functions
- parse_args(argv) -> Namespace: parses flags.
- collect_candidate_sessions(target: Optional[Path]) -> List[SessionRecord]: scans files (via chat_logs_to_sqlite.gather_input_files), filters, sorts.
- collect_sessions_from_database(db: Path) -> List[SessionRecord]: rebuilds sessions from SQLite `prompts` and `prompt_logs`.
- determine_output_path(base_output, session_id, exporting_multiple, *, workspace_key, group_by_workspace) -> Optional[Path]
- render_session_markdown(session, include_status, include_raw_actions) -> str: imported from copilot_markdown.
- export_session(markdown, destination)

Inputs
- Either: raw session JSON files (VS Code chatSessions/…) or `--database` pointing at `live_chat.db` created by `chat_logs_to_sqlite.py`.
- Optional `--session` to target a specific session; otherwise interactive selection.

Outputs
- Writes Markdown to file (if --output) or stdout; with `--workspace-directories`, groups files under workspace-derived subfolders.

Behavior
- Session reconstruction from DB: joins prompt logs to requests (`reconstruct_requests`) to approximate the original session structure.
- Output selection: single session → file path or stdout; `--all` → per-session files inside `--output` directory.
- Status: When `--include-status`, includes result.errorDetails as “> _Status_: …”.
- Raw mode: When `--raw-actions`, includes verbose JSON payloads within Actions blocks.

Edge cases
- Handles missing sessionId by falling back to filename; sorts by last activity.
- Skips invalid/malformed JSON files.

Contracts
- Delegates Markdown shaping to `copilot_markdown.render_session_markdown` to keep CLI thin.
- Normalizes workspace keys from source paths to group outputs.

Related
- Ingestor CLI: `script/chat_logs_to_sqlite.py` generates the DB used by `--database`.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002, ../../layer-2/requirements.mdmd.md#R006
