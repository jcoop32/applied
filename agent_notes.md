## Issue: 'MemoryObjectSendStream' object has no attribute 'send_message'
**Context:** Running the `mcp_bridge.py` script to bridge stdio to SSE for MCP servers.
**Root Cause:** The `mcp` SDK's `sse_client` helper returns a `MemoryObjectSendStream` for the write stream, which uses the standard `.send()` method, but the code was attempting to call `.send_message()` which does not exist on this object type.
**Solution:** specific code fix: Changed `await write_stream.send_message(data)` to `await write_stream.send(data)` in `app/mcp/mcp_bridge.py`.

## Issue: 'dict' object has no attribute 'message' in 'post_writer'
**Context:** Sending messages from the client (Stdio) to the MCP server via `mcp_bridge.py`.
**Root Cause:** The `sse_client` expects objects of type `SessionMessage` in the `write_stream`, but we were sending raw dictionaries. The `post_writer` internal function attempts to access `.message` on the object, causing an AttributeError.
**Solution:** Imported `SessionMessage` from `mcp.shared.message`. Parsed input JSON as `JSONRPCMessage` and wrapped it in `SessionMessage` before sending to the stream.

## Issue: 'context deadline exceeded' in MCP Bridge
**Context:** Establishing connection to MCP server via `mcp_bridge.py`.
**Root Cause:** Persistent timeouts ("context deadline exceeded"). Likely due to aggressive default timeouts in `sse_client` or environment-specific latency.
**Solution:** Updated `mcp_bridge.py` to use `timeout=None` and `sse_read_timeout=None` (disabling timeouts) and added `traceback.print_exc()` to debug specific underlying failures.

## Issue: MCP Server Connection Failed (ConnectError)
**Context:** Connecting to local Dockerized MCP servers (browser, supabase) via `mcp_bridge.py`.
**Root Cause:** `httpcore` / `anyio` connection failures on macOS when resolving `localhost`. IPv6 resolution or firewall issues prevent reliable connections to Docker ports despite being mapped to `0.0.0.0`.
**Solution:** Added logic to `app/mcp/mcp_bridge.py` to automatically replace `localhost` with `127.0.0.1` in the connection URL, bypassing resolution ambiguity.

## Issue: SyntaxError 'expected except or finally block' in ChatAgent
**Context:** Deployment/Docker startup failed with a `SyntaxError` in `app/agents/chat_agent.py`.
**Root Cause:** An unclosed `try:` block at line 18 wrapped the initialization logic but lacked a corresponding `except` block. A subsequent helper function definition broke the expected block structure.
**Solution:** Removed the invalid `try` block and dedented the initialization logic. Later re-added a correctly scoped `try/except` block around the main `generate_content_stream` failure point to ensure robust error handling without syntax errors.

## Issue: 'Storage endpoint URL should have a trailing slash'
**Context:** Supabase client initialization logged a warning about the storage URL format.
**Root Cause:** The `supabase-py` storage client might warn if the URL format isn't perfect, but previous attempts to manually append a slash `url += "/"` **caused** this warning or a double-slash issue in some versions.
**Solution:** Removed the manual slash appending. Passing `SUPABASE_URL` as-is (without trailing slash) resolves the warning in this environment. Verified that `list` and `get_public_url` work correctly without the manual slash.

## Issue: SyntaxError 'expected except or finally block' in chat.py
**Context:** During the implementation of error handling for Cloud Run resilience, `app/api/chat.py` was modified to wrap `handle_agent_action` in a `try` block, but the `except` block was inadvertently omitted or overwritten during a multi-step edit.
**Root Cause:** A tool call to `replace_file_content` updated the beginning of the function but failed to correctly append the necessary `except` block at the end, leaving an open `try` block.
**Solution:** Rewrote the entire `handle_agent_action` function using a single `replace_file_content` call to ensure the complete `try/except` structure was correctly applied with proper indentation.

## User Report: 2026-01-21
**Error:** Cloud Dispatch Error (empty message) / Cloud Worker failing silently.
**Root Cause:** The Gemini 2.5 Flash model in `GoogleResearcherAgent` exceeded the default output token limit (generating >8000 tokens), causing a `FinishReason.MAX_TOKENS` truncation. The resulting truncated JSON caused an `Unterminated string` error during parsing. The backend logging in `agent_runner.py` only printed `str(e)`, which was empty for some exceptions, masking the root cause.
**Fix Strategy:**
1.  **Optimized Prompt:** Updated `GoogleResearcherAgent` prompt to strictly forbid reasoning/markdown blocks and enforce conciseness ("Snippets must be under 20 words").
2.  **Increased Token Limit:** Updated `ChatGoogle` init to set `max_output_tokens` to 8192 as a safety buffer.
3.  **Improved Logging:** Updated `agent_runner.py` to use `traceback.format_exc()` for full error visibility.

## User Report: 2026-01-21
**Error:** FIND JOBS and Apply buttons not working. Chat returns "Something went wrong" immediately.
**Root Cause:**
1. Frontend: Race conditions with `window.func` assignments and HTML `onclick` attributes. Dynamic buttons need explicit event listeners.
2. Backend: `ChatAgent` crashes when Gemini 2.0 stream returns a `function_call` chunk because `chunk.text` access raises ValueError on non-text chunks.
**Fix Strategy:**
1. Frontend: Refactor `script.js` to remove `onclick` attributes and attach `addEventListener` in `initChatPage` and `loadJobs`.
2. Backend: Wrap `response_stream` loop in `try/except` in `chat_agent.py` and safely access `chunk.text` using `getattr` or `parts` check.
3. API: Ensure `handle_agent_action` in `chat.py` catches all exceptions and returns formatted JSON errors.

## User Report: 2026-01-21 (2)
**Error:** Apply button on Job Leads page is unresponsive. No feedback/modal.
**Root Cause:** (Investigation) Potential silent failure in `openApplyModal` or `loadJobs` event binding. The `resumeName` passed to the closure might be invalid, or `initApplyModal` might be failing to inject the modal on the Jobs page specifically.
**Fix Strategy:**
1.  Instrument `script.js` with `console.log` in `loadJobs` (binding) and `openApplyModal` (execution).
2.  Add a `try/catch` block inside the click handler to `alert()` errors to the user.
3.  Verify `initApplyModal` correctly injects the modal if missing.

## User Report: 2026-01-21 (3)
**Error:** `ReferenceError: handleApplyResumeUpload is not defined` when clicking Apply.
**Root Cause:** The `initApplyModal` function attempts to attach an event listener to `handleApplyResumeUpload`, but this function is not defined in `script.js`. It was likely referenced in a plan but never implemented.
**Fix Strategy:**
1.  Implement `handleApplyResumeUpload` in `script.js`.
2.  Logic should mirror `handleFileUpload` but update the Apply Modal's resume select dropdown upon success instead of just chatting.

## User Report: 2026-01-21 (Find Jobs Error)
**Error:** `ChatGoogle.__init__() got an unexpected keyword argument 'generation_config'`. Multiple "Starting Research" messages. Requested 5 jobs, got 10.
**Root Cause:**
1. `GoogleResearcherAgent`: The `ChatGoogle` wrapper (likely Langchain-based) does not accept `generation_config` in `__init__`. It was added in a previous attempt to fix token limits.
2. Duplicate Logs: `agent_runner.py` was saving a "Starting Research" chat message in addition to the one yielded by `ChatAgent`.
3. Incorrect Limit: `agent_runner.py` was hardcoding `limit=10` in the `MatcherAgent` call, ignoring the user-requested limit passed from `ChatAgent`.
**Fix Strategy:**
1. Updated `GoogleResearcherAgent` to pass `max_output_tokens=8192` directly (or via `model_kwargs` if needed, but trying direct arg first).
2. Removed the redundant `supabase_service.save_chat_message` call in `agent_runner.py`.
3. Updated `agent_runner.py` to pass the dynamic `limit` variable to `matcher.filter_and_score_leads`.
