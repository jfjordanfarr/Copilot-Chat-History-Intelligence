# Layer 4 — script/copilot_markdown/actions.py

Implementation
- File: [vscode-copilot-chat-main/script/copilot_markdown/actions.py](../../../vscode-copilot-chat-main/script/copilot_markdown/actions.py)

Purpose
- Bridge between raw `metadata.messages[]` and Markdown blocks via pattern matchers.

Public surface
- render_actions(messages: Iterable[dict], include_raw: bool=False) -> List[str]

Inputs
- messages: iterable of message dicts (often `result.metadata.messages`)
- include_raw: when true, includes raw payloads in blocks and disables noise suppression

Behavior
- Filters to dict messages; if non‑raw mode, drops entries without a `kind` (pure conversational metadata).
- Calls `patterns.render_message_stream` to obtain a list of block line arrays.
- Flattens blocks into a single list of Markdown lines with blank lines separating blocks.

Outputs
- Flat list of lines suitable for inclusion under an “#### Actions” section in a turn.

Edge cases
- Empty sequences or post‑filtering empties → returns [].

Dependencies
- patterns.py (pattern registry + render stream)

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002
