import os
from pathlib import Path

from dotenv import load_dotenv

from app.provider_mcp import create_provider_mcp, create_research_mcp


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(APP_DIR / ".env", override=True)

provider_id = os.getenv("PROVIDER_ID")

if provider_id:
    mcp = create_provider_mcp(provider_id)
else:
    mcp = create_research_mcp()


if __name__ == "__main__":
    mcp.run(
        transport=os.getenv("MCP_TRANSPORT", "http"),
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "9000")),
    )
