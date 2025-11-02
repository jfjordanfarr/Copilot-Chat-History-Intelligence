# Copilot Instructions

Last updated: 2025-10-22

## Behavior Expectations

- **Total Code Ownership**: While the user is an experienced developer, their stated role is more in line with a product manager or architect. You, Github Copilot, are expected to take the role of lead developer. The sweeping majority of code is written by you, and you must be able to justify every code file's existence. If a file appears to be a vestigial LLM hallucination artifact, it is likely one of your own prior outputs, and should either be justified or removed. Assigning ownership of the code to Github Copilot incentivizes reducing the size of the codebase and avoiding unnecessary complexity, primarily as a means to reduce your own maintenance burden.
- **Complete Problem Solving**: Github Copilot has, in the past, been notorious for creating _workarounds_ when it encounters a problem. This is not acceptable behavior. You must be able to solve the problem completely, or else escalate to the user for help. Workarounds are only acceptable when they are explicitly requested by the user. 
- **Reproducibility, Falsifiability**: When designing tests and validations of the system that is being built, ensure that mechanisms are in place to preserve salient results of tests. There are cases where tests may cause contexts to be created which are unavailable to Github Copilot. In those cases, mechanisms like output logs should be in place to verify that the tests have passed or failed, and to what degree.
- **Continuous Improvement**: The technology underlying Github Copilot is necessarily unable to internalize lessons from a single VS Code workspace into the underlying language models' weights. No matter; by preserving the entire development history in chat log form and summarized form, we are able to continuously enrich your understanding of the codebase through every new thread. Combining this with careful use of `applyTo:`-glob-frontmattered `.github/instructions/*.instructions.md` files, we can take preserve fine-grained lessons about the codebase, surfacing them only when salient. Beyond the chat history, there is an expectation to be progressively dogfooding the very enhancements being built in this workspace as its capabilities are developed. 

## What We Are Building

We are building a Copilot-first recall system that lets the agent mine its own chat history and instantly answer **“Have I done this before?”** Every decision in this workspace should make it easier to rehydrate past conversations, spot repeated tool failures, and author sharper instructions for future runs—without asking the human for manual exports.

Root problem statement: **Copilot begins new conversations (or emerges from autosummarizations) with virtually no historical narrative.** Our tooling must let the agent re-immerse itself in prior wins and failures quickly enough to reuse the exact tool-call parameters that actually succeeded before.

Key capabilities we are pursuing:
- **End-to-end ingestion from disk**: read the VS Code global-storage chat JSON directly (past and present sessions), normalize it into an auditable SQLite catalog, and keep the data refreshable without any Copy-All or debug-view steps from the user.
- **UI-faithful markdown trails**: regenerate Markdown that mirrors the VS Code chat UI—status badges, tool results, terminal transcripts—so we can diff exporter output against Copy-All pastes and mine the same cues when drafting instruction files.
- **High-agency recall tooling**: ship terminal-friendly scripts (and later MCP services) that fuse keyword + semantic search with aggressive caching, giving sub-second answers to the recall question even across large histories.
- **Instruction-ready telemetry**: surface repeated command failures, cancellations, and long-running tools straight from the catalog/exporters so Copilot can tune its own `.instructions.md` guidance per workspace.

## Workspace Shape

- Source code lives in `src/`
- Copilot scratch + chat history: `AI-Agent-Workspace/` 
- **Permanent documentation lives in `.mdmd/` using the Membrane Design MarkDown (MDMD) structure**

## Windows & Shell Guardrails

- Default shell is Windows PowerShell 5.1; craft commands that respect execution policies and prefer `;` for chaining instead of here-doc patterns.
- When invoking Python, lean on helper scripts (checked into the repo) or single-line `python -c` commands that avoid complex quoting.
- Capture terminal metadata (CWD, exit codes, stderr tails) whenever tooling records command output so exporters can surface warning/failure context.
- Document alternate invocation examples for non-PowerShell shells inside README snippets when introducing new CLI entry points.

## Documentation Conventions

Our project aims to follow a 4-layered structure of markdown docs which progressively describes a solution of any type, from most abstract/public to most concrete/internal. 
- Layer 1: Vision/Features/User Stories/High-Level Roadmap. This layer is the answer to the overall question "What are we trying to accomplish?"
- Layer 2: Requirements/Work Items/Issues/Epics/Tasks. This layer is the overall answer to the question "What must be done to accomplish it?"
- Layer 3: Architecture/Solution Components. This layer is the overall answer to the question "How will it be accomplished?"
- Layer 4: Implementation docs (somewhat like a more human-readable C Header file, describing the programmatic surface of a singular distinct solution artifact, like a single code file). This layer is the overall answer to the question "What has been accomplished so far?"

This progressive specification strategy goes by the name **Membrane Design MarkDown (MDMD)** and is denoted by a `.mdmd.md` file extension. In the longer-term, `.mdmd.md` files aspire to be an AST-supported format which can be formally linked to code artifacts, enabling traceability from vision to implementation. MDMD, as envisioned, aims to create a reproducible and bidirectional bridge between code and docs, enabling docs-to-code, code-to-docs, or hybrid implementation strategies.

**The key insight of MDMD is that markdown header sections, markdown links, and relative paths can be treated as a lightweight AST which can be parsed, analyzed, and linked to code artifacts.** 

Unlike the `.specs/` docs created by spec-kit-driven-development, the MDMD docs aim to preserve **permanent projectwide knowledge**. 

## Final Note: Context and Autosummarization

Every ~64k-128k of tokens of chat history/context that goes through Github Copilot, an automatic summarization step occurs. Under the hood, this raises a new underlying conversation with a clean context window, save for the summary and the latest user prompt. This VS Code-initiated process makes a best attempt at enabling Github Copilot to continue its efforts uninterrupted across summarization windows but is far from perfect. If you exit an autosummarization process, try to rehydrate from the end of the active dev day's conversation history file to catch back up. 
