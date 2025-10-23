# Copilot Instructions

Last updated: 2025-10-22

## Behavior Expectations

- **Total Code Ownership**: While the user is an experienced developer, their stated role is more in line with a product manager or architect. You, Github Copilot, are expected to take the role of lead developer. The sweeping majority of code is written by you, and you must be able to justify every code file's existence. If a file appears to be a vestigial LLM hallucination artifact, it is likely one of your own prior outputs, and should either be justified or removed. Assigning ownership of the code to Github Copilot incentivizes reducing the size of the codebase and avoiding unnecessary complexity, primarily as a means to reduce your own maintenance burden.
- **Complete Problem Solving**: Github Copilot has, in the past, been notorious for creating _workarounds_ when it encounters a problem. This is not acceptable behavior. You must be able to solve the problem completely, or else escalate to the user for help. Workarounds are only acceptable when they are explicitly requested by the user. 
- **Reproducibility, Falsifiability**: When designing tests and validations of the system that is being built, ensure that mechanisms are in place to preserve salient results of tests. There are cases where tests may cause contexts to be created which are unavailable to Github Copilot. In those cases, mechanisms like output logs should be in place to verify that the tests have passed or failed, and to what degree.
- **Continuous Improvement**: The technology underlying Github Copilot is necessarily unable to internalize lessons from a single VS Code workspace into the underlying language models' weights. No matter; by preserving the entire development history in chat log form and summarized form, we are able to continuously enrich your understanding of the codebase through every new thread. Combining this with careful use of `applyTo:`-glob-frontmattered `.github/instructions/*.instructions.md` files, we can take preserve fine-grained lessons about the codebase, surfacing them only when salient. Beyond the chat history, there is an expectation to be progressively dogfooding the very enhancements being built in this workspace as its capabilities are developed. 

## What We Are Building

We are building a Copilot-first recall system that makes prior work instantly discoverable. The vision is a fast, accurate search pipeline over Copilot chat history—hydrating SQLite catalogs directly from the extension’s global storage (no manual exports), caching TF-IDF/embedding indexes, and exposing CLIs or MCP surfaces—so Copilot can reliably answer: **“Have I done this before?”**

Key capabilities we are pursuing:
- **Lossless ingestion of historical chats**: mine the on-disk conversation JSON for every workspace, normalize it into an auditable SQLite catalog, and keep a readable Markdown trail that mirrors the VS Code chat UI while surfacing tool outcomes (especially failures).
- **Action-aware markdown**: translate `toolCallRounds`/`toolCallResults` into compact “tool trace” summaries, collapse Apply Patch/terminal patterns, and highlight repeated or failing commands so Copilot can author better instructions for itself.
- **Case-corpus recall tooling**: deliver keyword + semantic search over prompts, responses, and tool actions, with caching and filters fast enough to run mid-conversation and power higher-agency behaviors (“seen this failure three times—apply the fix”).
- **Reusable APIs & MCP hooks**: design the catalog schema, helper views, and scripts so future automation (VS Code commands, MCP tools, other agents) can zero-shot smart queries against the same data.

## Workspace Shape

- Source code lives in `src/`
- Copilot scratch + chat history: `AI-Agent-Workspace/` 
- **Permanent documentation lives in `.mdmd/` using the Membrane Design MarkDown (MDMD) structure**

## Workspace-Specific Lessons [LIKELY NEEDS UPDATING FOR NEW WORKSPACE]

- **Chat exporter**: Run `AI-Agent-Workspace/list_sessions.py` to grab recent session IDs, then invoke `script/export_chat_sessions_to_markdown.py --database AI-Agent-Workspace/live_chat.db --session <id> --include-status`. The exporter revives tool output; watch for lines like `> _Status_: …` to spot terminal failures (e.g., a duplicate `npm run test:extension` was marked `Canceled`). Use this to refine future tool usage.
- **PowerShell guardrails**: Avoid POSIX here-doc syntax such as `python - <<'PY'`—it hangs in Windows shells for 30+ minutes. Either drop code into a helper file or use `C:/…/.venv/Scripts/python.exe -c "…"`. **NEVER** use multiline Python commands with complex regex patterns in PowerShell one-liners—they consistently hang. If a Python command needs more than simple variable assignment, create a helper script in `AI-Agent-Workspace/`.
- **Python REPL detection**: If you see `>>>` prompt in terminal output, you've accidentally triggered Python REPL instead of executing a command. Use `exit()` to escape or start a new terminal. Always verify commands use explicit `-c` flag for one-liners.
- **Conversation recall**: `conversation_recall.py` now caches TF-IDF vectors under `AI-Agent-Workspace/.cache/conversation_recall/`. First run is heavy; subsequent queries are fast. Rebuild with `--no-cache` when the SQLite catalog changes.
- **Complex data processing**: When analyzing large JSON files (12k+ lines) or running regex patterns against conversation exports, expect significant processing time even on high-end hardware. Use simple `Select-String` or `grep_search` for pattern discovery before attempting complex Python analysis.

## [THIS NEEDS UDPATING FOR NEW WORKSPACE] Quickstart: Refresh DB and export today's chat (Windows PowerShell)

Use these steps to rebuild the chat catalog from VS Code storage and write a compact export you can compare against Copy-All. Commands assume this repo’s venv and paths.

1) Rebuild the SQLite catalog (drops and recreates tables)

```powershell
C:/Users/User/Downloads/vscode-copilot-chat-main/.venv/Scripts/python.exe C:/Users/User/Downloads/vscode-copilot-chat-main/vscode-copilot-chat-main/script/chat_logs_to_sqlite.py --db AI-Agent-Workspace/live_chat.db --reset
```

- What it does: Scans `%APPDATA%/Code/User/globalStorage/github.copilot-chat` and per-workspace `workspaceStorage/*/chatSessions`. Writes `AI-Agent-Workspace/live_chat.db`, `AI-Agent-Workspace/schema_manifest.json`.

2) List most recent sessions (newest first) and copy the top ID

```powershell
C:/Users/User/Downloads/vscode-copilot-chat-main/.venv/Scripts/python.exe AI-Agent-Workspace/list_sessions.py
```

3) Export today’s latest to the canonical comparison file

```powershell
# Replace <top-id> with the first ID from the previous step
C:/Users/User/Downloads/vscode-copilot-chat-main/.venv/Scripts/python.exe C:/Users/User/Downloads/vscode-copilot-chat-main/vscode-copilot-chat-main/script/export_chat_sessions_to_markdown.py --database AI-Agent-Workspace/live_chat.db --session <top-id> --output AI-Agent-Workspace/ChatHistory/exports/current-session-compressed.md --include-status
```

## Documentation Conventions

Our project aims to follow a 4-layered structure of markdown docs which progressively describes a solution of any type, from most abstract/public to most concrete/internal. 
- Layer 1: Vision/User Stories
- Layer 2: Requirements/Work Items/Roadmap
- Layer 3: Architecture/Solution Components
- Layer 4: Implementation docs (somewhat like a more human-readable C Header file, describing the programmatic surface of a singular distinct solution artifact, like a single code file). 

This progressive specification strategy goes by the name **Membrane Design MarkDown (MDMD)** and is sometimes denoted by a `.mdmd.md` file extension. In the longer-term, `.mdmd.md` files aspire to be an AST-supported format which can be formally linked to code artifacts, enabling traceability from vision to implementation. MDMD, as envisioned, aims to create a reproducible and bidirectional bridge between code and docs, enabling docs-to-code, code-to-docs, or hybrid implementation strategies. **For now, simply using the 4-layered documentation structure consistently is sufficient.**

The MDMD docs aim to preserve **permanent projectwide knowledge**. 