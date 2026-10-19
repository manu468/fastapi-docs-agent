# FastAPI Docs Agent

An agent that answers questions about FastAPI by deciding for itself when and what to search in the official docs. It is Project 2 of my AI engineering practice, built on the retrieval pipeline from [fastapi-docs-rag](https://github.com/manu468/fastapi-docs-rag) (Project 1).

The main question: **does letting the model run its own searches beat a fixed "retrieve once, then answer" pipeline?** I measured it with the same 20 questions and the same grader for both. I then moved the search tool into an MCP server and re-ran the evaluation to check that nothing broke.

## How it works

- `search_docs` is a tool backed by Project 1's `retrieve()` (ChromaDB, all-MiniLM-L6-v2 embeddings, 1,410 chunks, 5 results per search).
- `agent.py` runs the tool-use loop: Claude requests a search, my code runs it and returns the excerpts, and this repeats until Claude writes its answer.
- Excerpt numbers are global across all searches in a run, so a citation like `[7]` is unambiguous.
- Limits are enforced in code, not in the prompt: at most 4 searches (further calls get a "limit reached" result) and at most 6 model turns. Unknown tool names get an error result. Answers cut off at `max_tokens` are flagged.
- Answers must use only the excerpts and cite them.
- `mcp_server.py` exposes `search_docs` as an MCP server; `agent_mcp.py` is an MCP client that asks the server for its tools, translates them for Claude, and calls them. The search cap and citation numbering stay on the client, and retrieval stays on the server.

## Evaluation

20 questions, each with the docs page that should answer it. The grader is an LLM judge that splits each answer into claims and checks each against the excerpts the model was given.

| | Project 1 (fixed pipeline) | Agent | Agent + stricter prompt | Agent via MCP |
|---|---|---|---|---|
| Grounded claims | 146/150 (97%) | 241/255 (94.5%) | 236/248 (95%) | 249/256 (97%) |
| Unsupported claims | 4 | 14 | 12 | 7 |
| Correct citations | 135/138 (98%) | 222/234 (95%) | 218/228 (96%) | 232/240 (97%) |
| Expected page retrieved | 19/20 | 20/20 | 20/20 | 20/20 |
| Answers with a code block | 8/20 | 20/20 | 20/20 | 20/20 |
| Avg answer length (chars) | ~1,000 | 2,458 | 2,468 | 2,444 |
| Searches per question | 1 | 2.65 | 2.6 | 2.6 |

"Agent + stricter prompt" adds one rule: do not add advice, comparisons or background that the excerpts don't state.

Project 1 passed the top 10 chunks from one search to the model. The agent gets 5 per search and ends up with about 10 distinct excerpts per question, so both see a similar amount of text.

> `agent_results.json` holds the direct agent's last run (agent + stricter prompt); `agent_mcp_results.json` holds the MCP run. The first agent run's raw file was overwritten, so its numbers appear only in the table. The MCP run uses the same retriever, prompt and model; only the tool's location differs.

## What I learned

- **Finding, sticking to the source, and helping are three separate things.** Groundedness only measures whether claims match the given excerpts. It does not measure whether the right information was found. A system that refuses everything would score 100%.
- **The agent found more and was more useful.** It retrieved the expected page for all 20 questions and included code in every answer. Its unsupported claims were mostly helpful-sounding additions such as "X is generally preferred" or "A vs B is best for...", not invented facts.
- **A prompt rule is a request, not a guarantee.** "Use at most 4 searches" was ignored (one run made 8), so the cap moved into code. A second rule, "don't add outside claims", changed groundedness by under one point (0.7), which is within noise.
- **The agent is non-deterministic.** The same question produced different queries and sometimes different facts across runs. Three runs of essentially the same agent scored 94.5%, 95% and 97% grounded, so small metric differences (including between the agent and Project 1) mean little without repeated runs.
- **Who owns what in an MCP setup.** The server owns the tool and its definition (name, description and schema are generated from the function). The client owns the agent policy: the loop, the search cap and the citation numbering.
- **Re-run the evaluation after a refactor.** A placeholder left in the system prompt produced uncited, unrestricted answers that looked fine at a glance. The 20-question run is what verifies that behavior is unchanged.

## Limitations

- 20 questions and one run per configuration. The three agent runs scored 94.5%, 95% and 97% grounded, so run-to-run variation is at least a few points, and Project 1's 97% falls inside that range. I did not repeat runs, so I cannot say whether the fixed pipeline or the agent is more grounded.
- The judge is the same model family as the generator and makes mistakes. It also marks some reasonable inferences as unsupported.
- I did not measure whether answers are *correct*. Page retrieval, code blocks and answer length are proxies for usefulness, not accuracy checks.
- The docs contain version-history notes that a model can misread as current behavior.
- Project 1's "admits missing info" count (10/20) and the agent's (0/20) used different phrase lists, so I do not compare them.
- Each evaluation question starts a fresh MCP server process, which is slow but keeps runs independent. One earlier full run hit a temporary error partway through; I re-ran it and report only the clean run.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
# build the index first with build_index.py from fastapi-docs-rag
python agent.py "How do I add middleware in FastAPI?"       # tools called directly
python agent_mcp.py "How do I add middleware in FastAPI?"   # same agent, tools via MCP
python eval_agent.py        # full evaluation through MCP, writes agent_mcp_results.json
```

`retrieve.py`, `ask.py`, `grade.py` and `eval_set.json` are copied from Project 1.

## Future work

- Repeat runs per setting and report ranges.
- A key-facts check to measure answer correctness, not just groundedness.
- A verifier pass that removes claims the excerpts don't support.
- Production hardening: error handling, logging, and cost and latency measurements.