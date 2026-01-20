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
