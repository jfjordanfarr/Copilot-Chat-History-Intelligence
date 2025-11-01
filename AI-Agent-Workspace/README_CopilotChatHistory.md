# Copilot Chat History Catalog

- Database file: `live_chat.db`
- Schema version: 2
- Views: `tool_call_details`, `prompt_activity`

## Purpose
This catalog normalizes Copilot Chat prompt logs so language models and analysts can query historical tool usage, timelines, and prompt content without bespoke parsing.

## Tables
- `prompts`: One row per chat prompt; contains text, origin file/kind classifiers, and raw JSON payload.
- `prompt_logs`: Entries tied to each prompt (requests, tool calls, elements).
- `tool_results`: Flattened tool outputs linked to tool-call log rows.
- `catalog_metadata`: Key/value metadata about the catalog build.

## Views
- `tool_call_details`: Joins prompts, logs, and tool outputs for direct inspection of tool calls.
- `prompt_activity`: Aggregates how many entries of each kind appear per prompt.

## Sample Queries
```sql
SELECT prompt_id, prompt_text
FROM prompts
ORDER BY imported_at DESC
LIMIT 5;

SELECT prompt_text, summary, tool_content
FROM tool_call_details
WHERE tool_content IS NOT NULL
ORDER BY imported_at DESC
LIMIT 5;

SELECT p.prompt_text, l.summary
FROM prompt_logs l
JOIN prompts p ON p.prompt_id = l.prompt_id
WHERE l.kind = 'request'
ORDER BY l.time DESC
LIMIT 10;

SELECT kind, COUNT(*) AS total
FROM prompt_logs
GROUP BY kind
ORDER BY total DESC;
```

## LLM Prompting Tips
1. Ask the model to read this README first so it understands the table relationships.
2. Encourage use of the `tool_call_details` view for most tool analytics.
3. Remind the model that timestamps are stored as text in ISO-8601 format.
4. For large result sets, add `LIMIT` clauses to keep outputs manageable.

## Regeneration
Run `python script/chat_logs_to_sqlite.py` to refresh the catalog after exporting new prompt logs or mirroring live data.

## Schema Change Log

- v1 (2025-10-18)
  - Initial catalog with prompts, prompt_logs, tool_results tables, and helper views.
- v2 (2025-10-22)
  - Added source_kind classifier to prompts for downstream filtering.
  - Introduced schema migration runner for forward-compatible upgrades.

