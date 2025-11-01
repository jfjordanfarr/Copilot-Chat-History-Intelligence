# Layer 4 — src/export/utils.py

Implementation
- File: [src/export/utils.py](../../../src/export/utils.py)

What it does
- Provides shared helper functions for URI formatting, path extraction, path shortening, and key pruning.

Why it exists
- **DRY principle**: Centralizes common transformations used across export modules.
- **URI normalization**: Handles VS Code's multiple URI representations (fsPath, external, scheme+path) consistently.
- **Readability**: Shortens long paths to ≤4 segments for compact markdown output.
- **JSON cleaning**: Removes sensitive/noisy keys from nested structures before embedding in exports.

Public surface
- format_uri(uri: Dict[str, Any]) -> str
- extract_fs_path(uri: Dict[str, Any]) -> Optional[str]
- short_path(path: str) -> str
- prune_keys(value: Any, keys_to_remove: Iterable[str]) -> Any

Key functions
- **format_uri**: Normalizes VS Code URI dicts to strings
  - Priority: fsPath → path → external → scheme://authority/path → JSON fallback
  - Returns human-readable string representation for markdown
  
- **extract_fs_path**: Extracts filesystem path from URI dict
  - Checks fsPath, external (file://), and path keys in order
  - Returns None if no valid path found
  
- **short_path**: Truncates long paths to last 4 segments
  - Uses PurePath for cross-platform path handling
  - Full path returned if ≤4 segments
  - Gracefully handles invalid paths (returns original)
  
- **prune_keys**: Deep copies value with specified dict keys removed
  - Recursive traversal of dicts and lists
  - Preserves non-dict/list primitives unchanged
  - Used to strip sensitive keys (encrypted, authentication) from raw payloads

Inputs
- URIs as dicts with scheme/authority/path/fsPath/external keys
- Paths as strings (filesystem or URI-style)
- Arbitrary nested structures for key pruning

Outputs
- Formatted strings for URIs/paths
- Cleaned copies of nested data structures

Behavior
- All functions are pure (no side effects)
- Defensive type checking with fallbacks
- Short paths preserve directory structure context while reducing noise

Edge cases
- format_uri: Missing/empty keys → fallback chain → JSON dump
- extract_fs_path: No recognized path keys → returns None
- short_path: Invalid path string → returns original unchanged
- prune_keys: Empty key set → returns deep copy of original

Contracts
- Does not mutate input values
- Returns stable output for same input (deterministic)

Dependencies
- Standard library only: json, pathlib.PurePath, typing

Used by
- export.patterns (URI/path formatting in action blocks)
- export.markdown (reference rendering, path shortening)
- export.actions (raw payload cleaning via prune_keys)

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002
