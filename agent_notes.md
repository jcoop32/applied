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

## User Report: 2026-01-21 (Agent Execution & UI)
**Error:** `httpx.ReadTimeout`, Agent runs locally instead of Cloud Run, UI shows "Error starting research" then stale job matches, Cancel button missing.
**Root Cause:**
1. **Execution Environment:** `app/api/agents.py` defaulted `USE_GITHUB_ACTIONS=True`, causing `dispatch_github_action` to attempt (and timeout on) a GHA dispatch, instead of using the intended `agent_runner` Cloud Run logic.
2. **Timeout:** `app/services/agent_runner.py` had a short 10s timeout for Cloud Run dispatch, causing fallback to local execution on cold starts.
3. **Stale Data:** `script.js` polling logic `(attempts > 5)` incorrectly assumed research was done after 15s, displaying existing (stale) matches from the DB while the new research was still running locally.
4. **UI State:** The backend timeout caused the frontend `fetch` to fail, showing "Error starting research" and preventing the polling loop (and Cancel button visibility) from initializing correctly.
**Fix Strategy:**
1. **Config:** Changed `USE_GITHUB_ACTIONS` default to `False` in `agents.py` to prioritize `agent_runner` dispatch logic.
2. **Timeout:** Increased Cloud Run dispatch timeout to 60s in `agent_runner.py`.
3. **Frontend:** Updated `script.js` polling to ONLY show matches when `status === "COMPLETED"`, preventing stale data display.

## Internal Issue: Switch to Real-time Job Updates
**Context:** Job search status updates were previously polling every 3 seconds, delaying results and causing duplicate fetching.
**Solution:** Refactored `script.js` to utilize the existing Supabase Realtime subscription on the `profiles` table. The frontend now tracks `lastResearchStatus` and triggers `handleResearchCompletion()` immediately when the status transitions to "COMPLETED". Removed `pollResearchStatus` entirely. 
## User Report: 2026-01-21 (Cloud Run Applier)
**Error:** `Supabase Download Error` / `Worker Warning: no user_id found for resume download`.
**Root Cause:** The `user_id` was not being passed in the "apply" task payload to the Cloud Worker. The worker relies on `user_id` to construct the resume storage path (`{user_id}/{filename}`). The `payload.user_id` was None, and extraction from `user_profile` failed because `chat.py` wasn't injecting `user_id` into the profile blob sent to the worker.
**Fix Strategy:**
1.  **Inject User ID:** Updated `app/api/chat.py` to explicitly add `user_id` to the `profile_blob` before passing it to `agent_runner`.
2.  **Payload Update:** Updated `app/services/agent_runner.py` to extract `user_id` early and include it as a top-level field in the Cloud Run dispatch payload.

## User Report: 2026-01-22 (Search Limit)
**Error:** Agent returns fewer jobs than requested (e.g., 1 instead of 3).
**Root Cause:** 'GoogleResearcherAgent' generated a fixed set of search queries and executed them once. If those queries yielded few valid results, the agent returned whatever it found without attempting to expand the search.
**Fix Strategy:**
1. Refactored 'GoogleResearcherAgent' to implement a **Search Loop**.
2. Phase 1: Attempts strict "verified" queries (quoted titles).
3. Phase 2: If 'limit' is not reached, attempts broader queries.
4. The loop continues until the requested 'limit' is met or attempts are exhausted.

## User Report: 2026-01-22 (Supabase 401)
**Error:** GET | 401 | ... | /realtime/v1/websocket
**Root Cause:**
1. **Missing Auth Token:** The frontend `script.js` initializes the Supabase client anonymously (`createClient` without options), so it does not send the user's `access_token`.
2. **RLS/Auth Mismatch:** If "Enable Anonymous Access" is disabled in Supabase, this anonymous connection is rejected (401). Even if accepted, the subscribed channel filters by `user_id`, which fails RLS for anonymous users.
3. **Potential Key Issue:** The backend exposes `SUPABASE_KEY` as user anon key. If this is invalid/missing, connection fails.
**Fix Strategy:**
1. **Pass Token:** Update `script.js` to pass the stored JWT `token` in `createClient` options (`accessToken` or `global.headers`).
2. **Verify Secret:** Ensure the backend `SECRET_KEY` matches Supabase's JWT Secret so the token is accepted.
3. **Debug Config:** Add logging in `script.js` to verify `supabase_url` and `key` are loaded correctly.

## User Report: 2026-01-22 (Syntax Error)
**Error:** `SyntaxError: Identifier 'currentUser' has already been declared` in `static/script.js`.
**Root Cause:** A `multi_replace_file_content` operation aimed at adding polling logic accidentally duplicated the existing `let currentUser = null;` line due to an overlapping replacement range.
**Fix Strategy:** Removed the duplicate declaration line.

## User Report: 2026-01-22 (Browser Interaction Failure)
**Error:** `BrowserError: Failed to click element: ... Node with given id does not belong to the document`.
**Root Cause:** The `GoogleResearcherAgent` was attempting to interact with the search page (Brave Search) before the DOM was fully stable. The default `browser-use` wait times (likely 4.0s or less) were insufficient for the cloud environment, leading to stale element references and click failures.
**Fix Strategy:**
1. Increased `wait_for_network_idle_page_load_time` to 6.0s (from 4.0s).
2. Increased `minimum_wait_page_load_time` to 3.0s (from 2.0s).
3. Added `--disable-popup-blocking` and `--disable-notifications` to browser launch arguments to reduce interference.

## User Report: 2026-01-22 (Cloud Worker 404 & Poilling Flood)
**Error:** 
1. Cloud Worker 404: Resume download fails because `user_id` is missing in `profile_blob`.
2. Excessive Polling: Frontend polls `/api/profile` every 5 seconds when Realtime fails, flooding logs.

**Root Cause:**
1. `app/api/agents.py`: The `user_id` is available in `trigger_apply` but not injected into the `profile_blob` passed to the worker. The worker needs `user_id` to construct the resume path.
2. `static/script.js`: `startPollingFallback` has a hardcoded interval of 5000ms (5s), which is too aggressive.

**Fix Strategy:**
1. Inject `profile_blob['user_id'] = user_id` in `app/api/agents.py` before dispatching the task.
2. Increase polling interval to 15000ms (15s) in `static/script.js`.

## User Report: 2026-01-22 (Cloud Worker Disconnection)
**Error:** `Failed to update research status: Server disconnected` and `Storage endpoint URL should have a trailing slash`.
**Root Cause:**
1. **Connection Drops:** The Supabase client (httpx) inside Cloud Run occasionally drops the connection ("Server disconnected") during long-running async tasks, causing `update_research_status` to fail.
2. **URL Warning:** `supabase-py` (specifically the storage client) requires the `SUPABASE_URL` to have a trailing slash, otherwise it emits a warning (or could potentially cause issues in strict versions).
**Fix Strategy:**
1. **Resilience:** Added a 3-attempt retry loop with backoff to `update_research_status` in `app/services/agent_runner.py` to handle transient connection failures.
2. **Config:** Updated `app/services/supabase_client.py` to automatically append a trailing slash to the `SUPABASE_URL` if missing.

## User Report: 2026-01-22 (Persistent WebSocket 401)
**Error:** Supabase Realtime WebSocket returns 401 even with `access_token` passed correctly.
**Diagnosis:** The frontend code (`initRealtime` in `script.js`) correctly initializes the Supabase client with `Authorization: Bearer <token>`. The failure is likely due to server-side configuration in the Supabase Dashboard.
**Required Configuration (User Action):**
1. **Replication:** Realtime must be explicitly enabled for `profiles` and `leads`. (Database -> Replication).
2. **RLS Policies:** Since we use **custom Integer IDs** (not standard Supabase UUIDs), we must extract the ID from the JWT claims.
   *   Policy: `CREATE POLICY "Enable read for users" ON "public"."profiles" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.jwt() ->> 'id')::bigint = user_id);`

## User Report: 2026-01-22 (Cloud Dispatch Error)
**Error:** `Execution Mode 'cloud_run' requested but Cloud Dispatch failed or not configured.` in Cloud Run logs.
**Root Cause:** The `agent_runner.py` script has a safety check to prevent local execution when `execution_mode` is 'cloud_run', relying on the `IS_CLOUD_WORKER` environment variable. This variable was missing from the `Dockerfile` and Cloud Run configuration, causing the worker to misidentify itself as a local environment and block execution.
**Fix Strategy:**
1. Removed `ENV IS_CLOUD_WORKER=true` from `Dockerfile` (caused local execution issue).
2. Updated `deploy.sh` to set `IS_CLOUD_WORKER=true` via `--update-env-vars` purely for the Cloud Run instance.
3. Redeploy the Cloud Run service.

## User Report: 2026-01-24
**Error:** Syntax error at end of script.js ("expected '}'").
**Root Cause:** A failed `multi_replace_file_content` tool call resulted in a duplicate, unclosed `function createExperienceCard` declaration being inserted before the existing one, creating a nested function structure that swallowed the rest of the file and left the global scope unclosed.
**Fix Strategy:** Removed the orphaned duplicate lines (1249-1258).

## User Report: 2026-01-24 (Cloud Dispatch Failed)
**Error:** `Cloud Dispatch Failed: {"detail":"SupabaseService.update_lead_status() got an unexpected keyword argument 'status_msg'"}`
**Root Cause:** The `run_applier_task` function in `agent_runner.py` was calling `supabase_service.update_lead_status` with a `status_msg` keyword argument (likely from a previous version of the function signature), but the current definition in `supabase_client.py` does not accept this argument.
**Fix Strategy:** Removed the invalid `status_msg` argument and implemented dynamic status construction (e.g. "APPLYING (Cloud)" vs "APPLYING (Local)") based on `IS_CLOUD_WORKER` environment variable.

## Internal Issue: Missing Browser Use Cloud Session Link
**Context:** User reported that the "Watch Live" link for Browser Use Cloud is not appearing in the UI.
**Investigation:** Suspected issue with `browser-use` library not exposing `session_id` as expected, or `BROWSER_USE_API_KEY` not being detected. 
**Next Steps:** Instrumenting `app/agents/applier.py` with debug logging to inspect run-time attributes of the `Browser` object and environment variables.



## Internal Issue: Invalid Supabase Key Usage & Key Split
**Context:** Supabase Realtime WebSocket connection refused (NS_ERROR_WEBSOCKET_CONNECTION_REFUSED). Logs showed `apikey=sb_secret_...` which is invalid for client-side use.
**Root Cause:** The `.env` used a single `SUPABASE_KEY` which contained the Service Role (secret) key starting with `sb_secret_` (or similar non-JWT format in some contexts, though usually it's `eyJ...`). The frontend requires the Anon public key (JWT), and the backend should prefer the Service Role key for admin privileges. Sharing one key for both is insecure and caused the frontend to send an invalid key.
**Solution:**
1. Split configuration into `SUPABASE_ANON_KEY` (Frontend/Client) and `SUPABASE_SERVICE_ROLE_KEY` (Backend/Admin).
2. Updated `auth.py` to serve `SUPABASE_ANON_KEY` to the frontend via `/config`.
3. Updated `supabase_client.py` to use `SUPABASE_SERVICE_ROLE_KEY` for backend operations.
