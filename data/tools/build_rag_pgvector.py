from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List

import psycopg
import requests
from sklearn.feature_extraction.text import HashingVectorizer

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


def embed_with_openai_compatible(
    texts: List[str],
    api_base: str,
    api_key: str,
    model: str,
    batch_size: int,
) -> List[List[float]]:
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

    return all_vectors


@lru_cache(maxsize=2)
def get_local_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_with_local_model(texts: List[str], model_name: str, batch_size: int) -> List[List[float]]:
    model = get_local_embedding_model(model_name)
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_with_hashing(texts: List[str], n_features: int = 384) -> List[List[float]]:
    vectorizer = HashingVectorizer(
        n_features=n_features,
        alternate_sign=False,
        norm="l2",
        analyzer="char_wb",
        ngram_range=(2, 4),
    )
    matrix = vectorizer.transform(texts)
    return matrix.toarray().astype("float32").tolist()


def to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def run_schema_init(conn: psycopg.Connection, sql_path: Path) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()


def insert_docs(
    conn: psycopg.Connection,
    docs: List[RagDoc],
    vectors: List[List[float]],
    model: str,
    upsert: bool,
) -> None:
    if len(docs) != len(vectors):
        raise ValueError("docs and vectors count mismatch")

    sql_insert = """
    INSERT INTO rag_documents
      (doc_id, text_content, question, answer, metadata, source_file, embedding_model, embedding)
    VALUES
      (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::vector)
    """

    if upsert:
        sql_insert += """
        ON CONFLICT (doc_id) DO UPDATE SET
          text_content = EXCLUDED.text_content,
          question = EXCLUDED.question,
          answer = EXCLUDED.answer,
          metadata = EXCLUDED.metadata,
          source_file = EXCLUDED.source_file,
          embedding_model = EXCLUDED.embedding_model,
          embedding = EXCLUDED.embedding
        """

    rows = []
    for doc, vec in zip(docs, vectors):
        rows.append(
            (
                doc.doc_id,
                doc.text,
                doc.question,
                doc.answer,
                json.dumps(doc.metadata, ensure_ascii=False),
                doc.source_file,
                model,
                to_pgvector_literal(vec),
            )
        )

    with conn.cursor() as cur:
        cur.executemany(sql_insert, rows)
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RAG docs and ingest into PostgreSQL + pgvector.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--dsn", default=os.getenv("RAG_PG_DSN", ""))
    parser.add_argument("--model", default=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"))
    parser.add_argument(
        "--embedding-provider",
        choices=["openai", "local", "hash"],
        default=os.getenv("RAG_EMBEDDING_PROVIDER", "openai"),
    )
    parser.add_argument("--api-base", default=os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.getenv("EMBEDDING_API_KEY", ""))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--schema-sql", type=Path, default=Path("data/tools/init_rag_pgvector.sql"))
    parser.add_argument("--skip-init-schema", action="store_true")
    parser.add_argument("--no-upsert", action="store_true")
    args = parser.parse_args()

    if not args.dsn:
        raise ValueError("RAG_PG_DSN (or --dsn) is required")
    if args.embedding_provider == "openai" and not args.api_key:
        raise ValueError("EMBEDDING_API_KEY (or --api-key) is required")

    docs = build_docs(args.input_dir, args.input_glob)
    if not docs:
        print(f"No records found under {args.input_dir} with glob {args.input_glob}")
        return 1

    texts = [doc.text for doc in docs]
    if args.embedding_provider == "hash":
        vectors = embed_with_hashing(texts=texts)
    elif args.embedding_provider == "local":
        vectors = embed_with_local_model(
            texts=texts,
            model_name=args.model,
            batch_size=args.batch_size,
        )
    else:
        vectors = embed_with_openai_compatible(
            texts=texts,
            api_base=args.api_base,
            api_key=args.api_key,
            model=args.model,
            batch_size=args.batch_size,
        )

    with psycopg.connect(args.dsn) as conn:
        if not args.skip_init_schema:
            run_schema_init(conn, args.schema_sql)
        insert_docs(conn, docs, vectors, model=args.model, upsert=not args.no_upsert)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rag_documents")
            total = cur.fetchone()[0]

    print("PostgreSQL + pgvector ingest completed.")
    print(f"Inserted/Updated docs: {len(docs)}")
    print(f"Total docs in table: {total}")
    print(f"Embedding provider: {args.embedding_provider}")
    print(f"Embedding model: {args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
