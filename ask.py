import sys
import anthropic
from retrieve import retrieve

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You answer questions about FastAPI using ONLY the documentation excerpts provided.

Rules:
- Every statement must be supported by the excerpts. Do not add recommendations, comparisons, best practices, or examples that the excerpts do not contain, even if you know them to be true.
- Only include code or commands that appear in the excerpts. If the excerpts contain no example, say so instead of writing one.
- If the excerpts do not contain the answer, say you could not find it in the documentation. Do not guess.
- Be concise. Put the excerpt number like [2] right after each statement it supports."""  # (1)


def build_context(hits):
    parts = []
    for i, h in enumerate(hits, start=1):
        parts.append(f"[{i}] (source: {h['source']})\n{h['text']}")  # (2)
    return "\n\n---\n\n".join(parts)


def answer(question, n=5):
    hits = retrieve(question, n=n)  # (3)
    context = build_context(hits)
    user_message = f"Documentation excerpts:\n\n{context}\n\nQuestion: {question}"
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,  # (4)
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text, hits


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    text, hits = answer(question)
    print(text)
    print("\nRetrieved sources:")  # (5)
    for i, h in enumerate(hits, start=1):
        print(f"  [{i}] {h['source']}")