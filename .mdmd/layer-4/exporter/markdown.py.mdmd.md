# Layer 4 — script/copilot_markdown/markdown.py

Implementation
- File: [vscode-copilot-chat-main/script/copilot_markdown/markdown.py](../../../vscode-copilot-chat-main/script/copilot_markdown/markdown.py)

Purpose
- Build the transcript: USER/Copilot text, Actions, per‑turn counts, session Actions summary, Motifs (repeats).

Public surface
- render_session_markdown(session: dict, *, include_status: bool, include_raw_actions: bool = False) -> str

Key helpers (select)
- render_turn(request, *, include_status, include_raw_actions, _seen_state)
- render_actions(metadata.messages, include_raw)
- render_message_text, render_response_content, render_tool_invocations, render_followups
- _normalize_for_fingerprint(text) -> str; _segment_action_blocks(lines) -> List[(start,end)]
- _annotate_seen(lines, seen_map) → appends “— Seen before (Nx)” to block title lines
- ms_to_iso(timestamp_ms) → ISO8601 UTC string

Inputs
- session: { sessionId, creationDate, lastMessageDate, requests[] }
- requests[]: { message, timestamp, contentReferences, response, result:{ metadata:{ messages[] } }, followups }

Outputs
- Markdown string with:
  - Header (session meta)
  - Per‑turn sections with USER, Copilot, optional thinking, Actions block, tool invocations, status
  - Per‑turn “Actions this turn” summary (counts by title)
  - Session‑level “Actions summary” and “Motifs (repeats)” (when not include_raw_actions)

Behavior
- Injects actions into a request via response_parser when sessions serialize tool JSON in response text (not metadata).
- Builds compact Actions using actions.render_actions, then computes:
  - Per‑turn counts via block titles
  - A session‑level aggregation of action titles
  - Motif detection via fingerprint of block text (normalized: lowercase; mask paths/URIs/UUIDs; collapse numbers; whitespace squeeze)
- Seen‑before: maintains a session‑scoped fingerprint→count; annotates repeats on the first line of each block.
- Status lines: if include_status and result.errorDetails present, appends “> _Status_: …”.

Edge cases
- Missing/empty messages: Actions block omitted gracefully.
- include_raw_actions=True: emits raw JSON payloads within blocks; suppresses summaries/motifs for readability.
- Reference rendering: formats URIs with line ranges, variables with values, and plain labels when available.

Error modes
- Defensive JSON handling; treats unknown response shapes as text (render_response_content) and prunes sensitive keys.

Success criteria
- Text mirrors UI; Actions contain concise blocks; per‑turn counts and session summaries appear when data present; motif annotations applied deterministically.

Links
- Uses: actions.py, response_parser.py, patterns.py, utils.py
- Upstream CLI: script/export_chat_sessions_to_markdown.py

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002, ../../layer-2/requirements.mdmd.md#R004
