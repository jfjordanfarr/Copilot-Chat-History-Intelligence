# Layer 4 — src/export/actions.py

Implementation
- File: [src/export/actions.py](../../../src/export/actions.py)

What it does
- Bridges between raw `metadata.messages[]` and Markdown blocks via pattern matchers.

Why it exists
- **Thin orchestration layer**: Separates filtering/noise-suppression logic from pattern matching.
- **Conversational metadata removal**: Strips auto-approval chatter and other non-salient noise in default mode.
- **Raw mode toggle**: Preserves ability to dump full JSON payloads when debugging exporter itself.

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
