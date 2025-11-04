# Layer 4 — src/catalog/rich_text.py

## Metadata
- Layer: 4
- Implementation ID: IMP-012
- Code Path: [src/catalog/rich_text.py](../../../src/catalog/rich_text.py)
- Exports: `extract_text_fragments`, `flatten_structured_text`

## Purpose
- Centralise Copilot rich-text flattening so ingest and recall code reuse a single decoder.
- Normalise newline handling and JSON-encoded AST nodes ahead of hashing and redaction.
- Provide future vector search pipelines with ready-to-embed plain text fragments.

## Public Symbols

### extract_text_fragments(value: Any) -> List[str]
- Walks mixed payloads (strings, dicts, sequences) and returns ordered plain-text fragments.
- Detects serialized `{"node": ...}` strings, parses them, and collects nested `text` / `plainText` leaves.
- Guards against cyclic references and converts unexpected primitives via `str()`.

### flatten_structured_text(value: Any, *, separator: str = "\n") -> str
- Joins fragments from `extract_text_fragments` and trims surrounding whitespace.
- Ensures Windows `\r\n` newlines are normalised before hashing or storing in SQLite.
- Allows alternate separators when callers need space- or paragraph-delimited output.

## Collaborators
- [src/catalog/ingest.py](../../../src/catalog/ingest.py) — calls `flatten_structured_text` while populating `tool_output_text` rows.
- [src/catalog/__init__.py](../../../src/catalog/__init__.py) — exposes `fetch_tool_output_text` so downstream tooling can consume the flattened data.

## Linked Components
- [Layer 3 — Architecture](../../layer-3/architecture.mdmd.md#data-pipeline) (data normalization flow).
- [Layer 2 — Requirements](../../layer-2/requirements.mdmd.md#r004--catalog-ingest) tracks ingest obligations for rich tool output capture.

## Evidence
- Unit: [tests/unit/test_catalog_rich_text.py](../../../tests/unit/test_catalog_rich_text.py).
- Unit: [tests/unit/test_catalog_fetch.py](../../../tests/unit/test_catalog_fetch.py).
- Integration: [tests/integration/test_catalog_ingest.py](../../../tests/integration/test_catalog_ingest.py) validates persisted fragments and manifest entries.
