"""Sample Copilot chat session JSON and emit structural summaries."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarise Copilot chat metadata message shapes.")
    parser.add_argument("session", type=Path, help="Path to a chat session JSON file.")
    parser.add_argument("output", type=Path, help="Path to write the summary JSON.")
    return parser.parse_args()


def load_session(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def classify_value_type(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


def summarise_messages(session: Dict[str, Any]) -> Dict[str, Any]:
    requests = session.get("requests")
    if not isinstance(requests, list):
        return {}

    message_kinds = Counter()
    tool_names = Counter()
    example_messages: list[Dict[str, Any]] = []
    metadata_keys = Counter()
    round_examples: list[Dict[str, Any]] = []
    tool_call_results: list[Dict[str, Any]] = []
    result_type_counts = Counter()
    content_type_counts = Counter()

    for request in requests:
        if not isinstance(request, dict):
            continue
        result = request.get("result")
        if not isinstance(result, dict):
            continue
        metadata = result.get("metadata")
        if not isinstance(metadata, dict):
            continue
        metadata_keys.update(metadata.keys())
        for message in metadata.get("messages") or []:
            if not isinstance(message, dict):
                continue
            kind = message.get("kind") or "unknown"
            message_kinds[kind] += 1
            tool_name = message.get("toolName") or message.get("toolId")
            if isinstance(tool_name, str):
                tool_names[tool_name] += 1
            if len(example_messages) < 5:
                example_messages.append({
                    "kind": kind,
                    "keys": sorted(message.keys()),
                })

        for round_entry in metadata.get("toolCallRounds") or []:
            if not isinstance(round_entry, dict):
                continue
            if len(round_examples) >= 5:
                break
            round_snapshot: Dict[str, Any] = {
                "keys": sorted(round_entry.keys()),
            }
            messages = round_entry.get("messages")
            if isinstance(messages, list) and messages:
                trimmed = []
                for message in messages[:3]:
                    if not isinstance(message, dict):
                        continue
                    trimmed.append({
                        "kind": message.get("kind"),
                        "keys": sorted(message.keys()),
                    })
                round_snapshot["messages"] = trimmed
            tool_calls = round_entry.get("toolCalls")
            if isinstance(tool_calls, list) and tool_calls:
                trimmed_calls = []
                for call in tool_calls[:2]:
                    if not isinstance(call, dict):
                        continue
                    trimmed_call: Dict[str, Any] = {
                        "name": call.get("name") or call.get("toolName"),
                        "keys": sorted(call.keys()),
                    }
                    call_messages = call.get("messages")
                    if isinstance(call_messages, list) and call_messages:
                        trimmed_call["messages"] = [
                            {
                                "kind": message.get("kind"),
                                "keys": sorted(message.keys()),
                            }
                            for message in call_messages[:2]
                            if isinstance(message, dict)
                        ]
                    trimmed_calls.append(trimmed_call)
                round_snapshot["toolCalls"] = trimmed_calls
            round_examples.append(round_snapshot)

        tool_results = metadata.get("toolCallResults")
        if isinstance(tool_results, list):
            result_type_counts.update(["list"])
            for call_result in tool_results:
                if not isinstance(call_result, dict):
                    continue
                if "content" in call_result:
                    content_type_counts.update([classify_value_type(call_result.get("content"))])
                if len(tool_call_results) < 3:
                    snapshot = {
                        "keys": sorted(call_result.keys()),
                        "status": call_result.get("status"),
                    }
                    if "content" in call_result:
                        snapshot["contentType"] = classify_value_type(call_result.get("content"))
                        content_value = call_result.get("content")
                        if isinstance(content_value, str):
                            snapshot["content"] = content_value[:160]
                    if "invocation" in call_result and isinstance(call_result["invocation"], dict):
                        invocation = call_result["invocation"]
                        snapshot["invocation"] = {
                            "name": invocation.get("name"),
                            "keys": sorted(invocation.keys()),
                        }
                    tool_call_results.append(snapshot)
        elif isinstance(tool_results, dict):
            result_type_counts.update(["dict"])
            snapshot: Dict[str, Any] = {
                "keys": sorted(tool_results.keys()),
            }
            items = list(tool_results.items())
            if items:
                first_id, first_payload = items[0]
                if isinstance(first_payload, dict):
                    payload_snapshot: Dict[str, Any] = {
                        "id": first_id,
                        "keys": sorted(first_payload.keys()),
                        "status": first_payload.get("status"),
                    }
                    invocation = first_payload.get("invocation")
                    if isinstance(invocation, dict):
                        payload_snapshot["invocation"] = {
                            "name": invocation.get("name"),
                            "keys": sorted(invocation.keys()),
                        }
                    invocation_message = first_payload.get("invocationMessage")
                    if isinstance(invocation_message, str):
                        payload_snapshot["invocationMessage"] = invocation_message[:160]
                    result_message = first_payload.get("resultMessage")
                    if isinstance(result_message, str):
                        payload_snapshot["resultMessage"] = result_message[:160]
                    if "content" in first_payload:
                        content_value = first_payload.get("content")
                        payload_snapshot["contentType"] = classify_value_type(content_value)
                        if isinstance(content_value, str):
                            payload_snapshot["content"] = content_value[:160]
                    snapshot["sample"] = payload_snapshot
            tool_call_results.append(snapshot)
            for payload in tool_results.values():
                if isinstance(payload, dict) and "content" in payload:
                    content_type_counts.update([classify_value_type(payload.get("content"))])
        elif tool_results is not None:
            result_type_counts.update([type(tool_results).__name__])

    return {
        "messageKinds": dict(message_kinds),
        "toolIdentifiers": dict(tool_names),
        "requestCount": len(requests),
        "metadataKeys": dict(metadata_keys),
        "exampleMessages": example_messages,
        "toolCallRounds": round_examples,
        "toolCallResults": tool_call_results,
        "toolCallResultsTypes": dict(result_type_counts),
        "toolCallResultContentTypes": dict(content_type_counts),
    }


def main() -> None:
    args = parse_args()
    session = load_session(args.session)
    summary = summarise_messages(session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
