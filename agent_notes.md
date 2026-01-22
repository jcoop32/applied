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
