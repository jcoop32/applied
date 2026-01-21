import asyncio
import sys
import json
import argparse
from mcp.client.sse import sse_client
from mcp.types import JSONRPCMessage
from mcp.shared.message import SessionMessage

# Bridge between Stdio (VS Code) and SSE (Docker MCP Server)
# usage: uv run python app/mcp/mcp_bridge.py --url http://localhost:8001/sse

import traceback

# ... imports ...

async def run_bridge(url: str):
    # Fix for macOS/Docker localhost resolution issues
    # httpcore often fails with "All connection attempts failed" when resolving localhost if IPv6 is involved but not listening
    if "localhost" in url:
        sys.stderr.write(f"Info: Replacing 'localhost' with '127.0.0.1' in {url} for reliable Docker connection.\n")
        url = url.replace("localhost", "127.0.0.1")

    try:
        sys.stderr.write(f"Connecting to {url}...\n")
        # Connect to the SSE endpoint using the official client helper
        # timeout=None disables connect/write timeouts
        # sse_read_timeout=None disables read timeout
        async with sse_client(url, timeout=None, sse_read_timeout=None) as (read_stream, write_stream):
            sys.stderr.write("Connected! Bridge running...\n")
            
            # Task: Read from SSE -> Write to Stdout
            async def sse_to_stdout():
                try:
                    async for message in read_stream:
                        if isinstance(message, SessionMessage):
                            message = message.message
                            
                        if hasattr(message, "model_dump_json"):
                            json_str = message.model_dump_json(by_alias=True)
                        else:
                            json_str = json.dumps(message)
                        
                        sys.stdout.write(json_str + "\n")
                        sys.stdout.flush()
                except Exception as e:
                    sys.stderr.write(f"SSE Read Error: {e}\n")
                    raise e

            # Task: Read from Stdin -> Write to SSE
            async def stdin_to_sse():
                loop = asyncio.get_event_loop()
                while True:
                    line = await loop.run_in_executor(None, sys.stdin.readline)
                    if not line:
                        break
                    
                    try:
                        data = json.loads(line)
                        rpc_message = JSONRPCMessage.model_validate(data)
                        session_message = SessionMessage(rpc_message)
                        await write_stream.send(session_message)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        sys.stderr.write(f"Stdin Error: {e}\n")

            await asyncio.gather(sse_to_stdout(), stdin_to_sse())

    except Exception as e:
        sys.stderr.write(f"Bridge failed: {e}\n")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="SSE Endpoint URL")
    args = parser.parse_args()
    
    asyncio.run(run_bridge(args.url))
