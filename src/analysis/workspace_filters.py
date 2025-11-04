"""Utilities for resolving workspace fingerprint filters."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Sequence

__all__ = [
    "compute_workspace_fingerprint",
    "normalize_workspace_selector",
    "resolve_workspace_filters",
]


def compute_workspace_fingerprint(workspace_root: Path) -> str:
    """Return the stable fingerprint used to scope catalog records."""

    resolved = workspace_root.expanduser().resolve()
    return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16]


def _is_hex_fingerprint(candidate: str) -> bool:
    return len(candidate) == 16 and all(ch in "0123456789abcdef" for ch in candidate)


def normalize_workspace_selector(value: str, *, base_dir: Path) -> str:
    """Normalise user-provided workspace selectors to fingerprints.

    Selectors may be raw fingerprints, relative paths, or absolute paths. Paths
    are resolved against ``base_dir`` when necessary.
    """

    candidate = value.strip()
    if not candidate:
        raise ValueError("Workspace selector cannot be empty.")

    path_like = Path(candidate)
    if path_like.exists() or any(sep in candidate for sep in ("/", "\\")):
        target = path_like if path_like.is_absolute() else (base_dir / path_like)
        return compute_workspace_fingerprint(target)

    lowered = candidate.lower()
    if _is_hex_fingerprint(lowered):
        return lowered

    raise ValueError(
        f"Unrecognised workspace selector '{value}'. Provide a 16-character fingerprint or a workspace path."
    )


def resolve_workspace_filters(
    *,
    selectors: Optional[Sequence[str]],
    all_workspaces: bool,
    workspace_root: Optional[Path],
    cwd: Optional[Path] = None,
) -> Optional[List[str]]:
    """Resolve CLI flags into a list of workspace fingerprints or ``None``.

    When ``all_workspaces`` is True, ``None`` is returned to indicate no
    filtering. Otherwise the result is a sorted list containing at least one
    fingerprint derived from selectors or the provided workspace root (falling
    back to ``cwd``).
    """

    if all_workspaces:
        return None

    base_dir = (workspace_root or cwd or Path.cwd()).expanduser().resolve()

    if selectors:
        filters = {normalize_workspace_selector(selector, base_dir=base_dir) for selector in selectors}
        return sorted(filters)

    return [compute_workspace_fingerprint(base_dir)]
