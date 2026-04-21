#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

INVALID_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFD]")
NUMBERING_RE = re.compile(r"(?:(?:^|[。！？；,，\n])\s*)(?:\d+[\.、\)]|[一二三四五六七八九十]+[、\.\)]|（\d+）|（[一二三四五六七八九十]）)\s*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；.!?;])")


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


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\u3000", " ")
    text = text.replace("\u00A0", " ")
    text = text.replace("\u2028", " ")
    text = text.replace("\u2029", " ")
    text = INVALID_CHAR_RE.sub("", text)
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_question(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"^(问题|问)[：: ]*", "", text)
    text = NUMBERING_RE.sub("", text)
    return text.strip()


def strip_trailing_digit_noise(text: str) -> str:
    # Remove trailing standalone digit tokens like "1 2 3 4 ..." in linear time.
    tokens = text.split()
    i = len(tokens) - 1
    digit_count = 0
    while i >= 0 and tokens[i].isdigit():
        digit_count += 1
        i -= 1
    if digit_count >= 4:
        tokens = tokens[: i + 1]
    return " ".join(tokens)


def clean_answer(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text)
    text = re.sub(r"^(简要回答|详细回答|答案|回答)[：:]?", "", text)

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    filtered = []
    for sentence in sentences:
        if re.match(r"^(例如|比如|例如说|比如说)[：:]?", sentence) and len(sentence) <= 40:
            continue
        if re.match(r"^(注|注释)[：:]?", sentence) and len(sentence) <= 40:
            continue
        filtered.append(sentence)

    text = " ".join(filtered)
    text = re.sub(r"\s*([，。！？；：,.!?;:])\s*", r"\1 ", text)
    text = re.sub(r"\s+([)）\]}])", r"\1", text)
    text = re.sub(r"([([{])\s+", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    text = strip_trailing_digit_noise(text)
    return text.strip()


def ensure_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        metadata = {}
    for key in ["category", "difficulty", "type", "company", "position"]:
        if key not in metadata:
            metadata[key] = ""
    return metadata


def process_file(path: Path, file_index: int, file_total: int) -> List[dict]:
    content = json.loads(path.read_text(encoding="utf-8"))
    total = len(content)
    print(f"[{file_index}/{file_total}] Cleaning {path.name} - 0/{total}", flush=True)

    items = []
    for idx, item in enumerate(content, start=1):
        item_id = item.get("id", "") or f"item_{idx}"
        print(
            f"\r[{file_index}/{file_total}] Cleaning {path.name} - {idx}/{total} ({item_id})",
            end="",
            flush=True,
        )

        question = item.get("question", "") or item.get("q", "")
        answer = item.get("answer", "") or item.get("text", "")
        if not question and not answer:
            continue

        items.append(
            {
                "id": item.get("id", "") or clean_question(question)[:20].replace(" ", "_"),
                "question": clean_question(question),
                "answer": clean_answer(answer),
                "metadata": ensure_metadata(item.get("metadata", {})),
            }
        )

    print()
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean knowledge JSON files only (no chunking).")
    parser.add_argument("--input-dir", default="data/knowledge", help="Directory containing JSON knowledge files.")
    parser.add_argument("--inplace", action="store_true", help="Overwrite original files.")
    parser.add_argument("--backup", action="store_true", help="Backup originals to backup/clean_only.")
    args = parser.parse_args()

    input_dir = resolve_input_dir(args.input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    backup_dir = input_dir / "backup" / "clean_only"
    if args.backup:
        backup_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise SystemExit("No JSON files found")

    for file_index, path in enumerate(paths, start=1):
        cleaned_items = process_file(path, file_index, len(paths))

        if args.backup:
            backup_path = backup_dir / path.name
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        target = path if args.inplace else input_dir / f"{path.stem}_cleaned.json"
        target.write_text(json.dumps(cleaned_items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {target.name} ({len(cleaned_items)} items)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
