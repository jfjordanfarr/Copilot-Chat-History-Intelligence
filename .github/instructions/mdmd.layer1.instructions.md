---
applyTo: ".mdmd/layer-1/**/*.mdmd.md"
---

# Layer 1 MDMD Conventions

- Begin each file with a Metadata section that records the layer number and capability identifiers, for example:
  ```markdown
  ## Metadata
  - Layer: 1
  - Capability IDs: CAP-001, CAP-002
  ```
- Use CAP-### identifiers; keep the list in Metadata aligned with the Capabilities section.
- Canonical section order after Metadata:
  1. Heading level 1 title.
  2. Capabilities - introduce the section with a short summary, then create one heading per capability using the format `### CAP-### – Name` followed by descriptive prose.
  3. Desired Outcomes - keep outcomes scoped to the capabilities above.
  4. Downstream Requirements - link to Layer 2 docs by RequirementID using the REQ-### format and present each requirement as a heading for easy linking.
  5. Success Signals - measurable indicators or metrics per capability.
  6. Evidence - cite adoption metrics, stakeholder approvals, or other artefacts proving the capability is live.
- Optional supporting sections (Guiding Principles, Scope, Open Questions) follow Evidence.
- Prefer relative links (for example, ../../specs/...) so graph tooling can resolve relationships.