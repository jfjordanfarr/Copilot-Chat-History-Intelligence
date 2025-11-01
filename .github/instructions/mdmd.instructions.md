---
applyTo: "**/*.mdmd.md"
---

# Membrane Design MarkDown (MDMD) Instructions

## Documentation Conventions

Our project aims to follow a 4-layered structure of markdown docs which progressively describes a solution of any type, from most abstract/public to most concrete/internal. 
- Layer 1: Vision/Features/User Stories/High-Level Roadmap. This layer is the answer to the overall question "What are we trying to accomplish?"
- Layer 2: Requirements/Work Items/Issues/Epics/Tasks. This layer is the overall answer to the question "What must be done to accomplish it?"
- Layer 3: Architecture/Solution Components. This layer is the overall answer to the question "How will it be accomplished?"
- Layer 4: Implementation docs (somewhat like a more human-readable C Header file, describing the programmatic surface of a singular distinct solution artifact, like a single code file). This layer is the overall answer to the question "What has been accomplished so far?"

This progressive specification strategy goes by the name **Membrane Design MarkDown (MDMD)** and is denoted by a `.mdmd.md` file extension. In the longer-term, `.mdmd.md` files aspire to be an AST-supported format which can be formally linked to code artifacts, enabling traceability from vision to implementation. MDMD, as envisioned, aims to create a reproducible and bidirectional bridge between code and docs, enabling docs-to-code, code-to-docs, or hybrid implementation strategies.

**The key insight of MDMD is that markdown header sections, markdown links, and relative paths can be treated as a lightweight AST which can be parsed, analyzed, and linked to code artifacts.** 

### Key Notes:
- As a rule of thumb, each layer should only link to the layer above below, or to another element in its own layer. A layer 4 MDMD doc should link to one or more layer 3 architecture docs above it, a single implementation (i.e. code) file below it, and potentially other layer 4 docs as needed to describe dependencies/usages. 
- Layer 2 and layer 4 MDMD docs should carry an **Evidence** section which links to other documents or artifacts indicating their completion or correctness. For a layer 4 MDMD doc, this most often takes the form of links to various test files (which, in general, do not themselves require their own MDMD docs if they can be cleanly ascribed to a single implementation file; only test/infra files which other files/tests depend upon should get their own MDMD files). For a layer 2 MDMD doc, this may take the form of git commmit links, links to user acceptance test results, or other artifacts which indicate that the requirements have been met, work item completed, or issue resolved.
- Layer 4 MDMD docs should carry a **Purpose** section which definitively describe **why** a given implementation file exists. _Excess_ code is a liability, not an asset. Every code file must have a clear purpose which justifies its existence. Difficulty in articulating the purpose of a code file is a signal that the code file may be unnecessary or redundant.
- All forms of linking in MDMD files should take the form of standard MarkDown links with absolute paths (i.e. [Copilot Behavior Expectations](/.github/copilot-instructions.md#behavior-expectations)) or relative paths (i.e. [Copilot behavior expectations](../copilot-instructions.md#behavior-expectations)), where relative paths are typically only favored if they substantially reduce the length of the link. This is to allow tooling to easily detect and validate links, and, as our work progresses, build a project-wide knowledge graph of documentation artifacts. Please choose whichever form of linking is most useful for the given context.