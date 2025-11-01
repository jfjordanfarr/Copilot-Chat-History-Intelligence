"""Shared helpers for Copilot chat export logic."""

from __future__ import annotations

import json
from pathlib import PurePath
from typing import Any, Dict, Iterable, Optional, Set


def format_uri(uri: Dict[str, Any]) -> str:
    for key in ("fsPath", "path", "external"):
        value = uri.get(key)
        if isinstance(value, str) and value:
            return value
    scheme = uri.get("scheme")
    authority = uri.get("authority")
    path = uri.get("path")
    if scheme and path:
        if authority:
            return f"{scheme}://{authority}{path}"
        return f"{scheme}:{path}"
    return json.dumps(uri, ensure_ascii=False)


def extract_fs_path(uri: Dict[str, Any]) -> Optional[str]:
    value = uri.get("fsPath")
    if isinstance(value, str) and value:
        return value
    external = uri.get("external")
    if isinstance(external, str) and external.startswith("file://"):
        return external.replace("file://", "", 1)
    path = uri.get("path")
    if isinstance(path, str) and path:
        return path
    return None


def short_path(path: str) -> str:
    try:
        pure = PurePath(path)
    except ValueError:
        return path
    parts = pure.parts
    if len(parts) <= 4:
        return str(pure)
    return str(PurePath(*parts[-4:]))


def prune_keys(value: Any, keys_to_remove: Iterable[str]) -> Any:
    """Return a deep copy of *value* with matching dict keys removed."""

    key_set: Set[str] = set(keys_to_remove)
    if not key_set:
        return value

    def _prune(candidate: Any) -> Any:
        if isinstance(candidate, dict):
            return {
                key: _prune(child)
                for key, child in candidate.items()
                if key not in key_set
            }
        if isinstance(candidate, list):
            return [_prune(item) for item in candidate]
        return candidate

    return _prune(value)
