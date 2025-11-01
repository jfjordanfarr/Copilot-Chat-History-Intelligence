"""Action normalisation utilities for Copilot chat metadata messages."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .patterns import render_message_stream

MetadataMessage = Dict[str, Any]


def render_actions(messages: Iterable[MetadataMessage], include_raw: bool = False) -> List[str]:
    """Render metadata messages into Markdown lines.

    Returns a flat list of Markdown lines suitable for inclusion under a turn.
    """

    sequence: Sequence[MetadataMessage] = [message for message in messages if isinstance(message, dict)]
    if not sequence:
        return []

    if not include_raw:
        # Drop conversational metadata (role-only payloads) so we only surface
        # actual tool/action telemetry in the default rendering.
        filtered = [message for message in sequence if message.get("kind")]
        if not filtered:
            return []
        sequence = filtered

    blocks = render_message_stream(sequence, include_raw)
    lines: List[str] = []
    for block in blocks:
        if lines:
            lines.append("")
        lines.extend(block)
    return lines
