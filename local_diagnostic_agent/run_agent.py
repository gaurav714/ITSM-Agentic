"""Executable launcher for the local diagnostic MCP server."""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local diagnostic MCP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--open-health", action="store_true")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/health"
    print("Local Diagnostic MCP Server")
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"MCP endpoint: http://{args.host}:{args.port}/mcp")
    print("Keep this window open while using the helpdesk browser app.")
    print("Press Ctrl+C to stop.")

    if args.open_health:
        webbrowser.open(url)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
