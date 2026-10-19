"""FastAPI docs agent v2: the tools come from an MCP server, not an import."""
import asyncio
import json
import sys

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "claude-sonnet-4-6"
MAX_TURNS = 6
MAX_SEARCHES = 4  # enforced here, on the client: it's agent policy

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You answer questions about FastAPI using ONLY the documentation excerpts \
returned by the search_docs tool.

Rules:
- Use search_docs to find information. For a question that covers several topics, \
search each topic separately with its own focused query. If a result doesn't contain \
what you need, search again with different wording.
- Use at most 4 searches in total, then answer with what you have.
- Only state claims, and only show code, that appear in the excerpts. Do not use your own \
knowledge of FastAPI.
- If the excerpts don't contain part of the answer, say so plainly instead of filling the gap.
- Cite the excerpts you used with their numbers in square brackets, like [3]. \
Excerpt numbers are unique across all of your searches.
- Do not add advice, comparisons, or background that the excerpts don’t state. If it isn’t in an excerpt, leave it out.
"""

SERVER = StdioServerParameters(command=sys.executable, args=["mcp_server.py"])


def format_results(raw_json, seen):
    """Number excerpts globally across searches (the job run_search did in agent.py)."""
    parts = []
    for h in json.loads(raw_json):
        if h["text"] not in seen:
            seen[h["text"]] = (len(seen) + 1, h["source"])
        n = seen[h["text"]][0]
        parts.append(f"[{n}] (source: {h['source']})\n{h['text']}")
    return "\n\n".join(parts) if parts else "No results found."


async def run_agent(question, verbose=True):
    messages = [{"role": "user", "content": question}]
    seen, queries, blocked = {}, [], 0

    def finish(text, turns, finished, truncated=False):
        excerpts = [
            {"text": t, "source": s, "distance": 0.0}
            for t, (n, s) in sorted(seen.items(), key=lambda kv: kv[1][0])
        ]
        return {"answer": text, "turns": turns, "queries": queries, "blocked": blocked,
                "excerpts": excerpts, "finished": finished, "truncated": truncated}

    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Ask the server what it offers, then rename the key for Claude's API
            listed = await session.list_tools()
            tools = [
                {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
                for t in listed.tools
            ]
            tool_names = {t["name"] for t in tools}

            for turn in range(1, MAX_TURNS + 1):
                response = client.messages.create(
                    model=MODEL, max_tokens=3000, system=SYSTEM_PROMPT,
                    tools=tools, messages=messages,
                )
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use":
                    text = "".join(b.text for b in response.content if b.type == "text")
                    truncated = response.stop_reason == "max_tokens"
                    if truncated:
                        text += "\n\n[WARNING: answer was cut off at max_tokens]"
                    return finish(text, turn, True, truncated)

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    is_error = False
                    if block.name not in tool_names:
                        result_text = f"Error: unknown tool '{block.name}'. Available tools: {', '.join(sorted(tool_names))}."
                        is_error = True
                    elif block.name == "search_docs" and len(queries) >= MAX_SEARCHES:
                        blocked += 1
                        result_text = "Search limit reached. Answer now using the excerpts you already have."
                    else:
                        if block.name == "search_docs":
                            queries.append(block.input.get("query", ""))
                            if verbose:
                                print(f"[turn {turn}] search_docs({queries[-1]!r})")
                        # The call goes to the MCP server, not to a local function
                        result = await session.call_tool(block.name, block.input)
                        result_text = result.content[0].text if result.content else ""
                        is_error = bool(result.isError)
                        if block.name == "search_docs" and not is_error:
                            result_text = format_results(result_text, seen)
                    item = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                    if is_error:
                        item["is_error"] = True
                    tool_results.append(item)
                messages.append({"role": "user", "content": tool_results})

    return finish("Stopped: reached the maximum number of turns without a final answer.", MAX_TURNS, False)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    if not question:
        sys.exit('Usage: python agent_mcp.py "your question"')
    trace = asyncio.run(run_agent(question))
    print("\n" + trace["answer"])
    print(f"\n(turns: {trace['turns']}, searches: {len(trace['queries'])}, "
          f"blocked: {trace['blocked']}, distinct excerpts: {len(trace['excerpts'])})")