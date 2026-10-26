"""Run the MyShare MCP server.

python -m myshare_mcp --transport http  --port 8001   # Streamable HTTP at http://localhost:8001/mcp
python -m myshare_mcp --transport stdio               # stdin/stdout (needs MYSHARE_USER_TOKEN)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from myshare_shared.tracing import configure_tracing

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="myshare_mcp", description="MyShare MCP server")
    parser.add_argument(
        "--transport", choices=["http", "stdio"], default=os.environ.get("MCP_TRANSPORT", "http")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_SERVER_PORT", "8001")))
    parser.add_argument("--log-level", default=os.environ.get("MCP_LOG_LEVEL", "INFO"))
    args = parser.parse_args()

    # Logs go to STDERR, always. In stdio mode STDOUT *is* the protocol channel: every
    # byte written there must be a JSON-RPC message. A stray print() or log line on
    # stdout corrupts the stream and the client disconnects with a parse error.
    logging.basicConfig(
        stream=sys.stderr,
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("myshare_mcp")
    configure_tracing("mcp server")  # LangSmith privacy filter; no-op unless LANGSMITH_TRACING=true

    if args.transport == "stdio":
        log.info(
            "MyShare MCP server on stdio (API: %s)",
            os.environ.get("MYSHARE_API_URL", "http://localhost:8000"),
        )
        mcp.run("stdio")
    else:
        log.info("MyShare MCP server on http://%s:%s/mcp", args.host, args.port)
        # streamable_http_path defaults to /mcp. Each JSON-RPC message is one HTTP POST;
        # the server may answer with plain JSON or an SSE stream (for progress/notifications).
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
