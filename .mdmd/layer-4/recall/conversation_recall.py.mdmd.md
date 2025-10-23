# Layer 4 — conversation_recall.py

Implementation
- File: [conversation_recall.py](../../../conversation_recall.py)

Purpose
- Fast, local "Have I done this before?" search over the SQLite catalog using TF‑IDF with on‑disk caching.

Public surface
- CLI: conversation_recall.py "<query>" [--limit N] [--agent ID] [--session ID ...] [--db path] [--cache-dir dir] [--no-cache]

Core types
- Document { doc_id, prompt_id, session_id?, agent_id?, label, text, tags }

Key functions
- load_documents(db_path, limit_sessions?, agent_filter?) -> List[Document]
  - Scans prompts; for each response log, builds a "turn" doc (rendered user + summary), per-round docs, and per-tool docs with tool/status tags.
- build_tfidf_index(docs) -> (doc_vectors, norms, df, total_docs): term frequency, IDF, and vector norms.
- search(docs, vectors, norms, df, total_docs, query, limit) -> top matches by cosine similarity.
- Cache helpers: compute_cache_key, cache_directory, cache_path_for_key, load_cached_payload, store_cache.

Inputs
- SQLite DB at `AI-Agent-Workspace/live_chat.db` (default), produced by the ingestor.

Outputs
- Prints sorted matches with score, session id, doc id, tool/status tags when present, and a trimmed snippet.

Behavior
- Tokenizes with a simple word regex; builds normalized vectors; caches the full index under `.cache/conversation_recall/` near the DB (or an override directory).
- Cache key includes DB path, mtime, size, agent filter, and session filters; versioned via CACHE_VERSION.

Edge cases
- Empty catalog or no documents → exits with a message.
- Large catalogs → first run heavy; subsequent runs fast via cache.

Contracts
- Does not mutate the catalog; purely read-only search.

Extensibility
- Can be swapped for or augmented with embeddings later; current shape supports quick local recall.

Backlinks
- Architecture: ../../layer-3/architecture.mdmd.md
- Requirements: ../../layer-2/requirements.mdmd.md#R005
