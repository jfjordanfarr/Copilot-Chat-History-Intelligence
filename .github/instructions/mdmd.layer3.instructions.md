---
applyTo: ".mdmd/layer-3/**/*.mdmd.md"
---

# Layer 3 MDMD Conventions

- Begin with a Metadata section that lists the layer number and component identifiers, for example:
  ```markdown
  ## Metadata
  - Layer: 3
  - Component IDs: COMP-001, COMP-002
  ```
- Component identifiers follow the COMP-### pattern.
- Canonical section order:
  1. Heading level 1 title.
  2. Components - introduce the section briefly, then create one heading per component using the format `### COMP-### – Name` with purpose statements and the RequirementID it supports.
  3. Responsibilities - describe the guarantees each component must uphold; use subheadings when documenting distinct responsibility groups.
  4. Interfaces - document primary inputs, outputs, and integration points, giving each interface a heading if multiple exist.
  5. Linked Implementations - reference Layer 4 documents or code paths per component; use headings to enumerate implementations when more than one exists.
  6. Evidence - telemetry dashboards, runbooks, or tests that prove the architecture behaves as promised.
- Optional supporting sections such as Operational Notes, Failure Modes, or Open Questions come after Evidence.
- Keep terminology aligned with Layer 2 requirement wording so symbol correctness can resolve traceability.