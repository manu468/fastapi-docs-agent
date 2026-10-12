import sys
import chromadb

client = chromadb.PersistentClient(path="chroma_db")
collection = client.get_collection(name="fastapi_docs")


def retrieve(question, n=3):
    results = collection.query(query_texts=[question], n_results=n)  # (1)
    hits = []
    for doc, meta, dist in zip(  # (2)
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"text": doc, "source": meta["source"], "distance": dist})
    return hits


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])  # (3)
    for h in retrieve(question):
        print(f"--- distance {h['distance']:.3f} | {h['source']}")
        print(h["text"][:300])
        print()