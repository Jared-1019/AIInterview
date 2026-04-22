from __future__ import annotations

import json
import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import requests
from flask import Flask, jsonify, request
from sklearn.feature_extraction.text import HashingVectorizer

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RAG_DIR = BASE_DIR / "data" / "knowledge" / "rag"

RAG_DIR = Path(os.getenv("RAG_DIR", str(DEFAULT_RAG_DIR)))
DOCS_FILE = RAG_DIR / "rag_docs.jsonl"
INDEX_FILE = RAG_DIR / "rag_index.pkl"
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
RAG_BACKEND = os.getenv("RAG_BACKEND", "file")
RAG_PG_DSN = os.getenv("RAG_PG_DSN", "")
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
RAG_EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "openai")

app = Flask(__name__)

_DOCS: List[Dict[str, Any]] = []
_INDEX: Dict[str, Any] = {}


def load_docs(path: Path) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def embed_query_openai(query: str, model: str) -> np.ndarray:
    if not EMBEDDING_API_KEY:
        raise ValueError("EMBEDDING_API_KEY is required for openai backend")

    url = f"{EMBEDDING_API_BASE.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
    }
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


@lru_cache(maxsize=2)
def get_local_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_query_local(query: str, model: str) -> np.ndarray:
    sentence_model = get_local_embedding_model(model)
    vec = sentence_model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]
    return np.asarray(vec, dtype=np.float32)


def embed_query_hash(query: str, n_features: int = 384) -> np.ndarray:
    vectorizer = HashingVectorizer(
        n_features=n_features,
        alternate_sign=False,
        norm="l2",
        analyzer="char_wb",
        ngram_range=(2, 4),
    )
    matrix = vectorizer.transform([query])
    return np.asarray(matrix.toarray()[0], dtype=np.float32)


def to_pgvector_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec.tolist()) + "]"


def retrieve_pgvector(query: str, top_k: int) -> List[Dict[str, Any]]:
    if not RAG_PG_DSN:
        raise ValueError("RAG_PG_DSN is required when RAG_BACKEND=pgvector")

    if RAG_EMBEDDING_PROVIDER == "hash":
        query_vec = embed_query_hash(query)
    elif RAG_EMBEDDING_PROVIDER == "local":
        query_vec = embed_query_local(query, model=RAG_EMBEDDING_MODEL)
    else:
        query_vec = embed_query_openai(query, model=RAG_EMBEDDING_MODEL)
    vector_literal = to_pgvector_literal(query_vec)

    import psycopg

    sql = """
    SELECT
      doc_id,
      question,
      answer,
      metadata,
      source_file,
      1 - (embedding <=> %s::vector) AS score
    FROM rag_documents
    ORDER BY embedding <=> %s::vector
    LIMIT %s
    """

    with psycopg.connect(RAG_PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (vector_literal, vector_literal, top_k))
            rows = cur.fetchall()

    results: List[Dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "id": row[0],
                "question": row[1],
                "answer": row[2],
                "metadata": row[3] or {},
                "source_file": row[4],
                "score": float(row[5]),
            }
        )
    return results


def retrieve(query: str, top_k: int) -> List[Dict[str, Any]]:
    if RAG_BACKEND == "pgvector":
        return retrieve_pgvector(query, top_k)

    backend = _INDEX.get("backend")
    if backend == "openai":
        query_vec = embed_query_openai(query, model=_INDEX["model"])
        vectors = _INDEX["vectors"]
        scores = vectors @ query_vec
    elif backend == "tfidf":
        vectorizer = _INDEX["vectorizer"]
        matrix = _INDEX["matrix"]
        query_vec = vectorizer.transform([query])
        scores = (matrix @ query_vec.T).toarray().ravel()
    else:
        raise ValueError(f"Unsupported index backend: {backend}")

    top_indices = np.argsort(scores)[::-1][:top_k]
    results: List[Dict[str, Any]] = []
    for idx in top_indices:
        doc = _DOCS[int(idx)]
        results.append(
            {
                "score": float(scores[int(idx)]),
                "id": doc.get("id"),
                "question": doc.get("question"),
                "answer": doc.get("answer"),
                "metadata": doc.get("metadata", {}),
                "source_file": doc.get("source_file"),
            }
        )

    return results


@app.route("/health", methods=["GET"])
def health() -> Any:
    if RAG_BACKEND == "pgvector":
        if not RAG_PG_DSN:
            return jsonify({"ok": False, "message": "RAG_PG_DSN is missing"}), 503
        try:
            import psycopg

            with psycopg.connect(RAG_PG_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM rag_documents")
                    doc_count = cur.fetchone()[0]
            return jsonify(
                {
                    "ok": True,
                    "backend": "pgvector",
                    "doc_count": doc_count,
                    "embedding_provider": RAG_EMBEDDING_PROVIDER,
                    "embedding_model": RAG_EMBEDDING_MODEL,
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 503

    if not _DOCS or not _INDEX:
        return jsonify({"ok": False, "message": "RAG knowledge base not loaded"}), 503
    return jsonify(
        {
            "ok": True,
            "backend": _INDEX.get("backend", "file"),
            "doc_count": len(_DOCS),
            "rag_dir": str(RAG_DIR),
        }
    )


@app.route("/api/retrieve", methods=["POST"])
def api_retrieve() -> Any:
    payload = request.get_json(force=True)
    query = str(payload.get("query", "")).strip()
    top_k = int(payload.get("top_k", 5))

    if not query:
        return jsonify({"error": "query is required"}), 400
    if top_k <= 0:
        return jsonify({"error": "top_k must be > 0"}), 400

    try:
        results = retrieve(query, top_k=min(top_k, 20))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"query": query, "top_k": top_k, "results": results})


def load_knowledge_base() -> None:
    if RAG_BACKEND == "pgvector":
        if not RAG_PG_DSN:
            raise ValueError("RAG_PG_DSN is required when RAG_BACKEND=pgvector")
        return

    global _DOCS, _INDEX
    if not DOCS_FILE.exists() or not INDEX_FILE.exists():
        raise FileNotFoundError(
            f"Missing RAG files in {RAG_DIR}. Build them first with build_rag_knowledge_base.py"
        )

    _DOCS = load_docs(DOCS_FILE)
    with INDEX_FILE.open("rb") as f:
        _INDEX = pickle.load(f)


if __name__ == "__main__":
    load_knowledge_base()
    app.run(host="0.0.0.0", port=3001, debug=True)
