"""Pattern matchers that collapse Copilot metadata messages into Markdown-ready actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .utils import extract_fs_path, format_uri, prune_keys, short_path

MetadataMessage = Dict[str, Any]


@dataclass
class RenderedAction:
    title: str
    summary: str
    details: Sequence[str]
    raw_payloads: Sequence[MetadataMessage]
    _sensitive_keys = {"encrypted"}
    _noisy_metadata_keys = {
        "encrypted",
        "undoStop",
        "codeblockUri", 
        "invocationMessage",  # Already extracted in compact form
        "autoApproveInfo",    # Already extracted in compact form
        "prepareToolInvocation",  # Redundant preamble
    }

    def to_markdown(self, include_raw: bool) -> List[str]:
        lines: List[str] = [f"**{self.title}** — {self.summary}"]
        for detail in self.details:
            if detail:
                lines.append(detail)
        if include_raw:
            for payload in self.raw_payloads:
                lines.append("```json")
                cleaned = prune_keys(payload, self._noisy_metadata_keys)
                lines.append(json.dumps(cleaned, ensure_ascii=False, indent=2))
                lines.append("```")
        return lines


@dataclass
class PatternMatch:
    length: int
    action: RenderedAction


Matcher = Tuple[str, "PatternFunction"]
PatternFunction = Any  # Callable defined via Protocol-like usage to avoid runtime deps


def _is_kind(message: MetadataMessage, expected: str) -> bool:
    return message.get("kind") == expected


def _tool_identifier(message: MetadataMessage) -> Optional[str]:
    for key in ("toolName", "toolId", "tool"):
        value = message.get(key)
        if isinstance(value, str):
            return value
    tool = message.get("toolSpecificData")
    if isinstance(tool, dict):
        cand = tool.get("toolId") or tool.get("toolName")
        if isinstance(cand, str):
            return cand
    return None


def _line_delta(edit: Dict[str, Any]) -> Tuple[int, int]:
    text = edit.get("text")
    added = 0
    if isinstance(text, str) and text:
        added = text.count("\n") + 1
    rng = edit.get("range")
    removed = 0
    if isinstance(rng, dict):
        start = rng.get("startLineNumber")
        end = rng.get("endLineNumber")
        if isinstance(start, int) and isinstance(end, int):
            removed = max(0, end - start)
    return added, removed


def _format_apply_patch(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    if len(messages) < 3:
        return None
    first, second, third = messages[0], messages[1], messages[2]
    if not _is_kind(first, "prepareToolInvocation"):
        return None
    if _tool_identifier(first) != "copilot_applyPatch":
        return None
    if not _is_kind(second, "toolInvocationSerialized"):
        return None
    if _tool_identifier(second) not in {"copilot_applyPatch", "applyPatch"}:
        return None
    if not _is_kind(third, "textEditGroup"):
        return None

    edits = third.get("edits")
    if not isinstance(edits, list) or not edits:
        return None

    files: List[str] = []
    added_total = 0
    removed_total = 0
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        uri = edit.get("uri")
        if isinstance(uri, dict):
            fs_path = extract_fs_path(uri)
            if fs_path:
                files.append(short_path(fs_path))
        added, removed = _line_delta(edit)
        added_total += added
        removed_total += removed

    if not files:
        files.append("unknown file")

    # Unique & concise file summary
    unique_files = sorted(set(files))
    file_count = len(unique_files)
    display_files = unique_files[:3]
    more_count = max(0, file_count - len(display_files))

    undo_stop: Optional[MetadataMessage] = None
    if len(messages) > 3 and _is_kind(messages[3], "undoStop"):
        undo_stop = messages[3]

    title = "Apply Patch"
    summary = ", ".join(display_files) + (f", +{more_count} more" if more_count > 0 else "")
    details = [
        f"Files: {file_count}",
        f"Lines: +{added_total} / -{removed_total}",
    ]

    raw_payloads: List[MetadataMessage] = [first, second, third]
    if undo_stop:
        raw_payloads.append(undo_stop)

    action = RenderedAction(title=title, summary=summary, details=details, raw_payloads=raw_payloads)
    length = 4 if undo_stop else 3
    return PatternMatch(length=length, action=action)


def _format_terminal(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    if len(messages) < 2:
        return None
    first, second = messages[0], messages[1]
    if not _is_kind(first, "prepareToolInvocation"):
        return None
    if _tool_identifier(first) != "run_in_terminal":
        return None
    if not _is_kind(second, "toolInvocationSerialized"):
        return None
    if _tool_identifier(second) != "run_in_terminal":
        return None

    tool_data = second.get("toolSpecificData")
    summary = "Terminal command"
    details: List[str] = []
    status_suffix = ""

    def _collect_tail_from_result(result: Dict[str, Any]) -> Optional[Tuple[str, List[str]]]:
        """Return (label, lines) for a concise tail snippet.

        Preference: stderr-like fields, else stdout-like fields. Applies a
        conservative cap and marks truncation in the label.
        """
        if not isinstance(result, dict):
            return None

        # Helper to flatten potentially nested values into a single string
        def _to_text(val: Any) -> str:
            if val is None:
                return ""
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                return "\n".join(str(x) for x in val if x is not None)
            if isinstance(val, dict):
                for k in ("text", "value", "message", "stderr", "stdout"):
                    v = val.get(k)
                    if isinstance(v, str):
                        return v
                try:
                    return json.dumps(val, ensure_ascii=False)
                except Exception:
                    return str(val)
            return str(val)

        # Prefer stderr/error; fallback to stdout/output
        stderr_texts: List[str] = []
        for key in ("stderr", "error", "message", "lastLines", "content"):
            v = result.get(key)
            if v:
                stderr_texts.append(_to_text(v))

        stdout_texts: List[str] = []
        for key in ("stdout", "output"):
            v = result.get(key)
            if v:
                stdout_texts.append(_to_text(v))

        source_label = "stderr"
        joined = "\n".join(t for t in stderr_texts if t.strip())
        if not joined:
            source_label = "output"
            joined = "\n".join(t for t in stdout_texts if t.strip())
        if not joined:
            return None

        # Split and take a tail with caps
        lines = [ln for ln in joined.splitlines()]
        max_lines = 6
        max_chars = 700
        truncated = False
        if len(lines) > max_lines:
            truncated = True
            lines = lines[-max_lines:]
        # Char budget post line-tail selection
        current = "\n".join(lines)
        if len(current) > max_chars:
            truncated = True
            # Trim from the front to keep the very last characters
            keep = current[-max_chars:]
            lines = keep.splitlines()

        label = f"Last {source_label} lines:"
        if truncated:
            label = label[:-1] + " (truncated):"
        return (label, lines)
    
    if isinstance(tool_data, dict):
        command_line = tool_data.get("commandLine")
        if isinstance(command_line, dict):
            original = command_line.get("original")
            if isinstance(original, str):
                # Truncate very long commands
                if len(original) > 100:
                    summary = original[:97] + "..."
                else:
                    summary = original
        
        # Extract status information
        tool_result = tool_data.get("toolResult")
        if isinstance(tool_result, dict):
            exit_code = tool_result.get("exitCode")
            if isinstance(exit_code, int):
                if exit_code == 0:
                    status_suffix = " → ✓"
                else:
                    status_suffix = f" → exit {exit_code}"
            # Prefer stderr/output tail when failure or when warnings (exit=0 with stderr)
            error_present = tool_result.get("error") is not None
            stderr_present = bool(tool_result.get("stderr"))
            is_failure = (isinstance(exit_code, int) and exit_code != 0) or error_present
            warnings_only = (not is_failure) and stderr_present
            if is_failure or warnings_only:
                tail = _collect_tail_from_result(tool_result)
                if tail:
                    label, lines_tail = tail
                    if warnings_only:
                        # Re-label as warnings while preserving truncated marker
                        is_stderr = "stderr" in label.lower()
                        truncated_suffix = " (truncated):" if "(truncated):" in label else ":"
                        label = f"Warnings ({'stderr' if is_stderr else 'output'}) tail{truncated_suffix}"
                    details.append(label)
                    for ln in lines_tail:
                        if ln.strip():
                            details.append(f"  {ln}")

            # Optional: include duration/cwd if present
            duration_ms = None
            for k in ("durationMs", "elapsedMs", "runtimeMs"):
                v = tool_result.get(k)
                if isinstance(v, (int, float)):
                    duration_ms = int(v)
                    break
            if duration_ms is None:
                # Some records may have start/end timestamps
                start_ms = tool_result.get("startTimeMs")
                end_ms = tool_result.get("endTimeMs")
                if isinstance(start_ms, (int, float)) and isinstance(end_ms, (int, float)) and end_ms >= start_ms:
                    duration_ms = int(end_ms - start_ms)
            if isinstance(duration_ms, int) and duration_ms >= 0:
                details.append(f"Duration: {duration_ms} ms")
        
        # Include working directory / shell if provided at the tool layer
        cwd = tool_data.get("cwd") or tool_data.get("workingDirectory") or tool_data.get("directory")
        if isinstance(cwd, str) and cwd.strip():
            details.append(f"CWD: {short_path(cwd)}")

        shell = tool_data.get("language") or tool_data.get("shell")
        if isinstance(shell, str) and shell.strip():
            details.append(f"Shell: {shell}")

        auto_info = tool_data.get("autoApproveInfo")
        if isinstance(auto_info, dict):
            value = auto_info.get("value")
            if isinstance(value, str) and not status_suffix:
                # Only show explanation if no status marker
                details.append(value)
    
    # Detect post-invocation hints like interactive prompts
    # If the third message indicates an elicitation/awaiting input, surface a hint
    if len(messages) > 2:
        third = messages[2]
        if isinstance(third, dict) and third.get("kind") in {"elicitation", "progressTaskSerialized"}:
            content = third.get("title") or third.get("content") or third.get("invocationMessage") or third.get("message")
            # Handle nested structures
            if isinstance(content, dict):
                content = content.get("value") or content.get("text") or content.get("message")
            if isinstance(content, str) and "awaiting input" in content.lower():
                details.append("Awaiting input (interactive)")

    invocation_message = second.get("invocationMessage")
    if isinstance(invocation_message, str) and invocation_message:
        details.insert(0, invocation_message)

    action = RenderedAction(
        title="Terminal",
        summary=summary + status_suffix,
        details=details,
        raw_payloads=[first, second],
    )
    return PatternMatch(length=2, action=action)


def _format_read_file(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    if len(messages) < 2:
        return None
    first, second = messages[0], messages[1]
    if not _is_kind(first, "prepareToolInvocation"):
        return None
    if _tool_identifier(first) != "read_file":
        return None
    if not _is_kind(second, "toolInvocationSerialized"):
        return None
    if _tool_identifier(second) != "read_file":
        return None

    tool_data = second.get("toolSpecificData")
    summary = "file"
    details: List[str] = []
    
    if isinstance(tool_data, dict):
        file_path = tool_data.get("filePath")
        if isinstance(file_path, str):
            summary = short_path(file_path)
        
        offset = tool_data.get("offset")
        limit = tool_data.get("limit")
        if isinstance(offset, int) and isinstance(limit, int):
            end_line = offset + limit - 1
            details.append(f"Lines {offset}-{end_line}")
        elif isinstance(offset, int):
            details.append(f"Starting at line {offset}")
        elif isinstance(limit, int):
            details.append(f"First {limit} lines")

    action = RenderedAction(
        title="Read",
        summary=summary,
        details=details,
        raw_payloads=[first, second],
    )
    return PatternMatch(length=2, action=action)


def _format_grep_search(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    if len(messages) < 2:
        return None
    first, second = messages[0], messages[1]
    if not _is_kind(first, "prepareToolInvocation"):
        return None
    if _tool_identifier(first) != "grep_search":
        return None
    if not _is_kind(second, "toolInvocationSerialized"):
        return None
    if _tool_identifier(second) != "grep_search":
        return None

    tool_data = second.get("toolSpecificData")
    summary = "pattern search"
    details: List[str] = []
    
    if isinstance(tool_data, dict):
        query = tool_data.get("query")
        if isinstance(query, str):
            # Truncate long patterns
            if len(query) > 60:
                summary = f"`{query[:57]}...`"
            else:
                summary = f"`{query}`"
        
        include_pattern = tool_data.get("includePattern")
        if isinstance(include_pattern, str):
            details.append(f"in `{include_pattern}`")
        
        is_regexp = tool_data.get("isRegexp")
        if is_regexp:
            details.append("(regex)")

    action = RenderedAction(
        title="Search",
        summary=summary,
        details=details,
        raw_payloads=[first, second],
    )
    return PatternMatch(length=2, action=action)


def _format_inline_reference(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    current = messages[0]
    if not _is_kind(current, "inlineReference"):
        return None
    inline = current.get("inlineReference")
    if isinstance(inline, dict):
        name = "Inline reference"
        location = inline.get("location")
        if isinstance(location, dict):
            uri = location.get("uri")
            if isinstance(uri, dict):
                summary = format_uri(uri)
            else:
                summary = json.dumps(location, ensure_ascii=False)
        else:
            summary = "(no location)"
        # If a label/name exists, prepend it to the summary for context
        label = inline.get("name")
        if isinstance(label, str) and label.strip() and summary and summary != "(no location)":
            summary = f"{label.strip()} — {summary}"
    else:
        name = "Inline reference"
        summary = json.dumps(current, ensure_ascii=False)
    # Suppress unhelpful no-location references in default mode
    if not include_raw and summary == "(no location)":
        return PatternMatch(length=1, action=RenderedAction(title="", summary="", details=[], raw_payloads=[]))
    action = RenderedAction(title=name, summary=summary, details=[], raw_payloads=[current])
    return PatternMatch(length=1, action=action)


def _format_message(messages: Sequence[MetadataMessage], include_raw: bool) -> Optional[PatternMatch]:
    # Generic single-message fallback
    current = messages[0]
    kind = current.get("kind", "unknown")
    summary = json.dumps(current, ensure_ascii=False)[:120]
    action = RenderedAction(title=f"Raw {kind}", summary=summary, details=[], raw_payloads=[current])
    return PatternMatch(length=1, action=action)


PATTERN_FUNCTIONS = [
    _format_apply_patch,
    _format_terminal,
    _format_read_file,
    _format_grep_search,
    _format_inline_reference,
]


def match_patterns(messages: Sequence[MetadataMessage], include_raw: bool) -> PatternMatch:
    for formatter in PATTERN_FUNCTIONS:
        result = formatter(messages, include_raw)
        if result:
            return result
    return _format_message(messages, include_raw)


def render_message_stream(messages: Sequence[MetadataMessage], include_raw: bool) -> List[List[str]]:
    # Filter out standalone undoStop messages (they're auto-consumed by ApplyPatch pattern)
    filtered_messages: List[MetadataMessage] = []
    for msg in messages:
        # Skip undoStop unless include_raw (for audit trail preservation)
        if not include_raw and _is_kind(msg, "undoStop"):
            continue
        # Skip noisy singletons commonly emitted around edits and code blocks
        if not include_raw and (_is_kind(msg, "textEditGroup") or _is_kind(msg, "codeblockUri")):
            continue
        filtered_messages.append(msg)
    
    rendered: List[List[str]] = []
    index = 0
    total = len(filtered_messages)
    while index < total:
        subset = filtered_messages[index : index + 4]
        match = match_patterns(subset, include_raw)
        # Suppress low-value singletons by default (still parsable via --raw-actions)
        if (
            not include_raw
            and match.length == 1
            and subset
            and _is_kind(subset[0], "thinking")
        ):
            index += 1
            continue
        if (
            not include_raw
            and match.length == 1
            and subset
            and _is_kind(subset[0], "mcpServersStarting")
        ):
            index += 1
            continue
        if (
            not include_raw
            and match.length == 1
            and subset
            and (_is_kind(subset[0], "prepareToolInvocation") or _is_kind(subset[0], "toolInvocationSerialized"))
        ):
            # If a stray pre/post invocation message wasn't part of a recognised pattern, drop it to reduce noise
            index += 1
            continue

        rendered.append(match.action.to_markdown(include_raw))
        index += match.length
    return rendered
