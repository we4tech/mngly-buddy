"""MCP server exposing all BuddyAgent tools via stdio.

Run directly to start the MCP server:
    python mcp_server.py

The agent_app.py launches this as a subprocess via MCPStdioTool.
"""

import sys
from pathlib import Path

# Ensure the project root is on the path when run as a subprocess.
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from tools import all_tool_functions

mcp = FastMCP("buddy-tools")

# Register every raw tool function with the MCP server.
for _name, _fn in all_tool_functions().items():
    mcp.add_tool(_fn)

if __name__ == "__main__":
    mcp.run(transport="stdio")
