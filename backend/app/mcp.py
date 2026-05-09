import os

from fastmcp import FastMCP

from app.main import app


mcp = FastMCP.from_fastapi(
    app=app,
    name="Data Center Feasibility Texas Open Data MCP",
)


if __name__ == "__main__":
    mcp.run(
        transport=os.getenv("MCP_TRANSPORT", "http"),
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "9000")),
    )
