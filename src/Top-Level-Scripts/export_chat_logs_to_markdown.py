"""Utility to convert Copilot chat debug logs (``*.chatreplay.json`` files
exported via the chat debug view) into a Markdown transcript.

The script looks for exported chat logs in either a user-supplied location or the
common VS Code global storage folders. When multiple logs or prompts are found it
interactively lets the user pick one, then emits Copy-All-style Markdown.

Example usage (prints to stdout):
    python export_chat_logs_to_markdown.py
    python export_chat_logs_to_markdown.py path/to/log.chatreplay.json

Example usage (writes to file):
    python export_chat_logs_to_markdown.py path/to/logs -o transcript.md

The output aims to match the formatting produced by the in-editor exporter,
including tool call summaries, arguments, results, and non-success status notes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


CHATREPLAY_EXTENSION = ".chatreplay.json"
DEFAULT_PROMPT_SLUG = "copilot_chat_prompt"


class UserVisibleError(RuntimeError):
	"""Raised when the script should print a friendly error message."""


def default_storage_dirs() -> Sequence[Path]:
	dirs: List[Path] = []
	platform = sys.platform
	user_home = Path.home()

	if platform.startswith("win"):
		appdata = os.getenv("APPDATA")
		if appdata:
			base = Path(appdata)
			dirs.extend([
				base / "Code" / "User" / "globalStorage" / "github.copilot-chat",
				base / "Code - Insiders" / "User" / "globalStorage" / "github.copilot-chat",
				base / "Code - OSS" / "User" / "globalStorage" / "github.copilot-chat",
			])
	elif platform == "darwin":
		base = user_home / "Library" / "Application Support"
		dirs.extend([
			base / "Code" / "User" / "globalStorage" / "github.copilot-chat",
			base / "Code - Insiders" / "User" / "globalStorage" / "github.copilot-chat",
			base / "Code - OSS" / "User" / "globalStorage" / "github.copilot-chat",
		])
	else:
		dirs.extend([
			user_home / ".config" / "Code" / "User" / "globalStorage" / "github.copilot-chat",
			user_home / ".config" / "Code - Insiders" / "User" / "globalStorage" / "github.copilot-chat",
			user_home / ".config" / "Code - OSS" / "User" / "globalStorage" / "github.copilot-chat",
		])

	return [path for path in dirs if path.exists()]


def discover_chatreplay_files(target: Optional[Path]) -> List[Path]:
	"""Return possible chat replay JSON files ordered by recency."""

	candidates: List[Path] = []

	def add_candidate(path: Path) -> None:
		if path.is_file() and path.name.endswith(CHATREPLAY_EXTENSION):
			candidates.append(path)

	if target:
		target = target.expanduser()
		if target.is_file():
			add_candidate(target)
		elif target.is_dir():
			for item in target.rglob(f"*{CHATREPLAY_EXTENSION}"):
				add_candidate(item)
		else:
			raise UserVisibleError(f"No such file or directory: {target}")
	else:
		for directory in default_storage_dirs():
			for item in directory.rglob(f"*{CHATREPLAY_EXTENSION}"):
				add_candidate(item)

	unique: List[Path] = []
	seen = set()
	for path in candidates:
		try:
			resolved = path.resolve()
		except OSError:
			# Fall back to original path if resolving fails (e.g., permissions)
			resolved = path
		if resolved not in seen:
			seen.add(resolved)
			unique.append(resolved)

	try:
		unique.sort(key=lambda p: p.stat().st_mtime, reverse=True)
	except OSError:
		# If stat fails for some path, leave order as-is.
		pass

	return unique


def choose_item(items: Sequence[Any], formatter, noun: str) -> Any:
	if not items:
		raise UserVisibleError(f"No {noun}s are available.")
	if len(items) == 1:
		return items[0]

	print(f"Found {len(items)} {noun}s:")
	for index, item in enumerate(items, start=1):
		print(f"  [{index}] {formatter(item)}")

	while True:
		try:
			choice = input(f"Select {noun} [1-{len(items)}] (default 1): ").strip()
		except EOFError:
			choice = ""
		except KeyboardInterrupt:
			print("\nCancelled.")
			sys.exit(1)

		if not choice:
			return items[0]
		if choice.isdigit():
			position = int(choice)
			if 1 <= position <= len(items):
				return items[position - 1]
		print("Please enter a valid number within range.")


def describe_file(path: Path) -> str:
	try:
		mtime = datetime.fromtimestamp(path.stat().st_mtime)
		timestamp = mtime.strftime("%Y-%m-%d %H:%M")
	except OSError:
		timestamp = "unknown time"
	return f"{path.name} — {timestamp}"


def load_prompts(file_path: Path) -> List[Dict[str, Any]]:
	with file_path.open("r", encoding="utf-8") as handle:
		data = json.load(handle)

	if isinstance(data, dict) and isinstance(data.get("prompts"), list):
		prompts = [item for item in data["prompts"] if isinstance(item, dict)]
	elif isinstance(data, list):
		prompts = [item for item in data if isinstance(item, dict)]
	elif isinstance(data, dict):
		prompts = [data]
	else:
		raise UserVisibleError("Unrecognized chat replay JSON format.")

	if not prompts:
		raise UserVisibleError("The selected log did not contain any prompt entries.")

	return prompts


def summarize_prompt(prompt: Dict[str, Any]) -> str:
	prompt_text = str(prompt.get("prompt") or "").strip()
	if not prompt_text:
		prompt_text = "<empty prompt>"
	first_line = prompt_text.splitlines()[0]
	summary = textwrap.shorten(first_line, width=80, placeholder="…")
	log_count = prompt.get("logCount")
	if isinstance(log_count, int):
		summary += f" ({log_count} log entries)"
	return summary


def slugify_prompt(prompt: Dict[str, Any]) -> str:
	prompt_text = str(prompt.get("prompt") or DEFAULT_PROMPT_SLUG).strip()
	if not prompt_text:
		prompt_text = DEFAULT_PROMPT_SLUG
	first_line = prompt_text.splitlines()[0]
	slug = re.sub(r"[^A-Za-z0-9\-_.]+", "_", first_line)
	slug = slug.strip("._")
	return slug[:60] if slug else DEFAULT_PROMPT_SLUG


def normalize_text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return value.strip()
	if isinstance(value, list):
		parts = [normalize_text(part) for part in value]
		return "\n".join(part for part in parts if part)
	if isinstance(value, dict):
		for key in ("text", "content", "value"):
			candidate = value.get(key)
			if isinstance(candidate, str):
				return candidate.strip()
		image_url = value.get("imageUrl") or value.get("image_url")
		if isinstance(image_url, dict):
			image_url = image_url.get("url")
		if isinstance(image_url, str) and image_url:
			return f"![image]({image_url})"
	return str(value)


def prettify_json(value: Any) -> Optional[str]:
	if value is None:
		return None
	if isinstance(value, str):
		candidate = value.strip()
		if not candidate:
			return None
		try:
			parsed = json.loads(candidate)
		except json.JSONDecodeError:
			return candidate
		else:
			return json.dumps(parsed, indent=2, ensure_ascii=False)
	try:
		return json.dumps(value, indent=2, ensure_ascii=False)
	except (TypeError, ValueError):
		return str(value)


def format_response_content(content: Any) -> str:
	if content is None:
		return ""
	if isinstance(content, (str, int, float)):
		return str(content).strip()
	if isinstance(content, list):
		parts = [format_response_content(part) for part in content]
		parts = [part for part in parts if part]
		return "\n\n".join(parts)
	if isinstance(content, dict):
		for key in ("message", "text", "content", "value"):
			candidate = content.get(key)
			if isinstance(candidate, str):
				return candidate.strip()
			if isinstance(candidate, list):
				return format_response_content(candidate)
		image_url = content.get("imageUrl") or content.get("image_url")
		if isinstance(image_url, dict):
			image_url = image_url.get("url")
		if isinstance(image_url, str) and image_url:
			return f"![image]({image_url})"
		pretty = prettify_json(content)
		return pretty or ""
	return str(content)


def render_thinking(thinking: Dict[str, Any]) -> Optional[str]:
	if not isinstance(thinking, dict):
		return None
	text = normalize_text(thinking.get("text"))
	if not text:
		return None
	lines = ["> _Thinking_"]
	identifier = thinking.get("id")
	if isinstance(identifier, str) and identifier:
		lines.append(f"> id: {identifier}")
	for line in text.splitlines():
		lines.append(f"> {line}" if line else ">")
	return "\n".join(lines)


def render_tool_call(log: Dict[str, Any]) -> List[str]:
	lines: List[str] = ["", f"#### Tool call: {log.get('tool') or log.get('name') or 'Unknown tool'}"]

	pretty_args = prettify_json(log.get("args"))
	if pretty_args:
		lines.extend(["", "**Arguments**", "```json", pretty_args, "```"])

	thinking_block = render_thinking(log.get("thinking"))
	if thinking_block:
		lines.extend(["", thinking_block])

	lines.extend(["", "**Result**"])
	result_content = log.get("response")
	result_text = format_response_content(result_content)
	if result_text:
		lines.append(result_text)
	else:
		lines.append("> _No tool result returned._")

	edits = log.get("edits")
	if isinstance(edits, list) and edits:
		lines.extend(["", "**Edits**"])
		for entry in edits:
			if not isinstance(entry, dict):
				continue
			path = entry.get("path")
			lines.append(f"- `{path}`" if path else "- (unknown path)")
			pretty_edit = prettify_json(entry.get("edits"))
			if pretty_edit:
				lines.extend(["", "```json", pretty_edit, "```"])

	return lines


def render_element(log: Dict[str, Any]) -> List[str]:
	name = log.get("name") or "Element"
	tokens = log.get("tokens")
	max_tokens = log.get("maxTokens")
	details: List[str] = []
	if isinstance(tokens, (int, float)):
		details.append(f"tokens={tokens}")
	if isinstance(max_tokens, (int, float)):
		details.append(f"maxTokens={max_tokens}")
	detail_text = f" ({', '.join(details)})" if details else ""
	return ["", f"#### Prompt element: {name}{detail_text}"]


def render_request(log: Dict[str, Any], *, include_status: bool) -> List[str]:
	lines: List[str] = []
	response = log.get("response") or {}
	message = response.get("message") if isinstance(response, dict) else None
	response_text = format_response_content(message if message is not None else response)

	if response_text:
		lines.extend(["", response_text])
	else:
		lines.extend(["", "> _No assistant response recorded._"])

	if include_status and isinstance(response, dict):
		status_type = response.get("type")
		if status_type and status_type not in {"success", "completion"}:
			status_nice = status_type.replace("_", " ")
			reason = response.get("reason")
			if isinstance(reason, str) and reason:
				status_nice += f" — {reason}"
			lines.extend(["", f"> _Status_: {status_nice}"])
	return lines


def render_unknown(log: Dict[str, Any]) -> List[str]:
	pretty = prettify_json(log)
	return ["", pretty or str(log)]


def squeeze_blank_lines(lines: Iterable[str]) -> List[str]:
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


def render_prompt_to_markdown(prompt: Dict[str, Any], *, include_status: bool = True) -> str:
	lines: List[str] = ["### USER"]
	user_message = str(prompt.get("prompt") or "").strip()
	if user_message:
		lines.extend(["", user_message])
	else:
		lines.extend(["", "_No user prompt recorded._"])

	references = prompt.get("references")
	if isinstance(references, list) and references:
		rendered_refs = []
		for entry in references:
			if isinstance(entry, dict):
				label = entry.get("label")
				value = entry.get("value") or entry.get("uri")
				parts = [part for part in (label, value) if part]
				if parts:
					rendered_refs.append(" — ".join(parts))
			elif isinstance(entry, str):
				rendered_refs.append(entry)
		if rendered_refs:
			lines.extend(["", "#### References", "", *[f"- {ref}" for ref in rendered_refs]])

	lines.extend(["", "### Copilot"])

	logs = prompt.get("logs")
	if not isinstance(logs, list) or not logs:
		lines.extend(["", "> _No log entries captured for this prompt._"])
		return "\n".join(lines)

	for log in logs:
		if not isinstance(log, dict):
			continue
		kind = log.get("kind")
		if kind == "toolCall":
			lines.extend(render_tool_call(log))
		elif kind == "request":
			lines.extend(render_request(log, include_status=include_status))
		elif kind == "element":
			lines.extend(render_element(log))
		else:
			lines.extend(render_unknown(log))

	return "\n".join(squeeze_blank_lines(lines))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Convert Copilot chat logs (.chatreplay.json) to Markdown conversation transcripts.")
	parser.add_argument("path", nargs="?", help="Path to a .chatreplay.json file or a directory to scan.")
	parser.add_argument("-o", "--output", help="Optional file to write the Markdown transcript to. If the path is a directory, a filename is generated automatically.")
	parser.add_argument("--prompt-index", type=int, help="1-based index of the prompt to export (skips interactive selection).")
	parser.add_argument("--status", action="store_true", help="Include non-success completion statuses (matches the VS Code exporter).")
	return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
	args = parse_args(argv)

	target_path = Path(args.path).expanduser() if args.path else None

	files = discover_chatreplay_files(target_path)
	if not files:
		raise UserVisibleError(
			"No .chatreplay.json files were found. Use the Copilot Chat debug view to export prompt logs first."
		)

	selected_file = files[0]
	if len(files) > 1 and not (args.prompt_index and target_path and target_path.is_file()):
		selected_file = choose_item(files, describe_file, "chat log file")

	prompts = load_prompts(selected_file)

	if args.prompt_index:
		index = args.prompt_index - 1
		if not 0 <= index < len(prompts):
			raise UserVisibleError(
				f"Prompt index {args.prompt_index} is out of range (1-{len(prompts)})."
			)
		selected_prompt = prompts[index]
	else:
		selected_prompt = choose_item(prompts, summarize_prompt, "prompt") if len(prompts) > 1 else prompts[0]

	markdown = render_prompt_to_markdown(selected_prompt, include_status=args.status)

	if args.output:
		output_path = Path(args.output).expanduser()
		if output_path.exists() and output_path.is_dir():
			output_path = output_path / f"{slugify_prompt(selected_prompt)}.md"
		output_path.parent.mkdir(parents=True, exist_ok=True)
		output_path.write_text(markdown, encoding="utf-8")
		print(f"Wrote Markdown transcript to {output_path}")
	else:
		print(markdown)


if __name__ == "__main__":
	try:
		main()
	except UserVisibleError as exc:
		print(f"Error: {exc}", file=sys.stderr)
		sys.exit(1)
	except KeyboardInterrupt:
		print("\nCancelled.")
		sys.exit(1)
