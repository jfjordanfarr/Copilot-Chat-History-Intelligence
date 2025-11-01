# Layer 4 — src/export/patterns.py

Implementation
- File: [src/export/patterns.py](../../../src/export/patterns.py)

What it does
- Collapses low‑level `metadata.messages[]` into compact, UI‑parity action blocks.

Why it exists
- **Compression without loss**: Raw tool call JSON can be 12k+ lines per session; patterns compress to ~10% while preserving key details.
- **Functional pattern matching**: Detects multi-event sequences (Apply Patch = 4 records) and renders as single cohesive block.
- **Failure context preservation**: Terminal failures show stderr tails, exit codes, duration—critical for debugging repeated mistakes.
- **Extensibility**: Pattern registry enables adding new tool call compressors as VS Code APIs evolve.

Public surface
- render_message_stream(messages: Sequence[dict], include_raw: bool) -> List[List[str]]
- match_patterns(messages: Sequence[dict], include_raw: bool) -> PatternMatch

Key types
- RenderedAction { title: str, summary: str, details: [str], raw_payloads: [dict] } → to_markdown(include_raw)
- PatternMatch { length: int, action: RenderedAction }

Supported patterns (window ≤ 4)
- Apply Patch: [prepareToolInvocation(copilot_applyPatch), toolInvocationSerialized, textEditGroup, (undoStop?)]
  - Summary: top files (≤3), “+N more” if needed
  - Details: Files count; Lines +added/‑removed (estimated via edit text and ranges)
  - Raw payloads include undoStop when present
- Terminal: [prepareToolInvocation(run_in_terminal), toolInvocationSerialized]
  - Summary: command (truncated) + status suffix (✓ or “exit N”)
  - Details: invocation message; stderr‑first tail on failure (≤6 lines; ≤700 chars; “(truncated)”); Duration ms; CWD; Shell; interactive hint when 3rd msg indicates elicitation
- Read: [prepareToolInvocation(read_file), toolInvocationSerialized]
  - Summary: short path; Details: line range/offset/limit
- Search: [prepareToolInvocation(grep_search), toolInvocationSerialized]
  - Summary: query (truncated); Details: includePattern; (regex) marker
- Inline reference: [inlineReference]
  - Summary: label — URI[:lines] or JSON fallback; suppress no‑location in non‑raw mode

Noise suppression (default mode)
- Drop standalone undoStop, textEditGroup and codeblockUri singletons; strip stray prepare/toolSerialized not captured by a pattern; suppress thinking/mcpServersStarting.
- include_raw=True disables most suppression and embeds cleaned JSON of raw payloads in fenced blocks.

Inputs
- messages: raw `result.metadata.messages` entries (dicts)
- include_raw: toggles raw payload inclusion and suppression rules

Outputs
- Markdown blocks: [ ["**Title** — Summary", "Detail line", ...], ... ]

Edge cases
- Missing toolSpecificData; unknown kinds → generic Raw <kind> single‑message fallback.
- Apply Patch without edits → not matched; falls back to generic.

Contracts
- Windowed matching (up to 4 events) enables multi‑event motifs; `length` controls stream advancement to avoid duplication.
- Sensitive/noisy keys pruned (`encrypted`, `undoStop`, `codeblockUri`, invocation preambles) when embedding raw payloads.

Notes
- Tail extraction is conservative and resilient to shape drift (dict/list/string); prefers stderr keys, then stdout.
Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R002, ../../layer-2/requirements.mdmd.md#R003
