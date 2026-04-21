#!/usr/bin/env python3
"""Unify JSON records in data/knowledge to a fixed schema.

Target schema:
{
  "id": "...",
  "question": "...",
  "answer": "...",
  "metadata": {
    "category": "...",
    "difficulty": "...",
    "type": "...",
    "company": "...",
    "position": "..."
  }
}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

QUESTION_ANSWER_PATTERN = re.compile(r"问题\s*[:：]\s*(.*?)\s*回答\s*[:：]\s*(.*)", re.S)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pick_first(item: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        if key in item and item[key] is not None:
            value = normalize_text(item[key])
            if value:
                return value
    return ""


def parse_question_answer_from_text(text: str) -> Tuple[str, str]:
    text = normalize_text(text)
    if not text:
        return "", ""

    match = QUESTION_ANSWER_PATTERN.search(text)
    if match:
        return normalize_text(match.group(1)), normalize_text(match.group(2))

    return "", text


def normalize_metadata(item: Dict[str, Any]) -> Dict[str, str]:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "category": normalize_text(metadata.get("category") or item.get("category") or ""),
        "difficulty": normalize_text(metadata.get("difficulty") or item.get("difficulty") or ""),
        "type": normalize_text(metadata.get("type") or item.get("type") or ""),
        "company": normalize_text(metadata.get("company") or item.get("company") or ""),
        "position": normalize_text(metadata.get("position") or item.get("position") or ""),
    }


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    record_id = normalize_text(item.get("id", ""))
    question = pick_first(item, ["question", "query", "q"])
    answer = pick_first(item, ["answer", "response", "a"])

    text = pick_first(item, ["text", "content"])
    text_q, text_a = parse_question_answer_from_text(text)

    if not question and text_q:
        question = text_q
    if not answer and text_a:
        answer = text_a

    return {
        "id": record_id,
        "question": question,
        "answer": answer,
        "metadata": normalize_metadata(item),
    }


def load_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return [x for x in data["data"] if isinstance(x, dict)]
        return [data]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Unify knowledge JSON schema.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--backup", action="store_true", help="Backup original files before overwriting.")
    parser.add_argument("--backup-dir", type=Path, default=Path("data/knowledge/backup/unified"))
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("*.json"))
    if not files:
        print(f"No JSON files found under {args.input_dir}")
        return 1

    if args.backup:
        args.backup_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        records = load_json(path)
        unified = [normalize_record(item) for item in records]

        if args.backup:
            backup_path = args.backup_dir / path.name
            if not backup_path.exists():
                backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        path.write_text(json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Unified: {path.name} ({len(unified)} records)")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
