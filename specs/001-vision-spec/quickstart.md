# Quickstart — Copilot Recall Vision

Use this walkthrough to regenerate the Copilot chat catalog, produce UI-faithful exports, exercise recall queries, and update downstream agent context. Commands assume the repository root as the working directory.

## Prerequisites

- Python 3.13 (project targets 3.9+ portability, but the toolchain runs on the repo’s `.venv`)
- Windows PowerShell 5.1 (default shell) with execution policy that permits local scripts
- Access to VS Code global storage for Copilot chat (`%APPDATA%\Code\User\globalStorage` or platform equivalent)
- Git installed (required by spec-kit helper scripts) and ability to run `pytest` for verification

## 1. Bootstrap the Python environment

### PowerShell (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pytest pytest-cov
```

### POSIX shells (bash/zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pytest pytest-cov
```

> The code currently relies on the Python standard library; installing `pytest` and `pytest-cov` prepares the regression harnesses referenced in `research.md`.

## 2. Rebuild the chat catalog (FR-001, FR-005)

1. Ensure no Python process is holding the existing SQLite file (`.vscode/CopilotChatHistory/copilot_chat_logs.db`).
2. Run ingestion:

   ```powershell
   python -m catalog.ingest --db .vscode/CopilotChatHistory/copilot_chat_logs.db --output-dir .vscode/CopilotChatHistory
   ```

   POSIX equivalent:

   ```bash
   python -m catalog.ingest --db .vscode/CopilotChatHistory/copilot_chat_logs.db --output-dir .vscode/CopilotChatHistory
   ```

3. Verify artifacts:
   - `.vscode/CopilotChatHistory/copilot_chat_logs.db` (SQLite catalog refreshed)
   - `.vscode/CopilotChatHistory/schema_manifest.json` (schema version, source files)
   - `.vscode/CopilotChatHistory/README_CopilotChatHistory.md` (table overviews, sample queries)
4. Capture evidence by noting the ingestion timestamp from `catalog_metadata.generated_at_utc` or the manifest.

## 3. Inspect recent sessions and exports (FR-002, FR-004)

1. List the latest session identifiers:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/list_sessions.py
   ```

2. Render a UI-faithful export for a chosen session:

   ```powershell
    python -m export.cli --database .vscode/CopilotChatHistory/copilot_chat_logs.db --session <session-id> --include-status --output AI-Agent-Workspace/Project-Chat-History/CopyAll-Paste/<session-id>.md
   ```

   - Add `--lod 0` to generate the collapsed LOD-0 transcript under the same workspace directory.
   - Use `--all --output AI-Agent-Workspace/Project-Chat-History/CopyAll-Paste` for full backfills (watch disk usage).
3. Confirm exported Markdown mirrors the VS Code chat UI (Actions, exit codes, warning tails, cancellations) and remains within ±2× the Copy-All length.

## 4. Run recall queries (FR-003)

1. Warm the cache (optional but speeds subsequent searches):

   ```powershell
   python -m recall.conversation_recall "retry pytest after autosummarization" --db .vscode/CopilotChatHistory/copilot_chat_logs.db --limit 5
   ```

   POSIX equivalent uses the same syntax.

2. Inspect output for:
   - `score` (cosine similarity)
   - `session` / `doc` identifiers
   - Tool/status annotations (e.g., exit codes)
3. Cache files land in `AI-Agent-Workspace/.cache/conversation_recall/`. Delete files there to force a rebuild when the catalog changes materially.

## 5. Regression tests and telemetry evidence (SC-001, SC-002)

1. Execute the Python test suite once tests are present:

   ```powershell
   pytest
   ```

   Add `--maxfail=1 --disable-warnings -q` for shorter runs when triaging.
2. When the recall latency harness (`tests/regression/test_recall_latency.py`) lands, ensure it runs as part of CI and archive its timing output in `_temp/` or another ignored directory for audits.

## 6. Update agent context (spec-kit gate)

1. Regenerate agent instructions after plan updates:

   ```powershell
   .\.specify\scripts\powershell\update-agent-context.ps1 -AgentType copilot
   ```

2. POSIX devcontainers run the mirrored script:

   ```bash
   ./.specify/scripts/bash/update-agent-context.sh copilot
   ```

3. Inspect `.github/copilot-instructions.md` to confirm the technology stack, recent changes, and timestamp align with `plan.md`.

## 7. Maintain the user-intent census (FR-005, SC-005)

- Append new directives to `.mdmd/user-intent-census.md` every ≤1200 lines of chat history.
- Link census entries back to requirements in `/.mdmd/layer-2/requirements.mdmd.md` and note the corresponding session IDs for traceability.

## 8. Migration smoke test (FR-006, SC-003)

- Use (or author) `AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py` to clone the repo into a temp directory, rerun ingestion/export, and compare `schema_manifest.json` + export hashes.
- Preserve the script output (`_temp/migrate-log.txt`) as evidence that the migration checklist succeeds without manual edits.

Following these steps ensures the recall toolchain, exports, and governance artifacts stay in sync, satisfying the constitution’s environment-aware and intent-led requirements while unlocking `/speckit.tasks` for implementation planning.
