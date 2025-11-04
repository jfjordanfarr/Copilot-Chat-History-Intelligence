# Layer 4 — src/analysis/workspace_filters.py

Implementation
- File: [src/analysis/workspace_filters.py](../../../src/analysis/workspace_filters.py)

What it does
- Normalizes CLI workspace selectors into the 16-character fingerprints stored in the Copilot catalog.
- Computes default fingerprints from workspace roots, enabling helper scripts to scope telemetry per repo without manual lookup.

Why it exists
- **Repeatability**: Scripts like `measure_repeat_failures.py` and `analyze_terminal_failures.py` need deterministic workspace scoping across machines.
- **Ergonomics**: Accepts raw fingerprints or filesystem paths so operators can pass whichever identifier they have handy.
- **Safety**: Prevents cross-workspace bleed by defaulting to the current workspace fingerprint when no selectors are provided.

Public surface
- `compute_workspace_fingerprint(workspace_root: Path) -> str`: SHA-1 hash (first 16 hex chars) of the resolved path.
- `normalize_workspace_selector(value: str, *, base_dir: Path) -> str`: Converts paths or fingerprints into canonical 16-char fingerprints; raises on empty or unknown selectors.
- `resolve_workspace_filters(*, selectors=None, all_workspaces, workspace_root=None, cwd=None) -> Optional[List[str]]`: Applies CLI flags to produce either `None` (all workspaces) or an ordered list of fingerprints.

Inputs
- Workspace root paths supplied by CLI flags or implied by the current working directory.
- Optional selectors (fingerprints or paths) and `--all-workspaces` boolean from helper command lines.

Outputs
- List of fingerprints ready for SQL `IN` clauses, or `None` to indicate no filtering.

Behavior
- Resolves relative paths against a caller-supplied base directory to keep unit tests deterministic.
- De-dupes selectors when multiple paths resolve to the same fingerprint.
- Validates selector shape (16 lowercase hex) before accepting raw fingerprints.

Edge cases
- Raises `ValueError` for empty selectors or strings that are neither valid paths nor hex fingerprints.
- When no selectors are provided and `--all-workspaces` is absent, defaults to the fingerprint of `workspace_root` (or `cwd`).

Related
- Helper CLI: [AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py](../../../AI-Agent-Workspace/Workspace-Helper-Scripts/analyze_terminal_failures.py)
- Repeat-failure reporter: `AI-Agent-Workspace/Workspace-Helper-Scripts/measure_repeat_failures.py`
