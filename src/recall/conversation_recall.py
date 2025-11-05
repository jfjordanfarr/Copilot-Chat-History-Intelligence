"""Recall Copilot chat history snippets from the normalized catalog.

This module powers the ``conversation_recall`` CLI. It builds a TF–IDF index
from the normalized SQLite catalog produced by ``catalog.ingest`` and surfaces
snippets enriched with provenance (workspace fingerprint, timestamps, exit
codes, and tool outcomes). Cache artefacts live under
``AI-Agent-Workspace/.cache/conversation_recall`` by default so repeated queries
stay fast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from analysis import similarity_threshold as similarity_threshold_module
from catalog import fetch_tool_results

CATALOG_DB_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"
DEFAULT_CACHE_DIR = Path("AI-Agent-Workspace") / ".cache" / "conversation_recall"
CACHE_VERSION = 2


@dataclass
class Document:
    """Represent a recallable catalog request turn."""

    request_id: str
    session_id: str
    workspace_fingerprint: str
    timestamp_ms: Optional[int]
    agent_id: Optional[str]
    prompt_text: str
    response_text: str
    command_text: Optional[str]
    exit_code: Optional[int]
    tool_summaries: List[str]
    initial_location: Optional[str]
    custom_title: Optional[str]
    text: str

    def timestamp_iso(self) -> Optional[str]:
        if self.timestamp_ms is None:
            return None
        return (
            datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )


def tokenize(text: str) -> Counter:
    """Convert text to a token frequency Counter."""

    if not hasattr(tokenize, "_pattern"):
        tokenize._pattern = __import__("re").compile(r"[\w']+")  # type: ignore[attr-defined]
    pattern = tokenize._pattern  # type: ignore[attr-defined]
    return Counter(pattern.findall(text.lower()))


def build_tfidf_index(documents: List[Document]) -> Tuple[List[Dict[str, float]], List[float], Dict[str, int], int]:
    doc_term_counts: List[Counter] = [tokenize(doc.text) for doc in documents]
    df: defaultdict[str, int] = defaultdict(int)
    for counts in doc_term_counts:
        for term in counts:
            df[term] += 1
    total_docs = len(documents)
    doc_vectors: List[Dict[str, float]] = []
    norms: List[float] = []
    for counts in doc_term_counts:
        vec: Dict[str, float] = {}
        total_terms = sum(counts.values()) or 1
        norm_sq = 0.0
        for term, count in counts.items():
            idf = math.log((total_docs + 1) / (df[term] + 1)) + 1
            weight = (count / total_terms) * idf
            if weight:
                vec[term] = weight
                norm_sq += weight * weight
        doc_vectors.append(vec)
        norms.append(math.sqrt(norm_sq))
    return doc_vectors, norms, df, total_docs


def compute_query_vector(query: str, df: Dict[str, int], total_docs: int) -> Tuple[Dict[str, float], float]:
    counts = tokenize(query)
    total_terms = sum(counts.values()) or 1
    vec: Dict[str, float] = {}
    norm_sq = 0.0
    for term, count in counts.items():
        idf = math.log((total_docs + 1) / (df.get(term, 0) + 1)) + 1
        weight = (count / total_terms) * idf
        vec[term] = weight
        norm_sq += weight * weight
    return vec, math.sqrt(norm_sq)


def cosine_similarity(vec_a: Dict[str, float], norm_a: float, vec_b: Dict[str, float], norm_b: float) -> float:
    if not norm_a or not norm_b:
        return 0.0
    shared = set(vec_a.keys()) & set(vec_b.keys())
    if not shared:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in shared)
    return dot / (norm_a * norm_b)


def search(
    documents: List[Document],
    doc_vectors: List[Dict[str, float]],
    norms: List[float],
    df: Dict[str, int],
    total_docs: int,
    query: str,
    limit: int,
) -> List[Tuple[float, Document]]:
    query_vec, query_norm = compute_query_vector(query, df, total_docs)
    scores: List[Tuple[float, Document]] = []
    for doc, vec, norm in zip(documents, doc_vectors, norms):
        score = cosine_similarity(query_vec, query_norm, vec, norm)
        if score > 0:
            scores.append((score, doc))
    scores.sort(key=lambda item: item[0], reverse=True)
    return scores[:limit]


def compute_workspace_fingerprint(workspace_root: Path) -> str:
    return hashlib.sha1(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:16]


def resolve_workspace_root(db_path: Path, override: Optional[Path]) -> Path:
    if override:
        return override.expanduser().resolve()
    current = db_path.expanduser().resolve()
    parent = current.parent
    if parent.name == "CopilotChatHistory" and parent.parent.name == ".vscode":
        return parent.parent.parent
    return parent


def resolve_cache_dir(db_path: Path, override: Optional[Path], workspace_root: Path) -> Path:
    if override:
        cache_dir = override.expanduser()
    else:
        cache_dir = workspace_root / DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_cache_key(
    db_path: Path,
    agent: Optional[str],
    sessions: Optional[Sequence[str]],
    workspaces: Optional[Sequence[str]],
) -> Tuple[str, float, int, Optional[str], Tuple[str, ...], Tuple[str, ...]]:
    stat = db_path.stat()
    session_tuple: Tuple[str, ...] = tuple(sorted(set(sessions or [])))
    workspace_tuple: Tuple[str, ...] = tuple(sorted(set(workspaces or [])))
    return (
        str(db_path.resolve()),
        stat.st_mtime,
        stat.st_size,
        agent,
        session_tuple,
        workspace_tuple,
    )


def cache_path_for_key(cache_dir: Path, key: Tuple[str, float, int, Optional[str], Tuple[str, ...], Tuple[str, ...]]) -> Path:
    digest_source = json.dumps(
        {
            "db": key[0],
            "mtime": key[1],
            "size": key[2],
            "agent": key[3],
            "sessions": key[4],
            "workspaces": key[5],
            "version": CACHE_VERSION,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:32]
    return cache_dir / f"{digest}.pkl"


def load_cached_payload(path: Path, key: Tuple[str, float, int, Optional[str], Tuple[str, ...], Tuple[str, ...]]):
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
    except (OSError, pickle.PickleError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != CACHE_VERSION:
        return None
    if payload.get("key") != key:
        return None
    return payload


def store_cache(
    path: Path,
    key: Tuple[str, float, int, Optional[str], Tuple[str, ...], Tuple[str, ...]],
    documents: List[Document],
    doc_vectors: List[Dict[str, float]],
    norms: List[float],
    df: Dict[str, int],
    total_docs: int,
) -> None:
    payload = {
        "version": CACHE_VERSION,
        "key": key,
        "documents": documents,
        "doc_vectors": doc_vectors,
        "norms": norms,
        "df": dict(df),
        "total_docs": total_docs,
    }
    try:
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
    except OSError:
        pass


def extract_exit_code(metadata: object) -> Optional[int]:
    if isinstance(metadata, dict):
        for key in ("exitCode", "exit_code", "code"):
            value = metadata.get(key)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    continue
        for nested in metadata.values():
            code = extract_exit_code(nested)
            if code is not None:
                return code
    if isinstance(metadata, list):
        for item in metadata:
            code = extract_exit_code(item)
            if code is not None:
                return code
    return None


def extract_command(metadata: object) -> Optional[str]:
    if isinstance(metadata, dict):
        for key in ("command", "toolCommand", "lastCommand"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for nested in metadata.values():
            command = extract_command(nested)
            if command:
                return command
    if isinstance(metadata, list):
        for item in metadata:
            command = extract_command(item)
            if command:
                return command
    return None


def flatten_payload(payload: object) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (int, float)):
        return str(payload)
    if isinstance(payload, dict):
        fragments: List[str] = []
        for key, value in payload.items():
            if key in {"status", "$mid"}:
                continue
            text = flatten_payload(value)
            if text:
                fragments.append(text)
        return "\n".join(fragments)
    if isinstance(payload, list):
        fragments = [flatten_payload(item) for item in payload]
        return "\n".join(filter(None, fragments))
    return str(payload)


def summarise_tool_row(row: Dict[str, object]) -> Optional[str]:
    kind = str(row.get("tool_kind") or "tool")
    payload_json = row.get("payload_json")
    snippet = ""
    if isinstance(payload_json, str) and payload_json:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            snippet = payload_json
        else:
            snippet = flatten_payload(payload)
    snippet = (snippet or "").replace("\r", " ").replace("\n", " ")
    if len(snippet) > 160:
        snippet = snippet[:157] + "..."
    if snippet:
        return f"{kind}: {snippet}"
    return kind


def compose_document_text(
    prompt_text: str,
    response_text: str,
    command_text: Optional[str],
    exit_code: Optional[int],
    tool_summaries: Iterable[str],
) -> str:
    sections: List[str] = []
    if command_text:
        if exit_code is not None:
            sections.append(f"Command: {command_text} (exit_code={exit_code})")
        else:
            sections.append(f"Command: {command_text}")
    if prompt_text:
        sections.append(f"Prompt: {prompt_text}")
    if response_text:
        sections.append(f"Response: {response_text}")
    for summary in tool_summaries:
        sections.append(f"Tool Output: {summary}")
    return "\n\n".join(sections)


def load_documents(
    db_path: Path,
    *,
    sessions: Optional[Sequence[str]] = None,
    agent: Optional[str] = None,
    workspaces: Optional[Sequence[str]] = None,
) -> List[Document]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        clauses: List[str] = []
        params: List[object] = []
        if sessions:
            unique_sessions = sorted(set(sessions))
            placeholders = ",".join(["?"] * len(unique_sessions))
            clauses.append(f"r.session_id IN ({placeholders})")
            params.extend(unique_sessions)
        if agent:
            clauses.append("r.agent_id = ?")
            params.append(agent)
        if workspaces:
            unique_workspaces = sorted(set(workspaces))
            placeholders = ",".join(["?"] * len(unique_workspaces))
            clauses.append(f"r.workspace_fingerprint IN ({placeholders})")
            params.extend(unique_workspaces)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        rows = conn.execute(
            f"""
            SELECT
                r.request_id,
                r.session_id,
                r.workspace_fingerprint,
                r.timestamp_ms,
                r.prompt_text,
                r.agent_id,
                r.result_metadata_json,
                s.initial_location,
                s.custom_title
            FROM requests r
            JOIN chat_sessions s ON s.session_id = r.session_id
            {where_clause}
            ORDER BY
                CASE WHEN r.timestamp_ms IS NULL THEN 1 ELSE 0 END,
                r.timestamp_ms,
                r.request_id
            """,
            params,
        ).fetchall()
        if not rows:
            return []

        request_ids = [row["request_id"] for row in rows]
        response_map: Dict[str, str] = {}
        if request_ids:
            placeholders = ",".join(["?"] * len(request_ids))
            response_rows = conn.execute(
                f"SELECT request_id, GROUP_CONCAT(value, '\n\n') AS response_text FROM responses "
                f"WHERE request_id IN ({placeholders}) GROUP BY request_id",
                request_ids,
            ).fetchall()
            response_map = {row["request_id"]: row["response_text"] or "" for row in response_rows}

        tool_rows = fetch_tool_results(conn, request_ids=request_ids)
        tool_map: Dict[str, List[str]] = defaultdict(list)
        for tool in tool_rows:
            summary = summarise_tool_row(tool)
            if summary:
                tool_map[tool["request_id"]].append(summary)

        documents: List[Document] = []
        for row in rows:
            metadata: object = {}
            raw_metadata = row["result_metadata_json"]
            if isinstance(raw_metadata, str) and raw_metadata:
                try:
                    metadata = json.loads(raw_metadata)
                except json.JSONDecodeError:
                    metadata = {}
            command_text = extract_command(metadata)
            exit_code = extract_exit_code(metadata)
            response_text = response_map.get(row["request_id"], "") or ""
            tool_summaries = tool_map.get(row["request_id"], [])
            prompt_text = row["prompt_text"] or ""
            text = compose_document_text(prompt_text, response_text, command_text, exit_code, tool_summaries)
            documents.append(
                Document(
                    request_id=row["request_id"],
                    session_id=row["session_id"],
                    workspace_fingerprint=row["workspace_fingerprint"],
                    timestamp_ms=row["timestamp_ms"],
                    agent_id=row["agent_id"],
                    prompt_text=prompt_text,
                    response_text=response_text,
                    command_text=command_text,
                    exit_code=exit_code,
                    tool_summaries=tool_summaries,
                    initial_location=row["initial_location"],
                    custom_title=row["custom_title"],
                    text=text,
                )
            )
        return documents
    finally:
        conn.close()


def query_catalog(
    query: str,
    *,
    db_path: Path,
    limit: int,
    agent: Optional[str] = None,
    sessions: Optional[Sequence[str]] = None,
    workspaces: Optional[Sequence[str]] = None,
    cache_dir: Optional[Path] = None,
    workspace_root: Optional[Path] = None,
    use_cache: bool = True,
) -> Tuple[List[Tuple[float, Document]], float]:
    if not db_path.exists():
        raise FileNotFoundError(f"Catalog not found at {db_path}")

    resolved_workspace = resolve_workspace_root(db_path, workspace_root)
    cache_root = resolve_cache_dir(db_path, cache_dir, resolved_workspace)
    key = compute_cache_key(db_path, agent, sessions, workspaces)
    cache_path = cache_path_for_key(cache_root, key)

    documents: List[Document]
    doc_vectors: List[Dict[str, float]]
    norms: List[float]
    df: Dict[str, int]
    total_docs: int

    payload = None
    if use_cache and cache_path.exists():
        payload = load_cached_payload(cache_path, key)

    if payload:
        documents = payload["documents"]
        doc_vectors = payload["doc_vectors"]
        norms = payload["norms"]
        df = payload["df"]
        total_docs = payload["total_docs"]
    else:
        documents = load_documents(db_path, sessions=sessions, agent=agent, workspaces=workspaces)
        if not documents:
            return [], 0.0
        doc_vectors, norms, df, total_docs = build_tfidf_index(documents)
        if use_cache:
            store_cache(cache_path, key, documents, doc_vectors, norms, df, total_docs)

    started = time.perf_counter()
    results = search(documents, doc_vectors, norms, df, total_docs, query, limit)
    elapsed = time.perf_counter() - started
    return results, elapsed


def format_result(score: float, document: Document, *, threshold: Optional[float] = None) -> str:
    timestamp_text = document.timestamp_iso() or "unknown"
    if threshold is not None:
        relation = "≥" if score >= threshold else "<"
        header = (
            f"score={score:.3f} ({relation} threshold {threshold:.3f}) "
            f"request={document.request_id} "
            f"session={document.session_id or 'unknown'} "
            f"timestamp={timestamp_text} "
            f"fingerprint={document.workspace_fingerprint}"
        )
    else:
        header = (
            f"score={score:.3f} request={document.request_id} "
            f"session={document.session_id or 'unknown'} "
            f"timestamp={timestamp_text} "
            f"fingerprint={document.workspace_fingerprint}"
        )
    lines = [header]
    if document.command_text:
        lines.append(f"  command={document.command_text}")
    if document.exit_code is not None:
        lines.append(f"  exit_code={document.exit_code}")
    if document.tool_summaries:
        lines.append(f"  tools={' | '.join(document.tool_summaries)}")
    snippet = document.text.replace("\n", " ")
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."
    lines.append(f"  {snippet}")
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the Copilot recall catalog for similar cases.")
    parser.add_argument("query", help="What situation are you looking for?")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to return (default: 10).")
    parser.add_argument("--agent", help="Filter by agent identifier (matches requests.agent_id).")
    parser.add_argument(
        "--session",
        action="append",
        help="Restrict search to specific session ids (option may repeat).",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        help="Restrict search to workspace fingerprints (option may repeat).",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace root used to derive cache location and default fingerprint.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=CATALOG_DB_PATH,
        help="Path to the normalized catalog database (default: .vscode/CopilotChatHistory/copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Override the directory used to store cache artefacts.",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable cache usage for this run.")
    parser.add_argument("--print-latency", action="store_true", help="Display query latency once complete.")
    parser.add_argument(
        "--min-score",
        type=float,
        help="Minimum similarity score required for a result to be emitted (0-1). Defaults to the actionable threshold derived from metrics_repeat_failures telemetry.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    db_path: Path = args.db

    if not db_path.exists():
        parser.error(f"Catalog not found at {db_path}")

    if args.min_score is not None:
        min_score = max(0.0, min(1.0, args.min_score))
    else:
        try:
            min_score = similarity_threshold_module.compute_similarity_threshold(db_path).threshold
        except Exception:
            min_score = similarity_threshold_module.FALLBACK_THRESHOLD

    results, elapsed = query_catalog(
        args.query,
        db_path=db_path,
        limit=args.limit,
        agent=args.agent,
        sessions=args.session,
        workspaces=args.workspace,
        cache_dir=args.cache_dir,
        workspace_root=args.workspace_root,
        use_cache=not args.no_cache,
    )

    actionable = [(score, document) for score, document in results if score >= min_score]
    suppressed = len(results) - len(actionable)
    results = actionable

    if not results:
        if suppressed > 0:
            print(
                f"No similar situations found above threshold {min_score:.3f}. "
                f"{suppressed} candidate(s) were below the actionability threshold."
            )
        else:
            print("No similar situations found.")
        return 1

    print(
        f"Actionable results: {len(results)}/{len(results) + suppressed} (min_score={min_score:.3f})"
    )
    print()

    for score, document in results:
        print(format_result(score, document, threshold=min_score))
        print()

    if args.print_latency:
        print(f"query_latency_seconds={elapsed:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
