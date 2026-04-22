from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Dict, List

import numpy as np
import requests


def load_docs(path: Path) -> List[Dict[str, object]]:
    docs: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def embed_query_openai(
    query: str,
    api_base: str,
    api_key: str,
    model: str,
) -> np.ndarray:
    url = f"{api_base.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": query}

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    body = response.json()
    data = body.get("data", [])
    if not data:
        raise ValueError("Embedding API returned empty data")
    embedding = data[0].get("embedding")
    if not embedding:
        raise ValueError("Embedding API returned invalid embedding")

    vec = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def cosine_top_k(vectors: np.ndarray, query_vec: np.ndarray, top_k: int) -> List[int]:
    scores = vectors @ query_vec
    order = np.argsort(scores)[::-1]
    return order[:top_k].tolist()


def main() -> int:
    parser = argparse.ArgumentParser(description="Query built RAG knowledge base.")
    parser.add_argument("query", help="Search query text")
    parser.add_argument("--rag-dir", type=Path, default=Path("data/knowledge/rag"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--api-base", default=os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("EMBEDDING_API_KEY", ""))
    args = parser.parse_args()

    docs_file = args.rag_dir / "rag_docs.jsonl"
    index_file = args.rag_dir / "rag_index.pkl"

    if not docs_file.exists() or not index_file.exists():
        raise FileNotFoundError(f"RAG files not found in {args.rag_dir}")

    docs = load_docs(docs_file)
    with index_file.open("rb") as f:
        index = pickle.load(f)

    backend = index.get("backend")
    if backend == "openai":
        if not args.api_key:
            raise ValueError("EMBEDDING_API_KEY is required to query openai index")
        query_vec = embed_query_openai(
            query=args.query,
            api_base=args.api_base,
            api_key=args.api_key,
            model=index["model"],
        )
        vectors = index["vectors"]
        top_indices = cosine_top_k(vectors, query_vec, args.top_k)
        scores = (vectors @ query_vec).tolist()
    elif backend == "tfidf":
        vectorizer = index["vectorizer"]
        matrix = index["matrix"]
        query_vec = vectorizer.transform([args.query])
        sim = (matrix @ query_vec.T).toarray().ravel()
        top_indices = np.argsort(sim)[::-1][: args.top_k].tolist()
        scores = sim.tolist()
    else:
        raise ValueError(f"Unsupported index backend: {backend}")

    print(f"Backend: {backend}")
    print(f"Top {args.top_k} for query: {args.query}\n")

    for rank, idx in enumerate(top_indices, start=1):
        doc = docs[idx]
        score = float(scores[idx])
        print(f"[{rank}] score={score:.4f} id={doc.get('id')} source={doc.get('source_file')}")
        print(f"Q: {doc.get('question', '')}")
        answer = str(doc.get("answer", ""))
        preview = answer[:220] + ("..." if len(answer) > 220 else "")
        print(f"A: {preview}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
