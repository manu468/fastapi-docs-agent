import json
import anthropic
from ask import answer, build_context

client = anthropic.Anthropic()
JUDGE_MODEL = "claude-sonnet-4-6"

JUDGE_PROMPT = """You are a strict fact-checker for a documentation assistant.

You are given numbered documentation excerpts, a question, and an answer that was supposed to be written using ONLY those excerpts.

Your job:
1. Break the answer into its individual factual claims (ignore pleasantries and formatting).
2. For each claim, decide whether it is SUPPORTED by the excerpts. A claim is supported only if the excerpts state it or directly imply it. Paraphrases count as support. Do NOT use your own knowledge of the topic: if the excerpts do not say it, it is not supported, even if it is true in general.
3. If a claim cites an excerpt like [2], check that excerpt 2 actually supports it.
4. Say whether the answer declines to answer because the excerpts lack the information.

Reply with JSON only, in exactly this shape:
{"refused": false, "claims": [{"claim": "short restatement", "supported": true, "cited": [2], "citation_ok": true}]}

Use "cited": [] and "citation_ok": null for claims that cite nothing."""


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")  # (1)
    return json.loads(text[start:end + 1])


def judge(question, hits, answer_text):
    context = build_context(hits)  # (2)
    user_message = (
        f"Excerpts:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer to check:\n{answer_text}"
    )
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=2000,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return parse_json(response.content[0].text)


def summarize(verdict):
    claims = verdict.get("claims", [])
    supported = sum(1 for c in claims if c.get("supported"))
    cited = [c for c in claims if c.get("cited")]
    citation_ok = sum(1 for c in cited if c.get("citation_ok"))
    return len(claims), supported, len(cited), citation_ok


if __name__ == "__main__":
    with open("eval_set.json", encoding="utf-8") as f:
        eval_set = json.load(f)

    results = []
    tot = {"claims": 0, "supported": 0, "cited": 0, "cite_ok": 0}

    for item in eval_set:
        question = item["question"]
        try:
            text, hits = answer(question)
            verdict = judge(question, hits, text)
        except Exception as e:  # (3)
            print("ERROR |", question, "|", e)
            continue

        n, sup, nc, ok = summarize(verdict)
        tot["claims"] += n
        tot["supported"] += sup
        tot["cited"] += nc
        tot["cite_ok"] += ok

        retrieved = any(exp in h["source"] for exp in item["expected"] for h in hits)
        status = "REFUSED" if verdict.get("refused") else "answered"
        print(f"claims {sup}/{n} | cites {ok}/{nc} | retrieved: {'yes' if retrieved else 'NO'} | {status} | {question}")
        for c in verdict.get("claims", []):
            if not c.get("supported"):
                print("    UNSUPPORTED:", c["claim"])
            elif c.get("cited") and not c.get("citation_ok"):
                print("    BAD CITATION:", c["claim"], c["cited"])

        results.append({
            "question": question,
            "answer": text,
            "sources": [h["source"] for h in hits],
            "retrieved_expected": retrieved,
            "verdict": verdict,
        })

    with open("grade_results.json", "w", encoding="utf-8") as f:  # (4)
        json.dump(results, f, indent=2)

    if tot["claims"]:
        print(f"\nGrounded claims:  {tot['supported']}/{tot['claims']} = {tot['supported'] / tot['claims']:.0%}")
    if tot["cited"]:
        print(f"Correct citations: {tot['cite_ok']}/{tot['cited']} = {tot['cite_ok'] / tot['cited']:.0%}")
    print("Full details saved to grade_results.json")