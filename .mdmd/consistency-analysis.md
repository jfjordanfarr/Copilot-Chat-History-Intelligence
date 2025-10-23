# MDMD Consistency Analysis (2025-10-22)

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

Identified blind spots / gaps
1) Cross‑session motif counts inline
   - L1/L2 mention “across sessions”; L3 explains motif basics but not cross‑session inline annotations.
   - Action: extend exporter to load session‑external motif index and annotate “Seen across N sessions (M×)”.

2) Sequence motifs (n‑grams)
   - L1/L2 roadmap mentions pairs/triples; L3 lacks concrete design notes.
   - Action: add L3 design for sequence extraction and a small L4 contract (helper module or section in markdown.py).

3) MCP surface
   - L1 roadmap includes MCP; L2/L3 don’t define endpoints or contracts.
   - Action: add L2 interface stub and L3 component notes; optional L4 doc for an MCP adapter.

4) Testing & CI
   - No explicit tests/fixtures for exporter/recall; acceptance checks are manual.
   - Action: add minimal tests (golden export snapshot; TF‑IDF recall sample) and document in L2/L3.

5) Schema/versioning & migrations
   - L2 references manifest but not version bump policies; L3 lacks migration approach.
   - Action: add `schema_version` and a simple migration note; include in manifest and README.

6) Privacy/PII redaction specifics
   - L2 mentions pruning sensitive keys; no concrete list or toggle.
   - Action: add redaction policy and a `--redact` flag; document in L2 and L3.

7) Performance envelopes & big‑O notes
   - L2/NFRs set targets; L3 lacks rough complexity bounds for motif/recall and export passes.
   - Action: add brief performance notes and caps (lines, chars) in L3/L4 with tunables.

8) Portability & shell abstraction
   - Windows‑first guidance exists; cross‑platform pathways not specified.
   - Action: add a note on bash/zsh equivalents and how to detect shell for context lines.

9) Cancellation/timeout semantics
   - Exporter shows canceled requests; behavior for partially produced outputs not formalized.
   - Action: document how cancellations propagate to Actions summaries and motif counts.

10) Catalog filters & scoping
   - Mentioned informally (e.g., “constrain to today”); not surfaced as interfaces.
   - Action: add L2 options and L3 plumbing for scoped ingestion/export (by date/workspace/session).

Next steps
- Update L2 to include MCP interface stub, redaction flag, and scoped ingestion/export.
- Update L3 with cross‑session motif index design, sequence motif extraction, and performance caps.
- Implement exporter changes (cross‑session counts) and add a micro test harness.
