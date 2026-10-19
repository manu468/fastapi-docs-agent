# from mcp.server.fastmcp import FastMCP

# mcp = FastMCP("fastapi-docs")


# @mcp.tool()
# # def search_docs(query: str) -> str:
# def search_docs(query: str, n: int = 5) -> str:
#     """Search the official FastAPI documentation and return the most relevant excerpts.
#     Call it once per distinct topic, with a short, specific query."""
#     return f"(stub) you searched for: {query}"


# if __name__ == "__main__":
#     mcp.run()  # talks over stdin/stdout by default

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from retrieve import retrieve

RESULTS_PER_SEARCH = 5

mcp = FastMCP("fastapi-docs")


@mcp.tool()
def search_docs(
    query: Annotated[str, Field(description="What to look up, e.g. 'background tasks'")],
) -> str:
    """Search the official FastAPI documentation and return the most relevant excerpts.
    Call it once per distinct topic, with a short, specific query.
    Returns a JSON list of {source, text} excerpts."""
    hits = retrieve(query, n=RESULTS_PER_SEARCH)
    return json.dumps([{"source": h["source"], "text": h["text"]} for h in hits])


if __name__ == "__main__":
    mcp.run()