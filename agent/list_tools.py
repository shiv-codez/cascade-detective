import asyncio
import os
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(dotenv_path="../.env")

MCP_URL = "http://localhost:8000/mcp"
SIGNOZ_API_KEY = os.environ.get("SIGNOZ_API_KEY")

async def main():
    headers = {"SIGNOZ-API-KEY": SIGNOZ_API_KEY}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

if __name__ == "__main__":
    asyncio.run(main())