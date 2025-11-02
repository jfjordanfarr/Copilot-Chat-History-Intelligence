# Data Model — Copilot Recall Vision

We align the schema with the raw Copilot chat JSON harvested from `%APPDATA%/Code/User/globalStorage` and layer on top the minimum extras needed for telemetry-inspired analytics. Three tiers keep the design explainable: raw session capture, normalized catalog tables, and optional Agent Lightning–style telemetry.

## 1. Raw Session Layer (verbatim from JSON)

### ChatSessionRaw
- **Fields**:
  - `version`: Schema version integer.
  - `sessionId`: UUID string.
  - `requesterUsername`, `responderUsername`: GitHub handles.
  - `requesterAvatarIconUri`, `responderAvatarIconUri`: URI blobs.
  - `initialLocation`: Enum (`panel`, `inline`, `chat-scope`).
  - `creationDate`, `lastMessageDate`: Unix epoch millis.
  - `customTitle`: Optional string.
  - `isImported`: Boolean.
  - `requests`: Array of `RequestRaw` objects.

### RequestRaw
- **Fields**:
  - `requestId`: Stable id (`request_<uuid>`).
  - `message`: Aggregate prompt text plus `parts` (array of `MessagePartRaw`).
  - `variableData`: Optional `VariableBindingRaw` list.
  - `response`: Array of `ResponseRaw` payloads.
  - `responseId`: Upstream response identifier.
  - `result`: `ResultMetadataRaw` block containing timings, model ids, and chat transcript.
  - `followups`: Suggested follow-up prompts.
  - `isCanceled`: Boolean.
  - `agent`: `AgentDescriptorRaw` describing the responding agent.
  - `contentReferences`: Optional list of editor selections.
  - `codeCitations`: Optional list tying outputs to URIs (empty in sampled logs but preserved).
  - `timestamp`: Epoch millis when the request completed.

### MessagePartRaw
- `kind`: (`text`, `code`, `markdown`).
- `text`: Literal content.
- `range`: Raw document offsets.
- `editorRange`: VS Code selection metadata.

### VariableBindingRaw
- `id`: Identifier such as `vscode.implicit.selection`.
- `name`: Human-readable label.
- `value`: Arbitrary JSON (URIs, ranges, scalars).
- `isFile`: Boolean.
- `modelDescription`: String injected into the agent prompt.

### ResponseRaw
- `value`: Markdown/text returned to the UI.
- `supportThemeIcons`, `supportHtml`: Booleans.

### ResultMetadataRaw
- `timings`: `{firstProgress, totalElapsed}` in milliseconds.
- `metadata`: Nested object containing:
  - `messages`: Ordered transcript (`role`, `content`).
  - `modelMessageId`, `responseId`, `sessionId`, `agentId`.
  - `codeBlocks`: Optional array of structured outputs.

### FollowupRaw
- `kind`: (`reply`, `command`).
- `agentId`: Suggested handler.
- `message`: Prompt text.

### AgentDescriptorRaw
- `extensionId`, `publisherDisplayName`, `extensionDisplayName`, `id`.
- Metadata blob with help text, trusted commands, welcome message.
- `name`, `fullName`, `isDefault`, `locations`, `slashCommands`, `disambiguation` hints.

### ContentReferenceRaw
- `kind`: (`reference`).
- `reference.uri`: VS Code URI metadata.
- `reference.range`: Range in the referenced document.

### CodeCitationRaw
- Reserved for future evidence linking; presently captured as empty arrays.

## 2. Normalized Catalog Layer (SQLite)

### Table: `chat_sessions`
- `session_id` (PK)
- `version`
- `requester_username`, `responder_username`
- `initial_location`
- `creation_date_ms`, `last_message_date_ms`
- `custom_title` (nullable)
- `is_imported` (integer boolean)
- `raw_json` (lossless copy)
- Index on (`last_message_date_ms DESC`, `initial_location`)

### Table: `requests`
- `request_id` (PK)
- `session_id` (FK `chat_sessions.session_id`)
- `timestamp_ms`
- `prompt_text` (denormalized from `message.text`)
- `response_id` (nullable)
- `agent_id`
- `is_canceled` (integer boolean)
- `timing_first_progress_ms`, `timing_total_ms`
- `result_metadata_json`

### Table: `request_parts`
- Composite key (`request_id`, `part_index`)
- `kind`
- `text`
- `range_json`
- `editor_range_json`

### Table: `request_variables`
- Composite key (`request_id`, `variable_id`)
- `name`
- `value_json`
- `is_file`
- `model_description`

### Table: `responses`
- Composite key (`request_id`, `response_index`)
- `value`
- `supports_html`
- `supports_theme_icons`

### Table: `result_messages`
- Composite key (`request_id`, `message_index`)
- `role`
- `content`

### Table: `followups`
- Composite key (`request_id`, `followup_index`)
- `kind`
- `agent_id`
- `message`

### Table: `agents`
- `agent_id` (PK)
- `session_id` (last observed session)
- `descriptor_json`
- `is_default`
- `locations_json`

### Table: `content_references`
- Composite key (`request_id`, `reference_index`)
- `uri_json`
- `range_json`

### Table: `code_citations`
- Composite key (`request_id`, `citation_index`)
- `citation_json`

### Table: `tool_outputs`
- `request_id`
- `tool_kind`
- `payload_json`
- Captures future entries from `result.metadata.codeBlocks` or tool spans.

### Table: `metrics_repeat_failures`
- Composite key (`workspace_fingerprint`, `command_hash`, `exit_code`)
- `request_id` (FK `requests.request_id`)
- `occurrence_count` (integer)
- `first_seen_ms`, `last_seen_ms`
- `sample_snippet`
- `redacted_payload_json`
- Supports SC-004/FR-008 telemetry while keeping evidence anonymized.

### Planned materialized views
- `vw_request_summary`: quick recall over sessions, requests, responses.
- `vw_variable_usage`: audits implicit selections and file bindings.
- `vw_followup_recurrence`: surfaces recurring follow-up prompts for motif mining.

## 3. Telemetry Extensions (Agent Lightning Inspired)

Raw Copilot JSON lacks traces, but we reserve optional tables that harmonize with Agent Lightning once sidecar telemetry is available.

### Table: `rollouts`
- `rollout_id` (PK)
- `session_id` (FK)
- `resource_version_hash`
- `dataset_origin`
- `created_at_ms`

### Table: `attempts`
- Composite key (`rollout_id`, `attempt_id`)
- `status`
- `started_at_ms`, `ended_at_ms`
- `failure_class` (nullable)
- `reward_final` (real, nullable)
- Optional `request_id` FK for provenance.

### Table: `telemetry_spans`
- `span_id` (PK)
- `attempt_id` (FK `attempts`)
- `trace_id`, `parent_span_id`
- `sequence_id` (integer; mirrors Agent Lightning ordering)
- `name`, `span_kind`
- `start_time_ns`, `end_time_ns`
- `status_code`, `status_message`
- `attributes_json`
- Index on (`attempt_id`, `sequence_id`)

### Table: `reward_signals`
- Composite key (`attempt_id`, `reward_index`)
- `span_id` (FK `telemetry_spans`)
- `value` (real)
- `reward_kind`
- `notes` (nullable)

### Table: `transition_tuples`
- `tuple_id` (PK)
- `attempt_id` (FK)
- `state_ref`, `action_ref`, `reward_ref`, `next_state_ref`
- `adapter_version`

### Table: `instrumentation_sources`
- `instrumentation_id` (PK)
- `name`, `version`
- `config_json`
- `is_trusted`

Telemetry tables can remain empty until instrumentation is enabled, keeping the core recall catalog tightly coupled to the raw JSON while still future-proofing for RL pipelines inspired by Agent Lightning.

## 4. Relationships & Constraints

- `chat_sessions.session_id` → `requests.session_id` (1:N)
- `requests.request_id` anchors `request_parts`, `request_variables`, `responses`,
  `result_messages`, `followups`, `content_references`, `code_citations`, and
  `tool_outputs` (1:N). Cascading deletes remove dependent rows when a request is
  purged.
- `requests.request_id` links to `metrics_repeat_failures.request_id`, ensuring
  telemetry rows inherit provenance and workspace fingerprints.
- `agents.agent_id` may appear across sessions; descriptors are upserted per
  `agent_id` to avoid duplication.
- Timestamps use epoch millis integers to simplify SQLite windowing and order
  operations.
- Redaction runs prior to persistence: high-entropy tokens and credential-like
  patterns are hashed with a workspace-scoped salt so raw secrets never land in
  the catalog.

## 5. Security & Privacy Considerations

- Catalog artifacts stay inside `.vscode/CopilotChatHistory/`; migration scripts
  must document any override paths.
- Optional telemetry adapters (Agent Lightning, OTEL exporters) default to
  disabled. When enabled, they record consent + adapter version in
  `instrumentation_sources` and log outbound endpoints.
- Audit evidence (ingest logs, redaction reports) persists under
  `AI-Agent-Workspace/_temp/security/` with hashes stored in the requirements
  checklist so future agents can verify no unintended egress occurred.
