"""Parse embedded JSON tool calls from response text and normalize to metadata.messages format."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


def extract_json_blocks(text: str) -> List[Dict[str, Any]]:
    """Extract JSON objects with 'kind' field from text.
    
    Handles both inline and multi-line JSON blocks that appear in VS Code
    chat response text.
    """
    extracted = []
    brace_depth = 0
    start_idx = None
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_depth == 0:
                start_idx = i
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0 and start_idx is not None:
                candidate = text[start_idx:i+1]
                try:
                    parsed = json.loads(candidate)
                    # Only accept objects that look like tool call metadata
                    if isinstance(parsed, dict) and 'kind' in parsed:
                        extracted.append(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
                start_idx = None
    
    return extracted


def clean_response_text(text: str, json_blocks: List[Dict[str, Any]]) -> str:
    """Remove JSON blocks from response text, leaving only human-readable content.
    
    Also removes standalone markdown headings that were wrapping tool calls.
    """
    if not json_blocks:
        return text
    
    # Remove each JSON block
    cleaned = text
    for block in json_blocks:
        # Serialize back to match original
        block_str = json.dumps(block, ensure_ascii=False, indent=2)
        # Also try without indentation for inline blocks
        block_str_inline = json.dumps(block, ensure_ascii=False)
        
        cleaned = cleaned.replace(block_str, '')
        cleaned = cleaned.replace(block_str_inline, '')
    
    # Remove standalone markdown headings that typically wrap tool calls
    # Pattern: **Some text** on its own line
    lines = cleaned.split('\n')
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just bold markdown (tool call wrappers)
        if stripped and stripped.startswith('**') and stripped.endswith('**'):
            # Check if it looks like a tool call annotation
            inner = stripped[2:-2]
            if any(keyword in inner.lower() for keyword in ['preparing', 'reviewing', 'checking', 'verifying']):
                continue
        filtered_lines.append(line)
    
    cleaned = '\n'.join(filtered_lines)
    
    # Clean up excessive blank lines
    while '\n\n\n' in cleaned:
        cleaned = cleaned.replace('\n\n\n', '\n\n')
    
    return cleaned.strip()


def normalize_response_with_actions(response: Any) -> Tuple[Any, List[Dict[str, Any]]]:
    """Extract tool call metadata from response and return cleaned response plus messages.

    Supports two cases observed in VS Code data:
    1) Tool-call JSON embedded inside string content of response parts
    2) Tool-call JSON provided as standalone dict items in the response list

    Returns:
        (cleaned_response, messages_array) where messages_array is suitable for
        metadata.messages in the export format.
    """
    messages: List[Dict[str, Any]] = []

    if isinstance(response, list):
        cleaned_responses: List[Any] = []
        for item in response:
            # Case 2: Standalone dict items that look like tool-call metadata
            if isinstance(item, dict) and ('kind' in item or 'toolSpecificData' in item):
                # Some dicts are plain text blocks (with 'value'), keep those below
                if 'kind' in item and not item.get('value'):
                    messages.append(item)
                    # Do not include in cleaned response to avoid duplication
                    continue

            if isinstance(item, dict):
                value = item.get('value', '')
                if isinstance(value, str) and value:
                    # Case 1: JSON embedded within a text block
                    json_blocks = extract_json_blocks(value)
                    if json_blocks:
                        messages.extend(json_blocks)
                        cleaned_value = clean_response_text(value, json_blocks)
                    else:
                        cleaned_value = value
                    # Preserve the textual portion if anything remains
                    if cleaned_value:
                        cleaned_item = item.copy()
                        cleaned_item['value'] = cleaned_value
                        cleaned_responses.append(cleaned_item)
                else:
                    # Non-text dict item that isn't a tool-call message; keep as-is
                    cleaned_responses.append(item)
            else:
                # Primitive types (strings already handled above; others rare)
                cleaned_responses.append(item)
        return cleaned_responses, messages

    elif isinstance(response, str):
        json_blocks = extract_json_blocks(response)
        messages.extend(json_blocks)
        cleaned = clean_response_text(response, json_blocks)
        return cleaned, messages

    return response, messages


def inject_actions_into_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Parse response text for JSON tool calls and inject into metadata.messages.
    
    This allows the existing pattern system to process tool calls even when
    VS Code stores them as JSON-in-text rather than structured metadata.
    """
    result = request.get('result')
    if not isinstance(result, dict):
        return request
    
    metadata = result.get('metadata')
    if not isinstance(metadata, dict):
        return request
    
    # Check if messages already populated (older format)
    existing_messages = metadata.get('messages')
    if existing_messages and len(existing_messages) > 0:
        return request  # Already has structured data
    
    # Extract from response text
    response = request.get('response')
    cleaned_response, extracted_messages = normalize_response_with_actions(response)
    
    if extracted_messages:
        # Make a copy to avoid mutating original
        request_copy = request.copy()
        result_copy = result.copy()
        metadata_copy = metadata.copy()
        
        # Inject normalized messages
        metadata_copy['messages'] = extracted_messages
        result_copy['metadata'] = metadata_copy
        request_copy['result'] = result_copy
        
        # Also clean the response text
        request_copy['response'] = cleaned_response
        
        return request_copy
    
    return request
