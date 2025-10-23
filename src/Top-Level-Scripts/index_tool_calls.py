"""Build a Copilot tool-call index and Markdown instructions from chat logs.

The script can read either the SQLite catalog produced by ``chat_logs_to_sqlite.py``
or raw ``*.chatreplay.json`` exports. It emits two artifacts in the chosen output
folder by default:

* ``tool_call_index.jsonl`` – one JSON object per observed tool call with the
  surrounding prompt, arguments, status, and result snippet. This is intended to
  be LLM-friendly for retrieval or fine-tuning.
* ``tool_instructions.md`` – aggregated guidance per tool with lightweight
  statistics, keyword hints, and representative samples that can be dropped into
  a Copilot ``.instructions.md`` file.

Example usage::

    python index_tool_calls.py --db copilot_chat_logs.db --output-dir out/
    python index_tool_calls.py exports/ --output-dir out/
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    from chat_logs_to_sqlite import (  # type: ignore
        DEFAULT_DB_NAME,
        UserVisibleError,
        iter_chatreplay_files,
        load_prompts,
    )
except ImportError:  # pragma: no cover - fallback for standalone execution
    DEFAULT_DB_NAME = "copilot_chat_logs.db"

    class UserVisibleError(RuntimeError):
        pass

    def iter_chatreplay_files(target: Optional[Path]) -> Iterator[Path]:
        raise UserVisibleError("chat_logs_to_sqlite.py is required in the same directory.")

    def load_prompts(path: Path):
        raise UserVisibleError("chat_logs_to_sqlite.py is required in the same directory.")


@dataclass
class ToolSample:
    tool: str
    prompt_id: str
    log_id: str
    prompt_text: str
    arguments: Optional[str]
    result_text: Optional[str]
    status: Optional[str]
    intent: Optional[str]
    time: Optional[str]
    summary: Optional[str]
    source_file: Optional[str]
    imported_at: Optional[str]


@dataclass
class ToolSummary:
    tool: str
    samples: List[ToolSample] = field(default_factory=list)
    intents: Counter[str] = field(default_factory=Counter)
    statuses: Counter[str] = field(default_factory=Counter)
    keywords: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return len(self.samples)


STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "have",
    "your",
    "about",
    "there",
    "would",
    "could",
    "should",
    "their",
    "into",
    "where",
    "when",
    "what",
    "which",
    "will",
    "while",
    "against",
    "because",
    "having",
    "those",
    "these",
    "been",
    "some",
    "only",
    "here",
    "also",
    "just",
    "over",
    "than",
    "used",
    "using",
    "once",
    "each",
    "such",
    "ever",
    "very",
    "much",
    "make",
    "made",
    "does",
    "done",
    "need",
    "like",
    "give",
    "take",
    "most",
    "many",
    "more",
    "less",
    "them",
    "they",
    "were",
    "then",
    "back",
    "same",
    "into",
    "none",
    "null",
    "true",
    "false",
    "info",
    "data",
}

WORD_RE = re.compile(r"[A-Za-z0-9]{3,}")
SUCCESS_TOKENS = {"success", "succeeded", "ok", "completed", "done"}
FAILURE_TOKENS = {"fail", "failed", "error", "timeout", "cancelled", "canceled"}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index Copilot tool calls and emit Markdown instructions.")
    parser.add_argument(
        "path",
        nargs="?",
        help="Optional path to scan for .chatreplay.json exports when --db is not supplied.",
    )
    parser.add_argument(
        "--db",
        help="Optional SQLite catalog produced by chat_logs_to_sqlite.py. Defaults to copilot_chat_logs.db when present.",
    )
    parser.add_argument(
        "--output-dir",
        default="tool_call_index",
        help="Directory to write generated artifacts (default: tool_call_index).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=3,
        help="Maximum sample interactions per tool in Markdown output (default: 3).",
    )
    parser.add_argument(
        "--max-args-chars",
        type=int,
        default=400,
        help="Character limit for argument snippets in Markdown output (default: 400).",
    )
    parser.add_argument(
        "--max-result-chars",
        type=int,
        default=400,
        help="Character limit for result snippets in Markdown output (default: 400).",
    )
    parser.add_argument(
        "--no-jsonl",
        action="store_true",
        help="Skip writing tool_call_index.jsonl if the structured index is not needed.",
    )
    return parser.parse_args(argv)


def load_samples_from_database(db_path: Path) -> List[ToolSample]:
    if not db_path.exists():
        raise UserVisibleError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        prompts: Dict[str, Dict[str, Any]] = {}
        for row in conn.execute(
            "SELECT prompt_id, prompt_text, raw_json, source_file, imported_at FROM prompts"
        ):
            prompt_id = row["prompt_id"]
            prompt_text = (row["prompt_text"] or "").strip()
            raw_json = row["raw_json"]
            intent = None
            if raw_json:
                try:
                    prompt_payload = json.loads(raw_json)
                    intent = extract_intent(prompt_payload)
                except json.JSONDecodeError:
                    intent = None
            prompts[prompt_id] = {
                "prompt_text": prompt_text,
                "intent": intent,
                "source_file": row["source_file"],
                "imported_at": row["imported_at"],
            }

        tool_results: Dict[Tuple[str, str], List[Tuple[int, str]]] = defaultdict(list)
        for row in conn.execute(
            "SELECT prompt_id, log_id, part_index, content FROM tool_results ORDER BY prompt_id, log_id, part_index"
        ):
            key = (row["prompt_id"], row["log_id"])
            content = row["content"]
            if content is None:
                continue
            tool_results[key].append((row["part_index"], content))

        samples: List[ToolSample] = []
        seen: set[Tuple[str, str]] = set()

        for row in conn.execute(
            "SELECT prompt_id, log_id, raw_json, time, summary FROM prompt_logs WHERE kind = 'toolCall' ORDER BY prompt_id, log_index"
        ):
            prompt_id = row["prompt_id"]
            log_id = row["log_id"]
            key = (prompt_id, log_id)
            if key in seen:
                continue
            seen.add(key)

            raw_json = row["raw_json"]
            if not raw_json:
                continue
            try:
                log_payload = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            tool_name = extract_tool_name(log_payload)
            if not tool_name:
                continue

            prompt_info = prompts.get(prompt_id, {})
            prompt_text = prompt_info.get("prompt_text") or ""
            arguments = extract_arguments(log_payload)
            result_text = combine_result_text(log_payload, tool_results.get(key))
            status = extract_status(log_payload)
            summary = log_payload.get("summary") or row["summary"]
            intent = prompt_info.get("intent")
            source_file = prompt_info.get("source_file")
            imported_at = prompt_info.get("imported_at")
            time_value = extract_time_value(log_payload) or row["time"]

            samples.append(
                ToolSample(
                    tool=tool_name,
                    prompt_id=prompt_id,
                    log_id=log_id,
                    prompt_text=prompt_text,
                    arguments=arguments,
                    result_text=result_text,
                    status=status,
                    intent=intent,
                    time=time_value,
                    summary=summary,
                    source_file=source_file,
                    imported_at=imported_at,
                )
            )

        return samples
    finally:
        conn.close()


def load_samples_from_exports(target: Optional[Path]) -> List[ToolSample]:
    files = list(iter_chatreplay_files(target))
    if not files:
        raise UserVisibleError("No .chatreplay.json files located.")

    samples: List[ToolSample] = []
    seen: set[Tuple[str, str]] = set()

    for file_path in files:
        prompts, metadata = load_prompts(file_path)
        source_file = metadata.get("source_file")
        imported_at = metadata.get("imported_at")
        for prompt in prompts:
            prompt_id = str(prompt.get("promptId") or prompt.get("id") or "")
            if not prompt_id:
                continue
            prompt_text = str(prompt.get("prompt") or prompt.get("promptText") or "").strip()
            intent = extract_intent(prompt)
            logs = prompt.get("logs")
            if not isinstance(logs, list):
                continue
            for index, log in enumerate(logs):
                if not isinstance(log, dict) or log.get("kind") != "toolCall":
                    continue
                log_id = str(log.get("id") or f"{prompt_id}:{index}")
                key = (prompt_id, log_id)
                if key in seen:
                    continue
                seen.add(key)

                tool_name = extract_tool_name(log)
                if not tool_name:
                    continue
                arguments = extract_arguments(log)
                result_text = combine_result_text(log, None)
                status = extract_status(log)
                summary = log.get("summary")
                time_value = extract_time_value(log)

                samples.append(
                    ToolSample(
                        tool=tool_name,
                        prompt_id=prompt_id,
                        log_id=log_id,
                        prompt_text=prompt_text,
                        arguments=arguments,
                        result_text=result_text,
                        status=status,
                        intent=intent,
                        time=time_value,
                        summary=summary,
                        source_file=source_file,
                        imported_at=imported_at,
                    )
                )

    return samples


def extract_intent(payload: Dict[str, Any]) -> Optional[str]:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        intent = metadata.get("intent") or metadata.get("purpose")
        if isinstance(intent, str) and intent.strip():
            return intent.strip()
    intent = payload.get("intent")
    if isinstance(intent, str) and intent.strip():
        return intent.strip()
    return None


def extract_tool_name(payload: Dict[str, Any]) -> Optional[str]:
    candidates = [
        payload.get("tool"),
        payload.get("name"),
        payload.get("identifier"),
        payload.get("toolName"),
    ]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend(
            [
                metadata.get("tool"),
                metadata.get("name"),
                metadata.get("toolName"),
            ]
        )
    call = payload.get("call")
    if isinstance(call, dict):
        candidates.extend(
            [
                call.get("tool"),
                call.get("name"),
            ]
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_arguments(payload: Dict[str, Any]) -> Optional[str]:
    keys = ("arguments", "args", "input", "params", "parameters", "request")
    value = _extract_first(payload, keys)
    if value is None:
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            value = _extract_first(metadata, keys)
    if value is None:
        call = payload.get("call")
        if isinstance(call, dict):
            value = _extract_first(call, keys)
    return stringify_payload(value)


def extract_status(payload: Dict[str, Any]) -> Optional[str]:
    keys = ("status", "state", "outcome", "resultStatus")
    value = _extract_first(payload, keys)
    if value is None:
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            value = _extract_first(metadata, keys)
    if value is None and "error" in payload:
        return "error"
    if isinstance(value, str):
        return value.strip()
    return None


def extract_time_value(payload: Dict[str, Any]) -> Optional[str]:
    value = payload.get("time")
    if isinstance(value, str) and value.strip():
        return value.strip()
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("time", "timestamp", "startTime", "endTime"):
            candidate = metadata.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def combine_result_text(payload: Dict[str, Any], parts: Optional[List[Tuple[int, str]]]) -> Optional[str]:
    if parts:
        ordered = [value for _, value in sorted(parts, key=lambda item: item[0])]
        text = "\n".join(ordered).strip()
        if text:
            return text

    for key in ("response", "result", "output", "toolResponse"):
        value = payload.get(key)
        if value is not None:
            rendered = stringify_payload(value)
            if rendered:
                return rendered

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        preview = metadata.get("responsePreview") or metadata.get("resultPreview")
        if isinstance(preview, str) and preview.strip():
            return preview.strip()
    return None


def stringify_payload(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        return json.dumps(value, ensure_ascii=True, indent=2)
    except (TypeError, ValueError):
        return str(value)


def _extract_first(container: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in container:
            return container[key]
    return None


def aggregate_samples(samples: Iterable[ToolSample]) -> Dict[str, ToolSummary]:
    summaries: Dict[str, ToolSummary] = {}
    for sample in samples:
        summary = summaries.setdefault(sample.tool, ToolSummary(tool=sample.tool))
        summary.samples.append(sample)
        status = normalize_status(sample.status)
        summary.statuses[status] += 1
        intent = sample.intent or "unknown"
        summary.intents[intent] += 1
        update_keywords(summary.keywords, sample.prompt_text)
    return summaries


def normalize_status(status: Optional[str]) -> str:
    if not status:
        return "unknown"
    lowered = status.lower()
    if any(token in lowered for token in SUCCESS_TOKENS):
        return "success"
    if any(token in lowered for token in FAILURE_TOKENS):
        return "failure"
    return lowered.strip() or "unknown"


def update_keywords(counter: Counter[str], text: str) -> None:
    if not text:
        return
    for word in WORD_RE.findall(text.lower()):
        if word in STOPWORDS:
            continue
        counter[word] += 1


def write_jsonl(samples: Iterable[ToolSample], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            payload = {
                "tool": sample.tool,
                "prompt_id": sample.prompt_id,
                "log_id": sample.log_id,
                "prompt": sample.prompt_text,
                "arguments": sample.arguments,
                "status": sample.status,
                "result": sample.result_text,
                "intent": sample.intent,
                "time": sample.time,
                "summary": sample.summary,
                "source_file": sample.source_file,
                "imported_at": sample.imported_at,
            }
            handle.write(json.dumps(payload, ensure_ascii=True))
            handle.write("\n")


def write_markdown(
    summaries: Dict[str, ToolSummary],
    output_path: Path,
    *,
    max_samples: int,
    max_args_chars: int,
    max_result_chars: int,
) -> None:
    lines: List[str] = []
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    lines.append("# Copilot Tool Instruction Index")
    lines.append("")
    lines.append(f"Generated {now_iso} UTC by index_tool_calls.py")
    lines.append("")

    for tool_name in sorted(summaries.keys(), key=lambda key: summaries[key].total, reverse=True):
        summary = summaries[tool_name]
        if summary.total == 0:
            continue
        success = summary.statuses.get("success", 0)
        failure = summary.statuses.get("failure", 0)
        lines.append(f"## {tool_name}")
        lines.append("")
        lines.append(f"- calls: {summary.total}")
        if success or failure:
            lines.append(f"- status: {success} success, {failure} failure")
        intents = ", ".join(word for word, _ in summary.intents.most_common() if word != "unknown")
        if intents:
            lines.append(f"- intents: {intents}")
        keywords = ", ".join(word for word, _ in summary.keywords.most_common(8))
        if keywords:
            lines.append(f"- keywords: {keywords}")
        lines.append("")
        lines.append("### Sample interactions")
        lines.append("")

        for index, sample in enumerate(select_samples(summary.samples, max_samples), start=1):
            status = normalize_status(sample.status)
            timestamp = sample.time or sample.imported_at or "unknown"
            lines.append(f"#### Sample {index} — status: {status}; time: {timestamp}")
            lines.append("")
            prompt_excerpt = format_excerpt(sample.prompt_text, max_chars=400)
            lines.append("Prompt")
            lines.append("```")
            lines.append(prompt_excerpt)
            lines.append("```")
            lines.append("")
            if sample.arguments:
                argument_excerpt = format_excerpt(sample.arguments, max_chars=max_args_chars)
                lines.append("Arguments")
                lines.append("```json")
                lines.append(argument_excerpt)
                lines.append("```")
                lines.append("")
            if sample.result_text:
                result_excerpt = format_excerpt(sample.result_text, max_chars=max_result_chars)
                lines.append("Result")
                lines.append("```")
                lines.append(result_excerpt)
                lines.append("```")
                lines.append("")
            if sample.summary:
                lines.append(f"> Summary: {sample.summary}")
                lines.append("")

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def select_samples(samples: List[ToolSample], limit: int) -> List[ToolSample]:
    if limit <= 0:
        return []
    def sort_key(sample: ToolSample) -> Tuple[int, Optional[datetime]]:
        status_rank = {"success": 0, "unknown": 1, "failure": 2}.get(normalize_status(sample.status), 3)
        time_value = parse_time(sample.time or sample.imported_at)
        return (status_rank, time_value and -time_value.timestamp())

    sorted_samples = sorted(samples, key=sort_key)
    return sorted_samples[:limit]


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_excerpt(text: str, *, max_chars: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    samples: List[ToolSample] = []
    if args.db:
        samples.extend(load_samples_from_database(Path(args.db)))
    else:
        db_candidate = Path(DEFAULT_DB_NAME)
        if db_candidate.exists():
            samples.extend(load_samples_from_database(db_candidate))

    if not samples:
        target = Path(args.path).expanduser() if args.path else None
        samples.extend(load_samples_from_exports(target))

    if not samples:
        raise UserVisibleError("No tool calls found.")

    summaries = aggregate_samples(samples)

    markdown_path = output_dir / "tool_instructions.md"
    write_markdown(
        summaries,
        markdown_path,
        max_samples=args.max_samples,
        max_args_chars=args.max_args_chars,
        max_result_chars=args.max_result_chars,
    )

    if not args.no_jsonl:
        jsonl_path = output_dir / "tool_call_index.jsonl"
        write_jsonl(samples, jsonl_path)

    print(f"Wrote {markdown_path}")
    if not args.no_jsonl:
        print(f"Wrote {jsonl_path}")


if __name__ == "__main__":  # pragma: no cover
    try:
        main(sys.argv[1:])
    except UserVisibleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
