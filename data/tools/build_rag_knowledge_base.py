from __future__ import annotations

import argparse
import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import requests
from sklearn.feature_extraction.text import TfidfVectorizer

DEFAULT_INPUT_GLOB = "embedding_*_chunked.json"


@dataclass
class RagDoc:
    doc_id: str
    text: str
    question: str
    answer: str
    metadata: Dict[str, object]
    source_file: str


def iter_records(files: Iterable[Path]) -> Iterable[tuple[Path, dict]]:
    for file_path in files:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            if isinstance(item, dict):
                yield file_path, item


def build_docs(input_dir: Path, input_glob: str) -> List[RagDoc]:
    files = sorted(input_dir.glob(input_glob))
    docs: List[RagDoc] = []

    for file_path, item in iter_records(files):
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question and not answer:
            continue

        doc_id = str(item.get("id", "")).strip() or f"{file_path.stem}_{len(docs) + 1}"
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        text = f"问题：{question}\n回答：{answer}".strip()
        docs.append(
            RagDoc(
                doc_id=doc_id,
                text=text,
                question=question,
                answer=answer,
                metadata=metadata,
                source_file=file_path.name,
            )
        )

    return docs


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def embed_with_openai_compatible(
    texts: List[str],
    api_base: str,
    api_key: str,
    model: str,
    batch_size: int,
) -> np.ndarray:
    api_base = api_base.rstrip("/")
    url = f"{api_base}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    all_vectors: List[List[float]] = []
    total = len(texts)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        payload = {"model": model, "input": texts[start:end]}
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()

        data = body.get("data", [])
        if not isinstance(data, list):
            raise ValueError("Unexpected embedding response format: missing data list")

        vectors = [item.get("embedding") for item in data if isinstance(item, dict)]
        if len(vectors) != (end - start):
            raise ValueError("Embedding response count does not match request batch size")

        all_vectors.extend(vectors)
        print(f"Embedded {end}/{total}")

    arr = np.asarray(all_vectors, dtype=np.float32)
    return normalize(arr)


def build_tfidf_index(texts: List[str]) -> tuple[TfidfVectorizer, np.ndarray]:
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        min_df=1,
        max_df=0.98,
        norm="l2",
    )
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RAG knowledge base from chunked JSON files.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output-dir", type=Path, default=Path("data/knowledge/rag"))
    parser.add_argument("--backend", choices=["tfidf", "openai"], default="tfidf")
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--api-base", default=os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("EMBEDDING_API_KEY", ""))
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    docs = build_docs(args.input_dir, args.input_glob)
    if not docs:
        print(f"No records found under {args.input_dir} with glob {args.input_glob}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    docs_file = args.output_dir / "rag_docs.jsonl"
    index_file = args.output_dir / "rag_index.pkl"

    with docs_file.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(
                json.dumps(
                    {
                        "id": doc.doc_id,
                        "text": doc.text,
                        "question": doc.question,
                        "answer": doc.answer,
                        "metadata": doc.metadata,
                        "source_file": doc.source_file,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    texts = [doc.text for doc in docs]

    if args.backend == "openai":
        if not args.api_key:
            raise ValueError("EMBEDDING_API_KEY is required when backend=openai")
        vectors = embed_with_openai_compatible(
            texts=texts,
            api_base=args.api_base,
            api_key=args.api_key,
            model=args.model,
            batch_size=args.batch_size,
        )
        index_payload = {
            "backend": "openai",
            "model": args.model,
            "vectors": vectors,
            "doc_count": len(docs),
        }
    else:
        vectorizer, matrix = build_tfidf_index(texts)
        index_payload = {
            "backend": "tfidf",
            "model": "tfidf-charwb-2-4",
            "vectorizer": vectorizer,
            "matrix": matrix,
            "doc_count": len(docs),
        }

    with index_file.open("wb") as f:
        pickle.dump(index_payload, f)

    print("RAG knowledge base built successfully.")
    print(f"Docs: {len(docs)}")
    print(f"Docs file: {docs_file}")
    print(f"Index file: {index_file}")
    print(f"Backend: {index_payload['backend']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
