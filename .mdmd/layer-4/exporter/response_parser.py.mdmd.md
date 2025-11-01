# Layer 4 — src/export/response_parser.py

Implementation
- File: [src/export/response_parser.py](../../../src/export/response_parser.py)

What it does
- Hydrates `metadata.messages[]` when tool-call JSON is embedded inside response text rather than provided as structured metadata.

Why it exists
- **Format evolution handling**: VS Code chat storage format changed over time; older sessions embed tool JSON in response text.
- **Backward compatibility**: Enables consistent Actions rendering across all historical sessions regardless of storage format.
- **Noise removal**: Strips embedded JSON from response text after extracting it, improving readability.

Public surface
- inject_actions_into_request(request: dict) -> dict
- normalize_response_with_actions(response: Any) -> (cleaned_response: Any, messages: List[dict])
- extract_json_blocks(text: str) -> List[dict]
- clean_response_text(text: str, json_blocks: List[dict]) -> str

Behavior
- extract_json_blocks: scans text with brace depth tracking, parses JSON candidates, keeps dicts that contain a `kind` field.
- clean_response_text: removes those JSON blocks (indented and inline variants) and discards standalone bold headings that typically wrap tool calls; compacts blank lines.
- normalize_response_with_actions: supports two shapes
  1) response is a list of parts; dict parts with `kind` but not `value` are treated as tool messages; dict parts with `value` are scanned for embedded JSON and then cleaned.
  2) response is a string; scanned for embedded JSON and then cleaned.
- inject_actions_into_request: if `result.metadata.messages` is empty, extracts from `response`, injects messages, and replaces `response` with the cleaned version.

Inputs
- request: Copilot request object `{ response, result:{ metadata:{ messages? } } }`
- response: string or list of dict/parts as seen in VS Code logs

Outputs
- request (possibly copied) with `result.metadata.messages` populated and `response` cleaned for readability.

Edge cases
- No JSON blocks found → return original response; do not mutate request.
- Dict items that contain `value` (text) are preserved; pure tool-call dicts (with `kind` but no `value`) are siphoned into messages.

Contracts
- Does not mutate the original request unless it injects messages; then copies nested dicts.
- Keeps textual content whenever possible to avoid losing user-visible explanations.

Downstream
- Enables export.patterns + export.actions to format Actions blocks even for sessions using newer "JSON-in-text" emission styles.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002
