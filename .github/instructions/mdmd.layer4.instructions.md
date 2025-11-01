---
applyTo: ".mdmd/layer-4/**/*.mdmd.md"
---

# Layer 4 MDMD Conventions

- Provide a Metadata section at the top of each file:
  ```markdown
  ## Metadata
  - Layer: 4
  - Implementation ID: IMP-001
  - Code Path: packages/.../file.ts
  - Exports: exportedSymbolName, helper
  ```
- Implementation identifiers follow the IMP-### pattern and should match build outputs when possible.
- Canonical section order:
  1. Heading level 1 title.
  2. Purpose - describe why the implementation exists and which ComponentID it serves.
  3. Public Symbols - introduce the section, then declare each exported symbol as a heading using the format `### exportName` with supporting notes beneath.
  4. Collaborators - note other implementations or services relied upon, using subheadings when enumerating multiple collaborators.
  5. Linked Components - point to the Layer 3 files that consume this implementation and provide heading anchors when listing multiple consumers.
  6. Evidence - list tests, benchmarks, or verification artefacts that prove correctness.
- Optional sections such as Observability, Failure Modes, or Follow-up go after Evidence.
- When referencing code, prefer workspace relative paths so tooling can hop into the source quickly.