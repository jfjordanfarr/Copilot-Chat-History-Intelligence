"""Action normalisation utilities for Copilot chat metadata messages."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .patterns import render_message_stream

MetadataMessage = Dict[str, Any]

_TITLE_RE = re.compile(r"^\*\*(?P<title>[^*]+)\*\*")


@dataclass(frozen=True)
class RenderedActions:
    """Structured representation of Actions rendered for a single turn."""

    lines: List[str]
    counts: Mapping[str, int]

    def __bool__(self) -> bool:  # pragma: no cover - trivial proxy
        return bool(self.lines)


def _coalesce_blocks(blocks: Sequence[Sequence[str]]) -> RenderedActions:
    lines: List[str] = []
    counts: Dict[str, int] = {}
    for block in blocks:
        if not block:
            continue
        if lines:
            lines.append("")
        lines.extend(block)
        title_line = block[0]
        match = _TITLE_RE.match(title_line)
        if match:
            title = match.group("title").strip()
            if title:
                counts[title] = counts.get(title, 0) + 1
    return RenderedActions(lines=lines, counts=counts)


def render_actions(messages: Iterable[MetadataMessage], include_raw: bool = False) -> RenderedActions:
    """Render metadata messages into Markdown blocks with summary counts.

    The returned :class:`RenderedActions` exposes the flattened Markdown lines
    along with a count of action titles to support per-turn summaries.
    """

    sequence: Sequence[MetadataMessage] = [message for message in messages if isinstance(message, dict)]
    if not sequence:
        return RenderedActions(lines=[], counts={})

    if not include_raw:
        # Drop conversational metadata (role-only payloads) so we only surface
        # actual tool/action telemetry in the default rendering.
        filtered = [message for message in sequence if message.get("kind")]
        if not filtered:
            return RenderedActions(lines=[], counts={})
        sequence = filtered

    blocks = render_message_stream(sequence, include_raw)
    return _coalesce_blocks(blocks)
