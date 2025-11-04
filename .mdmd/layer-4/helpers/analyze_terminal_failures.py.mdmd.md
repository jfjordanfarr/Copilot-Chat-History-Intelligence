# Layer 4 — AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py

Implementation
- File: [AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py](../../../AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py)

What it does
- CLI wrapper around `analysis.terminal_failures` that prints per-command failure statistics and optionally emits JSON reports.
- Supports workspace-scoped filtering so operators can focus on the active repo without contaminating cross-workspace telemetry.

Why it exists
- **Operator visibility**: Quickly surfaces the most failure-prone commands after ingest without digging into raw SQL.
- **SC-004 evidence**: Provides ready-to-archive JSON summaries that slot into repeat-failure telemetry manifests.
- **Complement to measure_repeat_failures.py**: Offers ad-hoc diagnostics while the repeat-failure helper focuses on longitudinal metrics.

Public surface
- CLI: `python AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py [--db path] [--limit N] [--output report.json] [--sample-limit N] [--workspace selector] [--all-workspaces] [--workspace-root path]`

Inputs
- SQLite catalog (defaults to `.vscode/CopilotChatHistory/copilot_chat_logs.db`).
- Optional workspace selectors (paths or fingerprints), limit/sample counts, and JSON output path.

Outputs
- Console summary with overall totals plus a table of the top failing commands.
- Optional JSON payload containing summary stats, command breakdowns, and transcript samples (`--sample-limit`).

Behavior
- Resolves workspace selectors via `analysis.workspace_filters.resolve_workspace_filters`.
- Loads and classifies commands with `analysis.terminal_failures` and prints a formatted table.
- Writes structured JSON when `--output` is provided, including the catalog path and filter context for audits.
- Gracefully reports missing catalogs or SQLite errors via argparse `parser.error` so CI failures are legible.

Edge cases
- Prints “No run_in_terminal telemetry found” and exits 0 when the catalog lacks terminal calls for the selected scope.
- Accepts `--all-workspaces` to bypass filters, but otherwise defaults to the current workspace fingerprint.

Related
- Analysis module: [src/analysis/terminal_failures.py](../analysis/terminal_failures.py.mdmd.md)
- Workspace filtering utility: [src/analysis/workspace_filters.py](../analysis/workspace_filters.py.mdmd.md)
- Repeat-failure integration: `AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py`
