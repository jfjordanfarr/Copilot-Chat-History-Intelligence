# Copilot Chat History Catalog

This workspace contains the normalized Copilot chat catalog that powers recall and export tooling.

- **Database**: `.vscode/CopilotChatHistory/copilot_chat_logs.db`
- **Schema version**: `3`
- **Workspace fingerprint**: `5a70ddd9b8cd03e5`
- **Raw session JSON**: _not stored by default_; rehydrate via the steps below when needed.

## Source Data
- To keep the repo lean we prune the heavyweight JSON exports. Recreate them on demand:
    - **PowerShell**
        ```powershell
        $src = "$env:APPDATA/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions"
        $dst = "d:/Projects/Copilot-Chat-History-Intelligence/AI-Agent-Workspace/Project-Chat-History/Raw-JSON"
        Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
        New-Item $dst -ItemType Directory | Out-Null
        Copy-Item "$src/*.json" $dst
        ```
    - **bash/zsh**
        ```bash
        src="$HOME/.config/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions"
        dst="$(pwd)/AI-Agent-Workspace/Project-Chat-History/Raw-JSON"
        rm -rf "$dst" && mkdir -p "$dst"
        cp "$src"/*.json "$dst"/
        ```
- Copy-all markdown transcripts for the same sessions live under `Project-Chat-History/CopyAll-Paste/` with matching UUID filenames.
- `AI-Agent-Workspace/_temp/ingest_audit.json` records each refresh (files ingested, row counts, redaction metrics).

## Refresh Workflow
```powershell
$env:PYTHONPATH = "d:/Projects/Copilot-Chat-History-Intelligence/src"
D:/Projects/Copilot-Chat-History-Intelligence/.venv/Scripts/python.exe `
    -m catalog.ingest `
    "C:/Users/User/AppData/Roaming/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions" `
    --reset
```

Outputs:
- Regenerated SQLite catalog + manifest in `.vscode/CopilotChatHistory/`.
- Updated audit log in `AI-Agent-Workspace/_temp/ingest_audit.json`.
- Repeat-failure metrics rolled up in `metrics_repeat_failures`.

## Repeat Failure Reporting
- Use `python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py --output AI-Agent-Workspace/_temp/repeat_failures.json` to snapshot the aggregates.
- The helper now embeds terminal telemetry sourced from `analysis.terminal_failures`: console output prints an overall success/failure summary plus the top failure-prone commands, and JSON/security artifacts include a `terminal_failure_analysis` section with the same breakdown for long-term evidence.
- `--baseline` continues to compute deltas, while the terminal analytics portion always reflects the current catalog scope (workspace filters respected).
- For focused triage, run `python AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py --limit 10 --sample-limit 1` to print the highest-risk commands and optionally capture structured JSON (per-command stats plus transcript samples).

## Migration Sandbox
- To validate a relocation, clone the workspace into a throwaway directory and rerun the toolchain:
    - **PowerShell**
        ```powershell
        python AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py `
            --sessions "$env:APPDATA/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions" `
            --sandbox-dir AI-Agent-Workspace/_temp/migration_sandbox `
            --summary AI-Agent-Workspace/_temp/migration_summary.json
        ```
    - **bash/zsh**
        ```bash
        python AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py \
          --sessions "$HOME/.config/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions" \
          --sandbox-dir AI-Agent-Workspace/_temp/migration_sandbox \
          --summary AI-Agent-Workspace/_temp/migration_summary.json
        ```
- The summary JSON lists the cloned sandbox path, ingestion audit counts, exported Markdown files, and the recall query used for verification.
- Inspect `AI-Agent-Workspace/_temp/migration_exports/` inside the sandbox to diff Markdown outputs against the primary workspace.

## Key Tables
- `chat_sessions`: Session metadata and raw JSON snapshots.
- `requests`: Per-turn prompts, timing, agent, and metadata blobs.
- `request_parts`, `request_variables`, `responses`, `result_messages`, `followups`, `content_references`, `code_citations`, `tool_outputs`: Denormalised child entities matching VS Code session structure.
- `metrics_repeat_failures`: Aggregated non-zero exit codes by command fingerprint (powered by nested tool invocation parsing).

## Quick Queries
```sql
-- Recent sessions
SELECT session_id, last_message_date_ms
FROM chat_sessions
ORDER BY last_message_date_ms DESC
LIMIT 5;

-- Latest failed commands
SELECT command_text, exit_code, occurrence_count, last_seen_ms
FROM metrics_repeat_failures
ORDER BY occurrence_count DESC, last_seen_ms DESC
LIMIT 10;

-- Tool invocations stored alongside requests
SELECT request_id, tool_kind, substr(payload_json, 1, 200) AS payload_snippet
FROM tool_outputs
ORDER BY request_id, output_index
LIMIT 10;
```

## Schema Change Log
- **v3 (2024-11-01)**: Normalised Copilot chat telemetry, added repeat failure metrics, and automated manifest/README regeneration per ingest run.

