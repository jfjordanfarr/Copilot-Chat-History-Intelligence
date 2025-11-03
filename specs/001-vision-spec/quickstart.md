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

1. Locate the VS Code telemetry directory. The most recent path lives in `AI-Agent-Workspace/_temp/ingest_audit.json`; alternatively run:<br>`Get-ChildItem "$env:APPDATA/Code/User/workspaceStorage" -Directory | Where-Object { Test-Path "$($_.FullName)/chatSessions" } | Select-Object -First 1 FullName`
2. Run ingestion with a clean reset, pointing at that `chatSessions` directory:

   ```powershell
   python -m catalog.ingest --reset "$env:APPDATA/Code/User/workspaceStorage/<fingerprint>/chatSessions"
   ```

   POSIX equivalent:

   ```bash
   python -m catalog.ingest --reset "$HOME/Library/Application Support/Code/User/workspaceStorage/<fingerprint>/chatSessions"
   ```

   Add `--db` / `--output-dir` overrides when the defaults (`.vscode/CopilotChatHistory`) differ from your workspace layout.
3. Verify artifacts:
   - `.vscode/CopilotChatHistory/copilot_chat_logs.db` (SQLite catalog refreshed)
   - `.vscode/CopilotChatHistory/schema_manifest.json` (schema version, source files)
   - `.vscode/CopilotChatHistory/README_CopilotChatHistory.md` (table overviews, sample queries)
4. Confirm provenance & deduping guarantees:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/check_catalog_provenance.py --limit 5
   ```

   The helper should report matching `total` and `distinct_request_id` counts (currently 536) with zero missing fingerprints/timestamps and empty duplicate lists.
5. Capture evidence by noting the ingestion timestamp from `catalog_metadata.generated_at_utc` or the manifest.

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
3. Capture a repeat-failure baseline immediately after rollout:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py `
          --output AI-Agent-Workspace/_temp/telemetry/$(Get-Date -Format yyyy-MM-dd)_repeat_failures.json `
          --security-report AI-Agent-Workspace/_temp/security/repeat_failures_hashes.json
   ```

   Store the JSON and manifest under version control so SC-004 audits can reproduce the digest.
4. Re-run the measurement seven days later with the baseline to confirm a ≥60% reduction:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py `
          --baseline AI-Agent-Workspace/_temp/telemetry/<baseline-date>_repeat_failures.json `
          --output AI-Agent-Workspace/_temp/telemetry/$(Get-Date -Format yyyy-MM-dd)_repeat_failures.json `
          --security-report AI-Agent-Workspace/_temp/security/repeat_failures_hashes.json
   ```

   Verify the new report’s `summary.total_occurrences` is ≤40% of the baseline value and archive both outputs for the checklist.

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
- Regenerate the validator report after each ingest to prove tail gaps remain within the 1,200-line window:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/validate_census.py `
             --summary AI-Agent-Workspace/_temp/census_validation.json
   ```

   The run completes in under a minute on the current catalog; commit the refreshed JSON so any agent can replay the latest checkpoints inside the 15-minute SLA.

## 8. Migration smoke test (FR-006, SC-003)

- Identify the telemetry source before cloning:

   | Host OS | Workspace-scoped path | Global fallback |
   |---------|-----------------------|-----------------|
   | Windows | `%APPDATA%\Code\User\workspaceStorage\<fingerprint>\chatSessions` | `%APPDATA%\Code\User\globalStorage\github.copilot-chat\chatSessions` |
   | macOS | `~/Library/Application Support/Code/User/workspaceStorage/<fingerprint>/chatSessions` | `~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/chatSessions` |
   | Linux | `~/.config/Code/User/workspaceStorage/<fingerprint>/chatSessions` | `~/.config/Code/User/globalStorage/github.copilot-chat/chatSessions` |

- On Windows, run `Get-ChildItem "$env:APPDATA/Code/User/workspaceStorage" -Directory | where { Test-Path "$($_.FullName)/chatSessions" }` to list recent fingerprints. The sandbox helper reuses the most recent entry from `_temp/ingest_audit.json` and falls back to these locations when `--sessions` is omitted.
- Run `AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py` to clone the repo into a throwaway sandbox, rerun ingestion/export, and snapshot recall metrics:

   ```powershell
   python AI-Agent-Workspace/Workspace-Helper-Scripts/migrate_sandbox.py `
         --sessions "$env:APPDATA/Code/User/workspaceStorage/f8da2cbaae7003e40e01bcd4fe7fb2a6/chatSessions" `
         --sandbox-dir AI-Agent-Workspace/_temp/migration_sandbox `
         --summary AI-Agent-Workspace/_temp/migration_summary.json `
         --repeat-failures-output AI-Agent-Workspace/_temp/repeat_failures.json
   ```

   - Omit `--sessions` to let the helper reuse the most recent ingest audit hint.
   - Provide `--repeat-failures-baseline` when diffing against a prior run; by default the helper reuses the output file if it already exists.
   - Add `--keep` to reuse an existing sandbox between runs (handy when diffing exports).

- Inspect `_temp/migration_summary.json` for the regenerated database path, export listings, recall command, and the repeat-failure entry count; verify `_temp/repeat_failures.json` captured the metrics delta.
- Prune the sandbox when finished (or rely on `migrate_sandbox.py` without `--keep` to reset it automatically) and archive the summary JSON for the migration checklist.
- When cloning to a fresh machine, follow the recovery playbook:
   1. Restore the repo and `.venv`.
   2. Copy the telemetry directory listed above or point `catalog.ingest --path` at a network share.
   3. Run `python -m catalog.ingest --reset`, then rebuild exports with `python -m export.cli --all --include-status`.
   4. Recreate `_temp/census_validation.json` and `repeat_failures_hashes.json` using the commands in steps 7 and 5.
   5. Commit the refreshed Copy-All transcripts and manifests so the migration history stays auditable.
- When returning to the original machine, pull the updated Copy-All and telemetry artefacts, rerun ingestion, and repeat the validator plus telemetry steps to verify the census cadence and repeat-failure deltas remain within spec.

Following these steps ensures the recall toolchain, exports, and governance artifacts stay in sync, satisfying the constitution’s environment-aware and intent-led requirements while unlocking `/speckit.tasks` for implementation planning.
