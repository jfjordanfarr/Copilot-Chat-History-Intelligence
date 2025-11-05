"""Markdown builders for Copilot chat sessions.

Enhancements:
- Cross-session motif counts (W101): annotate action blocks with counts observed in prior exports.
- Canceled/terminated markers (W103): surface turn status within Actions and include session-level status summary.
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import re

from analysis import similarity_threshold as similarity_threshold_module

from .actions import RenderedActions, render_actions
from .response_parser import inject_actions_into_request
from .utils import format_uri, prune_keys

MetadataMessage = Dict[str, Any]
Request = Dict[str, Any]

SENSITIVE_METADATA_KEYS = {"encrypted"}
CATALOG_DB_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"


def ms_to_iso(timestamp_ms: Optional[int]) -> Optional[str]:
    if not isinstance(timestamp_ms, (int, float)):
        return None
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return dt.isoformat(timespec="seconds")


def squeeze(lines: Iterable[str]) -> List[str]:
    result: List[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        result.append(line)
        previous_blank = blank
    while result and not result[-1].strip():
        result.pop()
    return result


def render_message_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, dict):
        text = message.get("text")
        if isinstance(text, str):
            return text.strip()
        parts = message.get("parts")
        if isinstance(parts, list):
            collected = [render_message_text(part) for part in parts]
            return "\n".join(part for part in collected if part)
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    if isinstance(message, list):
        return "\n".join(part for part in (render_message_text(part) for part in message) if part)
    return str(message)


def render_response_content(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, (int, float)):
        return str(response)
    if isinstance(response, list):
        blocks = [render_response_content(part) for part in response]
        blocks = [block for block in blocks if block]
        return "\n\n".join(blocks)
    if isinstance(response, dict):
        for key in ("value", "content", "text"):
            candidate = response.get(key)
            if isinstance(candidate, str):
                return candidate.strip()
            if isinstance(candidate, list):
                return render_response_content(candidate)
        message = response.get("message")
        if message:
            return render_response_content(message)
        image_url = response.get("imageUrl") or response.get("image_url")
        if isinstance(image_url, dict):
            image_url = image_url.get("url")
        if isinstance(image_url, str) and image_url:
            return f"![image]({image_url})"
        pruned = prune_keys(response, SENSITIVE_METADATA_KEYS)
        try:
            return json.dumps(pruned, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(response)
    return str(response)


_FENCE_OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_TRIPLE_OPEN_RE = re.compile(r'^(?P<indent>[ \t]*)(?P<quote>"""|\'\'\')(?:[ \t]*)$')


def _collapse_structured_blocks(text: str) -> str:
    if not text:
        return text

    def _collapse_fences(lines: List[str]) -> List[str]:
        collapsed: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            fence_match = _FENCE_OPEN_RE.match(line)
            if fence_match:
                indent = fence_match.group("indent") or ""
                fence = fence_match.group("fence")
                info = fence_match.group("info") or ""
                collapsed.append(f"{indent}{fence}{info}")
                collapsed.append(f"{indent}...")
                i += 1
                while i < len(lines):
                    maybe_close = lines[i]
                    stripped = maybe_close.strip()
                    if stripped.startswith(fence) and stripped[len(fence) :].strip() == "":
                        collapsed.append(maybe_close)
                        break
                    i += 1
                else:
                    collapsed.append(f"{indent}{fence}")
                    return collapsed + lines[i:]
                i += 1
                continue
            collapsed.append(line)
            i += 1
        return collapsed

    def _collapse_triple_quotes(lines: List[str]) -> List[str]:
        collapsed: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            triple_match = _TRIPLE_OPEN_RE.match(line)
            if triple_match and i + 1 < len(lines):
                indent = triple_match.group("indent") or ""
                quote = triple_match.group("quote")
                collapsed.append(f"{indent}{quote}")
                collapsed.append(f"{indent}...")
                i += 1
                while i < len(lines):
                    maybe_close = lines[i]
                    if maybe_close.strip() == quote:
                        collapsed.append(maybe_close)
                        break
                    i += 1
                else:
                    collapsed.append(f"{indent}{quote}")
                    return collapsed + lines[i:]
                i += 1
                continue
            collapsed.append(line)
            i += 1
        return collapsed

    ends_with_newline = text.endswith("\n")
    lines = text.splitlines()
    lines = _collapse_fences(lines)
    lines = _collapse_triple_quotes(lines)
    collapsed_text = "\n".join(lines)
    if ends_with_newline:
        collapsed_text += "\n"
    return collapsed_text


def render_reference_entry(reference: Any) -> Optional[str]:
    if isinstance(reference, str):
        return reference
    if not isinstance(reference, dict):
        return None

    label = reference.get("label") or reference.get("name")
    anchor = reference.get("reference") or reference.get("anchor")
    range_info = reference.get("range")

    parts: List[str] = []
    if isinstance(anchor, dict) and "uri" in anchor:
        uri = anchor["uri"]
        if isinstance(uri, dict):
            parts.append(format_uri(uri))
        else:
            parts.append(str(uri))
        range_candidate = anchor.get("range") or range_info
        if isinstance(range_candidate, dict):
            line_start = range_candidate.get("startLineNumber") or range_candidate.get("start")
            line_end = range_candidate.get("endLineNumber") or range_candidate.get("end")
            if isinstance(line_start, int) and isinstance(line_end, int):
                suffix = f":{line_start}" if line_start == line_end else f":{line_start}-{line_end}"
                parts[-1] += suffix
    elif isinstance(anchor, dict) and "value" in anchor and isinstance(anchor["value"], str):
        parts.append(anchor["value"])
    elif isinstance(anchor, str):
        parts.append(anchor)

    if not parts and isinstance(range_info, dict):
        line_start = range_info.get("startLineNumber")
        line_end = range_info.get("endLineNumber")
        if isinstance(line_start, int) and isinstance(line_end, int):
            parts.append(f"lines {line_start}-{line_end}")

    if label:
        parts.insert(0, label)

    return " — ".join(parts) if parts else label


def collect_references(request: Dict[str, Any]) -> List[str]:
    entries: List[str] = []

    for reference in request.get("contentReferences") or []:
        rendered = render_reference_entry(reference)
        if rendered:
            entries.append(rendered)

    variable_data = request.get("variableData")
    if isinstance(variable_data, dict):
        for variable in variable_data.get("variables") or []:
            if not isinstance(variable, dict):
                continue
            label = variable.get("name") or variable.get("id")
            value = variable.get("value")
            rendered_value: Optional[str] = None
            if isinstance(value, dict) and "uri" in value:
                uri = value["uri"]
                if isinstance(uri, dict):
                    rendered_value = format_uri(uri)
                else:
                    rendered_value = str(uri)
                range_info = value.get("range")
                if isinstance(range_info, dict):
                    start = range_info.get("startLineNumber")
                    end = range_info.get("endLineNumber")
                    if isinstance(start, int) and isinstance(end, int):
                        suffix = f":{start}" if start == end else f":{start}-{end}"
                        rendered_value += suffix
            elif isinstance(value, dict) and "text" in value:
                rendered_value = textwrap.shorten(str(value.get("text")), width=80, placeholder="…")
            elif isinstance(value, str):
                rendered_value = value
            if rendered_value:
                entries.append(f"{label}: {rendered_value}" if label else rendered_value)

    return entries


def render_thinking_block(metadata: Dict[str, Any]) -> Optional[str]:
    thinking = metadata.get("thinking")
    if not thinking:
        return None
    if isinstance(thinking, dict):
        text = thinking.get("text")
    else:
        text = thinking
    if isinstance(text, list):
        text = "\n".join(part for part in text if isinstance(part, str))
    if not isinstance(text, str) or not text.strip():
        return None
    lines = ["> _Thinking_", ">"]
    for line in text.splitlines():
        lines.append(f"> {line}" if line else ">")
    return "\n".join(lines)


def render_tool_invocations(metadata: Dict[str, Any]) -> List[str]:
    invocations = metadata.get("toolInvocations")
    if not isinstance(invocations, list) or not invocations:
        return []

    lines: List[str] = []
    for tool in invocations:
        if not isinstance(tool, dict):
            continue
        tool = prune_keys(tool, SENSITIVE_METADATA_KEYS)
        name = tool.get("name") or tool.get("toolName") or tool.get("id") or "Unknown tool"
        lines.extend(["", f"#### Tool call: {name}"])

        arguments = tool.get("args") or tool.get("arguments")
        if isinstance(arguments, (dict, list)):
            pretty_args = json.dumps(arguments, ensure_ascii=False, indent=2)
            lines.extend(["", "**Arguments**", "```json", pretty_args, "```"])
        elif isinstance(arguments, str) and arguments.strip():
            maybe_json = arguments.strip()
            try:
                parsed = json.loads(maybe_json)
            except json.JSONDecodeError:
                lines.extend(["", "**Arguments**", "```", maybe_json, "```"])
            else:
                clean_parsed = prune_keys(parsed, SENSITIVE_METADATA_KEYS)
                lines.extend(["", "**Arguments**", "```json", json.dumps(clean_parsed, ensure_ascii=False, indent=2), "```"])

        result = tool.get("result") or tool.get("response")
        if result is not None:
            rendered = render_response_content(result)
            lines.extend(["", "**Result**", rendered or "> _No tool result returned._"])
        else:
            lines.extend(["", "**Result**", "> _No tool result returned._"])

    return lines


def render_followups(request: Dict[str, Any]) -> List[str]:
    followups = request.get("followups")
    if not isinstance(followups, list) or not followups:
        return []
    lines = ["", "#### Suggested follow-ups", ""]
    for followup in followups:
        if isinstance(followup, dict):
            message = followup.get("message") or followup.get("text")
        else:
            message = followup
        rendered = render_response_content(message)
        if rendered:
            lines.append(f"- {rendered}")
    return lines


def _normalize_for_fingerprint(text: str) -> str:
    # Lowercase and normalize common variable parts (paths, URIs, UUIDs/hex, numbers)
    s = text.lower()
    # Remove seen markers if present (even when followed by cross-session context)
    s = re.sub(r"\s+—\s+seen before \(\d+×\)", "", s)
    s = re.sub(r"\s+—\s+seen across \d+ sessions \(\d+× total\)", "", s)
    # Normalize file URIs
    s = re.sub(r"file:\/\/[^\s)]+", "<uri>", s)
    # Normalize windows/unix paths
    s = re.sub(r"[a-z]:[\\/][^\s\"]+", "<path>", s)
    s = re.sub(r"\b\/[\w\-\.\/]+", "<path>", s)
    # Normalize long hex/uuids
    s = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", s)
    # Collapse numbers
    s = re.sub(r"\d+", "#", s)
    # Whitespace collapse
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _segment_action_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """Return (start_index, end_index_exclusive) for each Actions block based on title line pattern.

    Blocks start with lines like: **Title** — summary
    and continue until a blank line or end.
    """
    indices: List[Tuple[int, int]] = []
    i = 0
    n = len(lines)
    title_re = re.compile(r"^\*\*[^*]+\*\*\s+—\s+.*")
    while i < n:
        if title_re.match(lines[i] or ""):
            start = i
            i += 1
            while i < n and (lines[i].strip() != ""):
                i += 1
            indices.append((start, i))
        else:
            i += 1
    return indices


def _annotate_seen(
    lines: List[str],
    seen: Dict[str, int],
    cross_stats: Optional[Dict[str, Tuple[int, int]]] = None,
    *,
    similarity_threshold_value: float,
) -> List[str]:
    if not lines:
        return lines
    blocks = _segment_action_blocks(lines)
    if not blocks:
        return lines
    out = lines[:]
    for start, end in blocks:
        block_text = "\n".join(out[start:end])
        fp = _normalize_for_fingerprint(block_text)
        prev = seen.get(fp, 0)
        seen[fp] = prev + 1
        if prev > 0:
            total_occurrences = prev + 1
            similarity_score = similarity_threshold_module.similarity_score_from_occurrence(total_occurrences)
            if similarity_score >= similarity_threshold_value:
                out[start] = (
                    out[start]
                    + f"  — Seen before ({prev}× prior, similarity={similarity_score:.2f} ≥ {similarity_threshold_value:.2f})"
                )
        if cross_stats is not None:
            sess_total = cross_stats.get(fp)
            if sess_total:
                sess_count, total_count = sess_total
                similarity_score = similarity_threshold_module.similarity_score_from_occurrence(total_count)
                if similarity_score >= similarity_threshold_value and "Seen across" not in out[start]:
                    out[start] = (
                        out[start]
                        + f"  — Seen across {sess_count} sessions ({total_count}× total, similarity={similarity_score:.2f} ≥ {similarity_threshold_value:.2f})"
                    )
    return out


def _extract_actions_blocks_from_lines(all_lines: List[str]) -> List[str]:
    """Return only the lines within all Actions sections from a full markdown transcript."""
    actions_only: List[str] = []
    within_actions = False
    for line in all_lines:
        if line.strip() == "#### Actions":
            within_actions = True
            continue
        if within_actions and line.startswith("### "):
            within_actions = False
        if within_actions:
            actions_only.append(line)
    return actions_only


def _build_cross_session_counts(exports_dir: Path) -> Dict[str, Tuple[int, int]]:
    """Scan prior exports to compute cross-session motif counts.

    Returns a mapping from action fingerprint to (unique_session_count, total_occurrences).
    """
    session_sets: Dict[str, set] = {}
    totals: Dict[str, int] = {}

    if not exports_dir.exists() or not exports_dir.is_dir():
        return {}

    for md_path in exports_dir.glob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        # Parse session id from header, if present
        session_id = None
        if lines:
            first = lines[0].strip()
            if first.startswith("# Copilot Chat Session"):
                # Expect "# Copilot Chat Session — <id>"
                parts = first.split("—", 1)
                if len(parts) == 2:
                    session_id = parts[1].strip()
        # Fallback to filename stem if header absent
        if not session_id:
            session_id = md_path.stem

        actions_only = _extract_actions_blocks_from_lines(lines)
        blocks = _segment_action_blocks(actions_only)
        for start, end in blocks:
            block_text = "\n".join(actions_only[start:end])
            fp = _normalize_for_fingerprint(block_text)
            totals[fp] = totals.get(fp, 0) + 1
            s = session_sets.get(fp)
            if s is None:
                s = set()
                session_sets[fp] = s
            s.add(session_id)

    cross: Dict[str, Tuple[int, int]] = {}
    for fp, s in session_sets.items():
        cross[fp] = (len(s), totals.get(fp, 0))
    return cross


def render_turn(
    request: Request,
    *,
    include_status: bool,
    include_raw_actions: bool,
    _seen_state: Optional[Dict[str, int]] = None,
    _cross_stats: Optional[Dict[str, Tuple[int, int]]] = None,
    _status_label: Optional[str] = None,
    _similarity_threshold: Optional[float] = None,
) -> List[str]:
    # Inject actions from response text if they're embedded as JSON
    request = inject_actions_into_request(request)
    
    lines: List[str] = ["### USER"]

    user_message = render_message_text(request.get("message"))
    if user_message:
        lines.extend(["", user_message])
    else:
        lines.extend(["", "_No user prompt recorded._"])

    timestamp = ms_to_iso(request.get("timestamp"))
    if timestamp:
        lines.extend(["", f"> _Timestamp_: {timestamp}"])

    references = collect_references(request)
    if references:
        lines.extend(["", "#### References", "", *[f"- {ref}" for ref in references]])

    lines.extend(["", "### Copilot"])
    response = render_response_content(request.get("response"))
    if response:
        lines.extend(["", response])
    else:
        lines.extend(["", "> _No assistant response recorded._"])

    result = request.get("result")
    if isinstance(result, dict):
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata_clean = prune_keys(metadata, SENSITIVE_METADATA_KEYS)

            thinking = render_thinking_block(metadata_clean)
            if thinking:
                lines.extend(["", thinking])

            rendered_actions: RenderedActions = render_actions(
                metadata_clean.get("messages") or [], include_raw=include_raw_actions
            )
            action_lines = rendered_actions.lines
            if action_lines and _seen_state is not None and not include_raw_actions:
                threshold_value = (
                    _similarity_threshold
                    if _similarity_threshold is not None
                    else similarity_threshold_module.FALLBACK_THRESHOLD
                )
                action_lines = _annotate_seen(
                    action_lines,
                    _seen_state,
                    _cross_stats,
                    similarity_threshold_value=threshold_value,
                )
            if action_lines:
                counts = rendered_actions.counts
                if counts:
                    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                    summary_bits = [f"{k} {v}" for k, v in ordered]
                    if _status_label and _status_label not in {"OK", ""}:
                        summary_bits.append(f"Status: {_status_label}")
                    lines.extend(["", f"> _Actions this turn_: " + " · ".join(summary_bits)])

                lines.extend(["", "#### Actions", ""])
                if _status_label in {"Canceled", "Terminated"}:
                    lines.extend([f"_Status: {_status_label}_", ""])
                lines.extend(action_lines)

            tool_lines = render_tool_invocations(metadata_clean)
            if tool_lines:
                lines.extend(tool_lines)

        if include_status:
            error_details = result.get("errorDetails")
            if isinstance(error_details, dict):
                status = error_details.get("message") or str(error_details)
                if status:
                    lines.extend(["", f"> _Status_: {status}"])

    lines.extend(render_followups(request))

    if request.get("isCanceled"):
        lines.extend(["", "> _Request marked as cancelled._"])

    return squeeze(lines)


def _render_lod0_transcript(session: Dict[str, Any]) -> str:
    requests = session.get("requests")
    if not isinstance(requests, list) or not requests:
        return ""

    user_label = (
        session.get("requesterDisplayName")
        or session.get("requesterUsername")
        or session.get("requester")
        or "USER"
    )
    assistant_label = (
        session.get("responderDisplayName")
        or session.get("responderUsername")
        or "GitHub Copilot"
    )

    lines: List[str] = []
    for request in requests:
        if not isinstance(request, dict):
            continue

        user_text = render_message_text(request.get("message"))
        if user_text:
            collapsed_user = _collapse_structured_blocks(user_text)
            lines.append(f"{user_label}: {collapsed_user}")
            lines.append("")

        response_text = render_response_content(request.get("response"))
        if response_text:
            collapsed_response = _collapse_structured_blocks(response_text)
            lines.append(f"{assistant_label}: {collapsed_response}")
            lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def render_session_markdown(
    session: Dict[str, Any],
    *,
    include_status: bool,
    include_raw_actions: bool = False,
    cross_session_dir: Optional[Path] = None,
    lod_level: Optional[int] = None,
    similarity_threshold: Optional[float] = None,
) -> str:
    if lod_level == 0:
        lod0 = _render_lod0_transcript(session)
        if lod0:
            return lod0
    session_id = session.get("sessionId") or "unknown-session"
    requester = session.get("requesterUsername")
    responder = session.get("responderUsername") or "GitHub Copilot"
    created = ms_to_iso(session.get("creationDate"))
    last = ms_to_iso(session.get("lastMessageDate"))
    location = session.get("initialLocation")
    workspace_key = session.get("workspaceKey")

    header: List[str] = [f"# Copilot Chat Session — {session_id}", ""]
    metadata_lines = [
        f"- Requester: {requester}" if requester else None,
        f"- Responder: {responder}" if responder else None,
        f"- Initial location: {location}" if location else None,
        f"- Workspace: {workspace_key}" if workspace_key else None,
        f"- Created: {created}" if created else None,
        f"- Last message: {last}" if last else None,
    ]
    header.extend(filter(None, metadata_lines))

    requests = session.get("requests")
    if not isinstance(requests, list) or not requests:
        header.extend(["", "_No conversation turns stored in this session._"])
        return "\n".join(header)

    transcript: List[str] = header

    # Track seen action fingerprints across the whole session for Seen-before annotations
    seen_state: Dict[str, int] = {}
    # Cross-session counts (optional)
    cross_stats: Optional[Dict[str, Tuple[int, int]]] = None
    if cross_session_dir is not None:
        try:
            cross_stats = _build_cross_session_counts(cross_session_dir)
        except Exception:
            cross_stats = None

    if similarity_threshold is None:
        try:
            session_similarity_threshold = similarity_threshold_module.compute_similarity_threshold(
                CATALOG_DB_PATH
            ).threshold
        except Exception:
            session_similarity_threshold = similarity_threshold_module.FALLBACK_THRESHOLD
    else:
        session_similarity_threshold = max(0.0, min(1.0, similarity_threshold))

    # Track status counts across the session
    status_counts: Dict[str, int] = {"Canceled": 0, "Terminated": 0, "Error": 0, "No response": 0, "OK": 0}

    def _classify_status(req: Request) -> str:
        # Canceled via request flag
        try:
            if req.get("isCanceled"):
                return "Canceled"
        except Exception:
            pass
        result = req.get("result")
        response = req.get("response")
        # Missing response
        if response is None and not isinstance(result, dict):
            return "No response"
        # Error details present
        if isinstance(result, dict):
            err = result.get("errorDetails")
            if err is not None:
                text = str(err).lower()
                if any(k in text for k in ("cancel", "cancelled", "canceled")):
                    return "Canceled"
                if any(k in text for k in ("terminate", "timeout", "abort")):
                    return "Terminated"
                return "Error"
        return "OK"

    for index, request in enumerate(requests, start=1):
        if not isinstance(request, dict):
            continue
        transcript.extend(["", f"## Turn {index}"])
        status_label = _classify_status(request)
        status_counts[status_label] = status_counts.get(status_label, 0) + 1
        transcript.extend(
            render_turn(
                request,
                include_status=include_status,
                include_raw_actions=include_raw_actions,
                _seen_state=seen_state,
                _cross_stats=cross_stats,
                _status_label=status_label,
                _similarity_threshold=session_similarity_threshold,
            )
        )
    # Inject a Motifs (repeats) section near the top if there are repeated motifs
    lines = squeeze(transcript)

    # Collect actions lines across transcript within Actions sections only
    actions_only: List[str] = _extract_actions_blocks_from_lines(lines)

    # Reuse block segmentation to group action title blocks
    blocks = _segment_action_blocks(actions_only)
    motif_counts: Dict[str, Tuple[int, str]] = {}
    for start, end in blocks:
        first_line = actions_only[start]
        fp = _normalize_for_fingerprint(first_line)
        count, exemplar = motif_counts.get(fp, (0, first_line))
        motif_counts[fp] = (count + 1, exemplar)

    repeats = [
        (c, l)
        for fp, (c, l) in motif_counts.items()
        if c > 1 and similarity_threshold_module.similarity_score_from_occurrence(c) >= session_similarity_threshold
    ]
    repeats.sort(reverse=True)

    # Build an overall action-type summary across the session
    title_counts: Dict[str, int] = {}
    title_re = re.compile(r"^\*\*(?P<title>[^*]+)\*\*")
    for start, _ in blocks:
        m = title_re.match(actions_only[start])
        if m:
            t = m.group("title").strip()
            if t:
                title_counts[t] = title_counts.get(t, 0) + 1

    summary_section: List[str] = []
    if title_counts and not include_raw_actions:
        ordered = sorted(title_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        summary_bits = [f"{k} {v}" for k, v in ordered]
        summary_section = ["", "## Actions summary", "", "- " + " · ".join(summary_bits)]

    # Build overall status summary (include even if no actions)
    status_section: List[str] = []
    if not include_raw_actions:
        # Only include non-zero statuses other than OK unless OK is the only class
        nonzero = {k: v for k, v in status_counts.items() if v > 0}
        if nonzero:
            # Prefer to suppress OK if others present
            items = [(k, v) for k, v in nonzero.items() if k != "OK"]
            if not items:
                items = [("OK", nonzero.get("OK", 0))]
            ordered = sorted(items, key=lambda kv: (-kv[1], kv[0]))
            bits = [f"{k} {v}" for k, v in ordered]
            status_section = ["", "## Status summary", "", "- " + " · ".join(bits)]

    # Build sequence motifs (bigrams/trigrams of action titles)
    sequence_section: List[str] = []
    if not include_raw_actions and blocks:
        # Extract ordered action titles for the whole session
        title_re2 = re.compile(r"^\*\*(?P<title>[^*]+)\*\*")
        titles: List[str] = []
        for start, _ in blocks:
            m = title_re2.match(actions_only[start])
            if m:
                t = m.group("title").strip()
                if t:
                    titles.append(t)
        # Count bigrams and trigrams
        bigrams: Dict[Tuple[str, str], int] = {}
        trigrams: Dict[Tuple[str, str, str], int] = {}
        for i in range(len(titles) - 1):
            pair = (titles[i], titles[i + 1])
            bigrams[pair] = bigrams.get(pair, 0) + 1
        for i in range(len(titles) - 2):
            tri = (titles[i], titles[i + 1], titles[i + 2])
            trigrams[tri] = trigrams.get(tri, 0) + 1
        top_pairs = sorted(bigrams.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        top_tris = sorted(trigrams.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        if top_pairs or top_tris:
            sequence_section = ["", "## Sequence motifs", ""]
            if top_pairs:
                sequence_section.append("- Bigrams:")
                for (a, b), c in top_pairs:
                    sequence_section.append(f"  - {c}× — {a} → {b}")
            if top_tris:
                sequence_section.append("- Trigrams:")
                for (a, b, c), n in top_tris:
                    sequence_section.append(f"  - {n}× — {a} → {b} → {c}")

    if (repeats or summary_section or status_section or sequence_section) and not include_raw_actions:
        motif_section: List[str] = []
        if repeats:
            motif_section = ["", "## Motifs (repeats)", ""]
            for count, exemplar in repeats[:12]:
                motif_section.append(f"- {count}× — {exemplar}")

        insert_at = len(header)
        lines = lines[:insert_at] + summary_section + status_section + sequence_section + motif_section + lines[insert_at:]

    return "\n".join(lines) + "\n"
