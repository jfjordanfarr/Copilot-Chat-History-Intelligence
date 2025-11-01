# MDMD Consistency Analysis (2025-10-31)

Purpose
- Place Layer 1–4 docs in joint context, verify cross-layer traceability, and surface blind spots or gaps to resolve next.

Scope reviewed
- L1 Vision: .mdmd/layer-1/vision.mdmd.md
- L2 Requirements: .mdmd/layer-2/requirements.mdmd.md
- L3 Architecture: .mdmd/layer-3/architecture.mdmd.md
- L4 Implementation contracts:
  - Exporter: .mdmd/layer-4/exporter/{markdown.py,patterns.py,actions.py,response_parser.py}.mdmd.md
  - CLIs: .mdmd/layer-4/cli/{export_chat_sessions_to_markdown.py,chat_logs_to_sqlite.py}.mdmd.md
  - Recall: .mdmd/layer-4/recall/{conversation_recall.py,seen_before.py,summarize_exports.py}.mdmd.md

Cross‑layer map (samples)
- L1 “Failure visibility” → L2 §3 (Failure visibility) → L3 `patterns.py` (Terminal formatter) → L4 patterns.py.mdmd.md (stderr‑first tails, truncation, interactive)
- L1 “Motifs/Seen before” → L2 §4 (Motif detection) → L3 `markdown.py` (annotations) & recall tools → L4 markdown.py.mdmd.md + seen_before.py.mdmd.md
- L1 “Zero‑manual ingestion” → L2 §1 (Catalog ingestion) → L3 `chat_logs_to_sqlite.py` → L4 chat_logs_to_sqlite.py.mdmd.md
- L1 “UI‑parity Markdown” → L2 §2 (Markdown export) → L3 exporter pipeline → L4 actions.py/markdown.py/patterns.py
- L1 “Recall mid‑conversation” → L2 §5 (Recall tooling) → L3 TF‑IDF cache → L4 conversation_recall.py.mdmd.md

Findings: consistency
- Vision ↔ Requirements: aligned; all L1 themes have explicit L2 requirements and acceptance checks.
- Requirements ↔ Architecture: components cover all FRs/NFRs with clear data flows and registries.
- Architecture ↔ Implementation: Layer 4 docs exist for each named component; inputs/outputs and edge cases are captured.

Identified blind spots / gaps (post-2025-10-31 updates)
1) LOD pipeline documentation
   - LOD-0 export now exists in code + L4 doc (Copy-All style with `...` fences). Higher-level summary specs still TBD.
   - Action: Define LOD-1/2 contracts (inputs/outputs) once we know the summarisation layers beyond LOD-0.

2) MCP surface details
   - L1/L2/L3 now mention MCP placeholders; no interface schema yet.
   - Action: draft request/response examples and plan tests (future doc or prototype).

3) Testing & CI
   - Still missing automated coverage; requirements refer to future work.
   - Action: add minimal tests and CI entry.

4) Privacy redaction implementation
   - Requirements call for configurable redaction; code still default-prunes only.
   - Action: implement `--redact` path and document behavior.

5) Performance envelopes & tunables
   - Requirements note caps; architecture lacks concrete defaults.
   - Action: specify recommended line/char caps and knob locations (doc + code).

6) Portability guidance
   - Requirements mention shell differences; docs/code need usage notes.
   - Action: add quickstart appendix or inline doc updates.

7) Catalog scoping & config
   - Requirements mention config and scoped ingestion/export; code partly implements CLI flags, config pending.
   - Action: land shared config + doc.

Next steps
- Capture L4 hooks for LOD summaries.
- Prototype MCP stubs and document payloads.
- Prioritize tests/CI, redaction toggle, config portability work.
