import argparse
import hashlib
import json
import math
import pickle
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DB_PATH = Path('AI-Agent-Workspace/live_chat.db')
TOKEN_RE = re.compile(r"[\w']+")
CACHE_VERSION = 1


@dataclass
class Document:
    doc_id: str
    prompt_id: str
    session_id: Optional[str]
    agent_id: Optional[str]
    label: str
    text: str
    tags: Dict[str, str]


def load_documents(db_path: Path, limit_sessions: Optional[Sequence[str]] = None, agent_filter: Optional[str] = None) -> List[Document]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        docs: List[Document] = []
        for row in conn.execute('SELECT prompt_id, raw_json FROM prompts'):
            prompt_id = row['prompt_id']
            entry = json.loads(row['raw_json'])
            for log_index, log in enumerate(entry.get('logs', [])):
                if log.get('kind') != 'response':
                    continue
                result = log.get('result')
                if not isinstance(result, dict):
                    continue
                metadata = result.get('metadata')
                if not isinstance(metadata, dict):
                    continue
                session_id = metadata.get('sessionId')
                if limit_sessions and session_id not in limit_sessions:
                    continue
                agent_id = metadata.get('agentId')
                if agent_filter and agent_id != agent_filter:
                    continue
                rendered_user = render_segments(metadata.get('renderedUserMessage'))
                summary = metadata.get('summary') if isinstance(metadata.get('summary'), str) else ''
                doc_label = f"prompt:{prompt_id} log:{log_index}"
                base_text = '\n'.join(filter(None, [rendered_user, summary]))
                if base_text:
                    docs.append(Document(
                        doc_id=f"{prompt_id}:{log_index}:turn",
                        prompt_id=prompt_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        label=doc_label,
                        text=base_text,
                        tags={'type': 'turn'}
                    ))
                rounds = metadata.get('toolCallRounds') or []
                if isinstance(rounds, list):
                    for round_index, round_entry in enumerate(rounds):
                        docs.extend(expand_round_documents(prompt_id, log_index, round_index, round_entry, metadata, session_id, agent_id))
        return docs
    finally:
        conn.close()


def expand_round_documents(prompt_id: str, log_index: int, round_index: int, round_entry: dict, metadata: dict, session_id: Optional[str], agent_id: Optional[str]) -> List[Document]:
    docs: List[Document] = []
    if not isinstance(round_entry, dict):
        return docs
    response_text = round_entry.get('response', '')
    round_summary = round_entry.get('summary', '')
    thinking = render_segments(round_entry.get('thinking'))
    round_components = '\n'.join(filter(None, [response_text, round_summary, thinking]))
    if round_components:
        docs.append(Document(
            doc_id=f"{prompt_id}:{log_index}:round:{round_index}",
            prompt_id=prompt_id,
            session_id=session_id,
            agent_id=agent_id,
            label=f"{prompt_id} round {round_index}",
            text=round_components,
            tags={'type': 'round'}
        ))
    tool_calls = round_entry.get('toolCalls') or []
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            doc = build_tool_call_document(tool_call, metadata, prompt_id, log_index, round_index, session_id, agent_id)
            if doc:
                docs.append(doc)
    return docs


def build_tool_call_document(tool_call: dict, metadata: dict, prompt_id: str, log_index: int, round_index: int, session_id: Optional[str], agent_id: Optional[str]) -> Optional[Document]:
    if not isinstance(tool_call, dict):
        return None
    call_id = tool_call.get('id') or f"{prompt_id}:{round_index}:anon"
    tool_name = tool_call.get('name', 'unknown-tool')
    args = tool_call.get('arguments')
    args_text = ''
    if isinstance(args, str):
        args_text = args
    elif isinstance(args, dict):
        args_text = json.dumps(args, ensure_ascii=False)
    result_payload = None
    tool_results = metadata.get('toolCallResults')
    if isinstance(tool_results, dict):
        result_payload = tool_results.get(call_id)
    result_text = render_tool_result(result_payload)
    combined_text = '\n'.join(filter(None, [f"tool:{tool_name}", args_text, result_text]))
    status = ''
    if isinstance(result_payload, dict):
        status = str(result_payload.get('status', ''))
    if not combined_text:
        return None
    return Document(
        doc_id=f"{prompt_id}:{log_index}:round:{round_index}:tool:{call_id}",
        prompt_id=prompt_id,
        session_id=session_id,
        agent_id=agent_id,
        label=f"{tool_name} ({call_id})",
        text=combined_text,
        tags={'type': 'tool', 'tool': tool_name, 'status': status}
    )


def render_segments(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ' '.join(render_segments(v) for v in value.values())
    if isinstance(value, list):
        return ' '.join(render_segments(item) for item in value)
    return ''


def render_tool_result(payload) -> str:
    if payload is None:
        return ''
    if isinstance(payload, dict):
        if 'content' in payload and isinstance(payload['content'], list):
            parts = [render_tool_result(part) for part in payload['content']]
            return '\n'.join(filter(None, parts))
        values = []
        for key, value in payload.items():
            if key in {'status', '$mid'}:
                continue
            text = render_tool_result(value)
            if text:
                values.append(text)
        return '\n'.join(values)
    if isinstance(payload, list):
        return '\n'.join(filter(None, (render_tool_result(item) for item in payload)))
    if isinstance(payload, str):
        return payload
    return str(payload)


def tokenize(text: str) -> Counter:
    tokens = TOKEN_RE.findall(text.lower())
    return Counter(tokens)


def build_tfidf_index(documents: List[Document]):
    doc_term_counts: List[Counter] = [tokenize(doc.text) for doc in documents]
    df: defaultdict = defaultdict(int)
    for counts in doc_term_counts:
        for term in counts:
            df[term] += 1
    total_docs = len(documents)
    doc_vectors: List[Dict[str, float]] = []
    norms: List[float] = []
    for counts in doc_term_counts:
        vec: Dict[str, float] = {}
        norm_sq = 0.0
        for term, count in counts.items():
            idf = math.log((total_docs + 1) / (df[term] + 1)) + 1
            weight = (count / sum(counts.values())) * idf
            if weight:
                vec[term] = weight
                norm_sq += weight * weight
        doc_vectors.append(vec)
        norms.append(math.sqrt(norm_sq))
    return doc_vectors, norms, df, total_docs


def compute_query_vector(query: str, df: Dict[str, int], total_docs: int):
    counts = tokenize(query)
    vec: Dict[str, float] = {}
    norm_sq = 0.0
    for term, count in counts.items():
        idf = math.log((total_docs + 1) / (df.get(term, 0) + 1)) + 1
        weight = (count / sum(counts.values())) * idf
        vec[term] = weight
        norm_sq += weight * weight
    return vec, math.sqrt(norm_sq)


def cosine_similarity(vec_a: Dict[str, float], norm_a: float, vec_b: Dict[str, float], norm_b: float) -> float:
    if not norm_a or not norm_b:
        return 0.0
    shared = set(vec_a.keys()) & set(vec_b.keys())
    dot = sum(vec_a[t] * vec_b[t] for t in shared)
    return dot / (norm_a * norm_b)


def search(documents: List[Document], doc_vectors: List[Dict[str, float]], norms: List[float], df: Dict[str, int], total_docs: int, query: str, limit: int) -> List[tuple]:
    query_vec, query_norm = compute_query_vector(query, df, total_docs)
    scores = []
    for doc, vec, norm in zip(documents, doc_vectors, norms):
        score = cosine_similarity(query_vec, query_norm, vec, norm)
        if score > 0:
            scores.append((score, doc))
    scores.sort(key=lambda item: item[0], reverse=True)
    return scores[:limit]


def compute_cache_key(db_path: Path, agent: Optional[str], sessions: Optional[Sequence[str]]) -> Tuple[str, float, int, Optional[str], Tuple[str, ...]]:
    db_stat = db_path.stat()
    session_tuple: Tuple[str, ...] = tuple(sorted(sessions)) if sessions else tuple()
    return (str(db_path.resolve()), db_stat.st_mtime, db_stat.st_size, agent, session_tuple)


def cache_directory(db_path: Path, override: Optional[Path]) -> Path:
    if override is not None:
        directory = override
    else:
        directory = db_path.parent / '.cache' / 'conversation_recall'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cache_path_for_key(cache_dir: Path, key: Tuple[str, float, int, Optional[str], Tuple[str, ...]]) -> Path:
    digest_source = json.dumps({
        'db': key[0],
        'mtime': key[1],
        'size': key[2],
        'agent': key[3],
        'sessions': key[4],
        'version': CACHE_VERSION,
    }, sort_keys=True)
    digest = hashlib.sha256(digest_source.encode('utf-8')).hexdigest()[:24]
    return cache_dir / f'{digest}.pkl'


def load_cached_payload(path: Path, key: Tuple[str, float, int, Optional[str], Tuple[str, ...]]):
    try:
        with path.open('rb') as handle:
            payload = pickle.load(handle)
    except (OSError, pickle.PickleError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get('version') != CACHE_VERSION:
        return None
    if payload.get('key') != key:
        return None
    return payload


def store_cache(path: Path, key: Tuple[str, float, int, Optional[str], Tuple[str, ...]], documents: List[Document], doc_vectors: List[Dict[str, float]], norms: List[float], df: Dict[str, int], total_docs: int) -> None:
    payload = {
        'version': CACHE_VERSION,
        'key': key,
        'documents': documents,
        'doc_vectors': doc_vectors,
        'norms': norms,
        'df': dict(df),
        'total_docs': total_docs,
    }
    try:
        with path.open('wb') as handle:
            pickle.dump(payload, handle)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description='Search Copilot chat history for similar situations.')
    parser.add_argument('query', help='What situation are you looking for?')
    parser.add_argument('--limit', type=int, default=10, help='Maximum results to display.')
    parser.add_argument('--agent', help='Filter by agent identifier.')
    parser.add_argument('--session', action='append', help='Restrict to specific session ids (can repeat).')
    parser.add_argument('--db', type=Path, default=DB_PATH, help='Path to the live_chat.db catalog.')
    parser.add_argument('--cache-dir', type=Path, help='Directory to store TF-IDF cache artifacts.')
    parser.add_argument('--no-cache', action='store_true', help='Disable cache usage for this run.')
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f'Database not found at {args.db}')

    key = compute_cache_key(args.db, args.agent, args.session)
    cache_dir = cache_directory(args.db, args.cache_dir)
    cache_path = cache_path_for_key(cache_dir, key)

    documents: List[Document]
    doc_vectors: List[Dict[str, float]]
    norms: List[float]
    df: Dict[str, int]
    total_docs: int

    payload = None
    if not args.no_cache and cache_path.exists():
        payload = load_cached_payload(cache_path, key)

    if payload:
        documents = payload['documents']
        doc_vectors = payload['doc_vectors']
        norms = payload['norms']
        df = payload['df']
        total_docs = payload['total_docs']
    else:
        documents = load_documents(args.db, args.session, args.agent)
        if not documents:
            raise SystemExit('No documents available. Ensure the catalog is populated.')
        doc_vectors, norms, df, total_docs = build_tfidf_index(documents)
        if not args.no_cache:
            store_cache(cache_path, key, documents, doc_vectors, norms, df, total_docs)

    results = search(documents, doc_vectors, norms, df, total_docs, args.query, args.limit)

    if not results:
        print('No similar situations found.')
        return

    for score, doc in results:
        snippet = doc.text.replace('\n', ' ')
        if len(snippet) > 220:
            snippet = snippet[:217] + '...'
        status = doc.tags.get('status', '')
        tool = doc.tags.get('tool', '')
        print(f"score={score:.3f} session={doc.session_id or 'unknown'} doc={doc.doc_id}")
        if tool:
            print(f"  tool={tool}")
        if status:
            print(f"  status={status}")
        print(f"  {snippet}\n")


if __name__ == '__main__':
    main()
