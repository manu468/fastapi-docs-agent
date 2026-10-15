import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["mcp_server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                print(t.name, "|", t.description, "|", t.inputSchema)
            # result = await session.call_tool("search_docs", {"query": "middleware"})
            # print(result.content[0].text)
            result = await session.call_tool("search_docs", {"query": "how do I add middleware"})
            print(result.content[0].text[:800])


asyncio.run(main())