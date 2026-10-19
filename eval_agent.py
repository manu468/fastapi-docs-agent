"""Run the agent over eval_set.json and grade it with the Project 1 judge.

Usage:
    python eval_agent.py        # all questions
    python eval_agent.py 3      # first 3 questions only (smoke test)

Results go to agent_results.json (grade_results.json from Project 1 is not touched).
"""
import json
import sys

# from agent import run_agent -- commenting out after adding agent mcp and mcp server, replcaed with below code
import asyncio

from agent_mcp import run_agent as run_agent_async


def run_agent(question, verbose=False):
    # agent_mcp.run_agent is async; this wrapper lets the rest of the file call it normally
    return asyncio.run(run_agent_async(question, verbose=verbose))


from grade import judge, summarize  # the same LLM judge used for Project 1

def root_causes(e):
    if isinstance(e, BaseExceptionGroup):
        return [c for sub in e.exceptions for c in root_causes(sub)]
    return [e]

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with open("eval_set.json", encoding="utf-8") as f:
        eval_set = json.load(f)
    if limit:
        eval_set = eval_set[:limit]

    results = []
    tot = {"claims": 0, "supported": 0, "cited": 0, "cite_ok": 0}
    searches, excerpt_counts = [], []
    retrieved_count = refused_count = truncated_count = no_answer_count = graded = 0
    error_count = 0

    for item in eval_set:
        question = item["question"]
        try:
            trace = run_agent(question, verbose=False)
            if not trace["finished"]:
                no_answer_count += 1
                print("NO ANSWER (hit turn cap) |", question)
                results.append({"question": question, "queries": trace["queries"], "finished": False})
                continue
            verdict = judge(question, trace["excerpts"], trace["answer"])
        # except Exception as e:
        #     print("ERROR |", question, "|", e)
        #     continue
        except Exception as e:
            error_count += 1
            print("ERROR |", question)
            for c in root_causes(e):
                print("      cause:", repr(c))
            continue

        graded += 1
        n, sup, nc, ok = summarize(verdict)
        tot["claims"] += n
        tot["supported"] += sup
        tot["cited"] += nc
        tot["cite_ok"] += ok

        n_search = len(trace["queries"])
        n_exc = len(trace["excerpts"])
        searches.append(n_search)
        excerpt_counts.append(n_exc)
        truncated_count += 1 if trace["truncated"] else 0

        retrieved = any(exp in e["source"] for exp in item["expected"] for e in trace["excerpts"])
        retrieved_count += 1 if retrieved else 0
        refused = bool(verdict.get("refused"))
        refused_count += 1 if refused else 0
        status = "REFUSED" if refused else "answered"

        print(
            f"claims {sup}/{n} | cites {ok}/{nc} | searches {n_search} | excerpts {n_exc} | "
            f"retrieved: {'yes' if retrieved else 'NO'} | {status} | {question}"
        )
        for c in verdict.get("claims", []):
            if not c.get("supported"):
                print("    UNSUPPORTED:", c["claim"])
            elif c.get("cited") and not c.get("citation_ok"):
                print("    BAD CITATION:", c["claim"], c["cited"])

        results.append(
            {
                "question": question,
                "answer": trace["answer"],
                "queries": trace["queries"],
                "blocked": trace["blocked"],
                "turns": trace["turns"],
                "truncated": trace["truncated"],
                "sources": [e["source"] for e in trace["excerpts"]],
                "excerpts": trace["excerpts"],  # kept so any claim can be checked by hand later
                "retrieved_expected": retrieved,
                "verdict": verdict,
            }
        )

    # with open("agent_results.json", "w", encoding="utf-8") as f:
    with open("agent_mcp_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print()
    if tot["claims"]:
        print(f"Grounded claims:   {tot['supported']}/{tot['claims']} = {tot['supported'] / tot['claims']:.0%}")
    if tot["cited"]:
        print(f"Correct citations: {tot['cite_ok']}/{tot['cited']} = {tot['cite_ok'] / tot['cited']:.0%}")
    if graded:
        print(f"Avg searches per question:           {sum(searches) / graded:.1f}")
        print(f"Avg distinct excerpts per question:  {sum(excerpt_counts) / graded:.1f}")
        print(f"Expected page retrieved:             {retrieved_count}/{graded}")
        print(f"Judge says refused:                  {refused_count}/{graded}")
        print(f"Answers cut off at max_tokens:       {truncated_count}/{graded}")
    if no_answer_count:
        print(f"No answer (hit turn cap):            {no_answer_count}")
    if error_count:
        print(f"ERRORS (not graded):                 {error_count}")
    # print("Full details saved to agent_results.json")
        print("Full details saved to agent_mcp_results.json")