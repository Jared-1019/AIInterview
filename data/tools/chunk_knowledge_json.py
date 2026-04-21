#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

DEFAULT_MIN_CHARS = 200
DEFAULT_MAX_CHARS = 500
DEFAULT_OVERLAP = 60

CHUNK_SPLIT_RE = re.compile(r"(?<=[。！？；.!?;])\s+")
CHUNK_SUFFIX_RE = re.compile(r"(?:_c\d+)+$")


def resolve_input_dir(input_dir: str) -> Path:
    path = Path(input_dir)
    if path.is_absolute():
        return path

    cwd_candidate = Path.cwd().resolve()
    script_root_candidate = Path(__file__).resolve().parents[2]
    if cwd_candidate.joinpath(path).is_dir():
        return cwd_candidate.joinpath(path).resolve()
    if script_root_candidate.joinpath(path).is_dir():
        return script_root_candidate.joinpath(path).resolve()
    return cwd_candidate


def split_to_chunks(text: str, min_chars: int, max_chars: int, overlap: int) -> List[str]:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return [text]

    sentences = [s.strip() for s in CHUNK_SPLIT_RE.split(text) if s.strip()]
    chunks = []
    current = ""

    for sentence in sentences:
        if not current:
            current = sentence
            continue
        candidate = (current + " " + sentence).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current.strip())
            current = sentence

    if current:
        chunks.append(current.strip())

    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
            continue
        final_chunks.extend(chunk[i : i + max_chars].strip() for i in range(0, len(chunk), max_chars))

    output = []
    step = max(1, max_chars - overlap)
    for chunk in final_chunks:
        if len(chunk) < min_chars:
            output.append(chunk)
            continue
        output.extend(chunk[i : i + max_chars].strip() for i in range(0, len(chunk), step))

    compact = []
    for chunk in output:
        if len(chunk) < min_chars and compact:
            compact[-1] = (compact[-1] + " " + chunk).strip()
        else:
            compact.append(chunk)

    if compact and len(compact[-1]) < min_chars and len(compact) > 1:
        tail = compact.pop()
        compact[-1] = (compact[-1] + " " + tail).strip()

    return compact


def ensure_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        metadata = {}
    for key in ["category", "difficulty", "type", "company", "position"]:
        if key not in metadata:
            metadata[key] = ""
    return metadata


def normalize_base_id(base_id: str) -> str:
    if not isinstance(base_id, str):
        return ""
    return CHUNK_SUFFIX_RE.sub("", base_id)


def process_file(path: Path, min_chars: int, max_chars: int, overlap: int, file_index: int, file_total: int) -> List[dict]:
    content = json.loads(path.read_text(encoding="utf-8"))
    total = len(content)
    print(f"[{file_index}/{file_total}] Chunking {path.name} - 0/{total}", flush=True)

    items = []
    for idx, item in enumerate(content, start=1):
        raw_id = item.get("id", "") or f"item_{idx}"
        base_id = normalize_base_id(raw_id)
        question = item.get("question", "") or item.get("q", "")
        answer = item.get("answer", "") or item.get("text", "")
        metadata = ensure_metadata(item.get("metadata", {}))

        chunks = split_to_chunks(answer, min_chars, max_chars, overlap)
        if len(chunks) == 1:
            items.append(
                {
                    "id": base_id,
                    "question": question,
                    "answer": chunks[0],
                    "metadata": metadata,
                }
            )
        else:
            for chunk_index, chunk in enumerate(chunks, start=1):
                items.append(
                    {
                        "id": f"{base_id}_c{chunk_index}",
                        "question": question,
                        "answer": chunk,
                        "metadata": metadata,
                    }
                )

        print(
            f"\r[{file_index}/{file_total}] Chunking {path.name} - {idx}/{total}",
            end="",
            flush=True,
        )

    print()
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk knowledge JSON files only (no cleaning).")
    parser.add_argument("--input-dir", default="data/knowledge", help="Directory containing JSON knowledge files.")
    parser.add_argument("--inplace", action="store_true", help="Overwrite original files.")
    parser.add_argument("--backup", action="store_true", help="Backup originals to backup/chunk_only.")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    args = parser.parse_args()

    input_dir = resolve_input_dir(args.input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    backup_dir = input_dir / "backup" / "chunk_only"
    if args.backup:
        backup_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise SystemExit("No JSON files found")

    for file_index, path in enumerate(paths, start=1):
        chunked_items = process_file(path, args.min_chars, args.max_chars, args.overlap, file_index, len(paths))

        if args.backup:
            backup_path = backup_dir / path.name
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        target = path if args.inplace else input_dir / f"{path.stem}_chunked.json"
        target.write_text(json.dumps(chunked_items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {target.name} ({len(chunked_items)} items)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
