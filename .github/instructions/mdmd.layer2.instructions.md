---
applyTo: ".mdmd/layer-2/**/*.mdmd.md"
---

# Layer 2 MDMD Conventions

- Start with a Metadata section capturing the layer number and requirement identifiers, for example:
  ```markdown
  ## Metadata
  - Layer: 2
  - Requirement IDs: REQ-001, REQ-020
  ```
- Requirement identifiers follow the REQ-### pattern and should mirror the names in the Requirements section.
- Canonical section order:
  1. Heading level 1 title.
  2. Requirements - introduce the section briefly, then create one heading per requirement using the format `### REQ-### – Name`; include parent CapabilityIDs in the accompanying prose.
  3. Acceptance Criteria - enumerate the verification signals for each requirement. Inside this section, mirror the requirement headings using `### REQ-### – Acceptance Criteria` so each criterion remains deeplinkable.
  4. Linked Components - reference Layer 3 component documents and relevant ComponentID values.
  5. Linked Implementations - reference Layer 4 documents that satisfy the requirement.
  6. Evidence - commit links, test suites, or work item artefacts that prove completion. List each requirement's evidence under `### REQ-### – Evidence` headings.
- Optional sections such as Scope Notes or Open Issues come after Evidence.
- Always link to downstream files with relative paths so graph tooling can build coverage maps.