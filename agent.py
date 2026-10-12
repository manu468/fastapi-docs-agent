"""FastAPI docs agent: the model decides when and what to search.

Usage:
    python agent.py "Compare how FastAPI handles background tasks versus dependencies"
"""
import sys

import anthropic

from retrieve import retrieve  # import only the function: retrieve.py has its own `client` (Chroma)

MODEL = "claude-sonnet-4-6"
MAX_TURNS = 6          # safety cap on model calls: stops a confused model from looping forever
MAX_SEARCHES = 4       # enforced in code (see run_agent), not just requested in the prompt
RESULTS_PER_SEARCH = 5

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

# Adapted from the Project 1 rules. Citations use GLOBAL numbers because there can be several searches.
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

TOOLS = [
    {
        "name": "search_docs",
        "description": (
            "Search the official FastAPI documentation and return the most relevant "
            "excerpts. Call it once per distinct topic, with a short, specific query. "
            "You may call it several times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look up, e.g. 'background tasks'",
                }
            },
            "required": ["query"],
        },
    }
]


def run_search(query, seen):
    """Run retrieval and format the chunks with numbers that are unique across searches.

    `seen` maps chunk text -> (excerpt number, source file).
    """
    hits = retrieve(query, n=RESULTS_PER_SEARCH)
    parts = []
    for h in hits:
        if h["text"] not in seen:
            seen[h["text"]] = (len(seen) + 1, h["source"])
        n = seen[h["text"]][0]
        parts.append(f"[{n}] (source: {h['source']})\n{h['text']}")
    return "\n\n".join(parts) if parts else "No results found."


def run_agent(question, verbose=True):
    """Run the tool-use loop. Returns a dict describing the whole run."""
    messages = [{"role": "user", "content": question}]
    seen = {}       # chunk text -> (number, source), shared across all searches in this run
    queries = []    # the searches that were actually executed
    blocked = 0     # search requests refused because the budget was used up

    def finish(text, turns, finished, truncated=False):
        # excerpts in the same order as their citation numbers, so excerpt n is excerpts[n-1]
        excerpts = [
            {"text": t, "source": s, "distance": 0.0}
            for t, (n, s) in sorted(seen.items(), key=lambda kv: kv[1][0])
        ]
        return {
            "answer": text,
            "turns": turns,
            "queries": queries,
            "blocked": blocked,
            "excerpts": excerpts,
            "finished": finished,
            "truncated": truncated,
        }

    for turn in range(1, MAX_TURNS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # The model wrote a final answer (or ran out of tokens).
            text = "".join(b.text for b in response.content if b.type == "text")
            truncated = response.stop_reason == "max_tokens"
            if truncated:
                text += "\n\n[WARNING: answer was cut off at max_tokens]"
            return finish(text, turn, True, truncated)

        # The model asked for one or more tool calls. YOUR code runs them.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "search_docs":
                if len(queries) >= MAX_SEARCHES:
                    # Budget enforced here: the prompt only asks, the code decides.
                    blocked += 1
                    result_text = "Search limit reached. Answer now using the excerpts you already have."
                else:
                    query = block.input.get("query", "")
                    queries.append(query)
                    if verbose:
                        print(f"[turn {turn}] search_docs({query!r})")
                    result_text = run_search(query, seen)
            else:
                if verbose:
                    print(f"[turn {turn}] model asked for unknown tool {block.name!r}")
                result_text = f"Error: unknown tool '{block.name}'. Available tools: search_docs."
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # ties this result to the request that asked for it
                    "content": result_text,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return finish("Stopped: reached the maximum number of turns without a final answer.", MAX_TURNS, False)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    if not question:
        sys.exit('Usage: python agent.py "your question"')
    trace = run_agent(question)
    print("\n" + trace["answer"])
    print(
        f"\n(turns: {trace['turns']}, searches: {len(trace['queries'])}, "
        f"blocked: {trace['blocked']}, distinct excerpts: {len(trace['excerpts'])})"
    )