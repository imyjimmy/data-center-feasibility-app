import os

from fastmcp import FastMCP

from app.main import app
from app.provider_mcp import create_provider_mcp


provider_id = os.getenv("PROVIDER_ID")

if provider_id:
    mcp = create_provider_mcp(provider_id)
else:
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
