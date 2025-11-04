"""Utilities for flattening Copilot rich-text payloads into plain text.

The Copilot chat service serializes tool results using a nested "node" AST
structure. Each node includes metadata (ctor/type/priority) with textual leaves
stored under ``text`` or ``value`` keys. This module decodes those payloads into
joined strings so downstream catalog consumers can run heuristics, compute
hashes, or feed the transcripts into vector indexes.
"""
from __future__ import annotations

import json
from typing import Any, List, Sequence, Set

__all__ = [
    "extract_text_fragments",
    "flatten_structured_text",
]


def extract_text_fragments(value: Any) -> List[str]:
    """Return ordered text fragments extracted from a structured payload.

    The function walks strings, mappings, and sequences that follow the Copilot
    rich-text schema. When it encounters a serialized ``{"node": ...}``
    document, it loads the JSON and extracts the ``text`` leaves while
    preserving order. Primitive strings are normalised to ``"\n"`` newlines but
    otherwise left intact.
    """

    fragments: List[str] = []
    _collect_fragments(value, fragments, set())
    return [_normalise_newlines(fragment) for fragment in fragments if fragment]


def flatten_structured_text(value: Any, *, separator: str = "\n") -> str:
    """Collapse a structured payload into a single plain-text string."""

    fragments = extract_text_fragments(value)
    if not fragments:
        return ""
    combined = separator.join(fragments).strip()
    return combined


def _collect_fragments(value: Any, fragments: List[str], seen: Set[int]) -> None:
    if value is None:
        return

    if isinstance(value, str):
        _collect_from_string(value, fragments, seen)
        return

    # Guard against cyclic references.
    obj_id = id(value)
    if obj_id in seen:
        return
    seen.add(obj_id)

    if isinstance(value, dict):
        _collect_from_mapping(value, fragments, seen)
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _collect_fragments(item, fragments, seen)
        return

    # Fallback: stringify unexpected primitives.
    fragments.append(str(value))


def _collect_from_string(text: str, fragments: List[str], seen: Set[int]) -> None:
    stripped = text.lstrip()
    if stripped.startswith("{") and "\"node\"" in stripped[:80]:
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            fragments.append(text)
            return
        _collect_fragments(parsed, fragments, seen)
        return
    fragments.append(text)


def _collect_from_mapping(payload: dict, fragments: List[str], seen: Set[int]) -> None:
    text_value = payload.get("text")
    if isinstance(text_value, str):
        fragments.append(text_value)

    plain_value = payload.get("plainText")
    if isinstance(plain_value, str):
        fragments.append(plain_value)

    value = payload.get("value")
    if isinstance(value, str):
        _collect_from_string(value, fragments, seen)
    elif value is not None:
        _collect_fragments(value, fragments, seen)

    for key in (
        "content",
        "message",
        "messages",
        "parts",
        "children",
        "node",
        "items",
        "segments",
        "rows",
        "blocks",
        "body",
        "elements",
    ):
        child = payload.get(key)
        if child is not None:
            _collect_fragments(child, fragments, seen)

    # Walk any remaining values to catch nested structures stored under other keys.
    for key, child in payload.items():
        if key in {"text", "plainText", "value"}:
            continue
        if key in {
            "type",
            "ctor",
            "ctorName",
            "priority",
            "props",
            "references",
            "lineBreakBefore",
            "supportHtml",
            "supportThemeIcons",
            "role",
            "kind",
            "language",
        }:
            continue
        _collect_fragments(child, fragments, seen)


def _normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
