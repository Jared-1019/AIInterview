#!/usr/bin/env python3
"""Split extra follow-up questions into separate embedding items.

This script processes embedding files under the knowledge folder and ensures
qa_extra text blocks containing follow-up questions such as
"面试官可能的追问1" / "面试官可能的追问2" / "追问1" are split into
separate items. Each output item will have a text field in the form:

  问题：<follow-up question> 回答：<follow-up answer>

If an original extra entry contains leading extra text before the first follow-up,
that part is preserved as a separate item.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

FOLLOW_UP_MARKER = re.compile(
    r"(?m)^(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问)\s*[:：]?\s*$"
)
QUESTION_LINE = re.compile(r"^(.*?[？?])\s*(.*)$", re.S)
ANSWER_LABEL = re.compile(r"^(简答|回答|答案|答)\s*[:：]?\s*", re.I)


def normalize_answer(answer: str) -> str:
    answer = answer.strip()
    answer = ANSWER_LABEL.sub("", answer)
    answer = re.sub(r"\s*\n\s*", " ", answer)
    answer = re.sub(r"\s+", " ", answer)
    answer = re.sub(r"\s+([，。！？；：、,.!?;:])", r"\1", answer)
    return answer.strip()


def split_follow_up_blocks(answer: str) -> List[str]:
    parts: List[str] = []
    last_end = 0
    matches = list(FOLLOW_UP_MARKER.finditer(answer))
    if not matches:
        return [answer.strip()] if answer.strip() else []

    for idx, match in enumerate(matches):
        if idx == 0 and match.start() > 0:
            prefix = answer[: match.start()].strip()
            if prefix:
                parts.append(prefix)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(answer)
        block = answer[match.start() : end].strip()
        if block:
            parts.append(block)
        last_end = end

    return [part for part in parts if part.strip()]


def extract_follow_up_question_and_answer(block: str, original_question: str) -> Dict[str, str]:
    block = block.strip()
    block = FOLLOW_UP_MARKER.sub("", block).strip()
    if not block:
        return {"question": original_question, "answer": ""}

    first_line, *rest = block.splitlines()
    first_line = first_line.strip()
    remaining = "\n".join(rest).strip()

    question = original_question
    answer = block

    matched = QUESTION_LINE.match(block)
    if matched:
        candidate_question = matched.group(1).strip()
        candidate_answer = matched.group(2).strip()
        if candidate_question.endswith("?" ) or candidate_question.endswith("？"):
            question = candidate_question
            answer = candidate_answer
    elif remaining:
        answer = normalize_answer(remaining)
    else:
        answer = normalize_answer(block)

    answer = normalize_answer(answer)
    return {"question": question, "answer": answer}


def rewrite_extra_entry(entry: Dict[str, object]) -> List[Dict[str, object]]:
    text = entry.get("text", "")
    if not isinstance(text, str):
        return [entry]

    prefix, sep, rest = text.partition(" 回答：")
    if not sep:
        return [entry]

    if not rest.strip():
        return [entry]

    blocks = split_follow_up_blocks(rest)
    new_items: List[Dict[str, object]] = []
    base_id = str(entry.get("id", ""))
    has_prefix_item = False
    suffix_index = 1

    if blocks and not FOLLOW_UP_MARKER.match(blocks[0]):
        if len(blocks) > 1:
            question_text = prefix.replace("问题：", "").strip()
            answer_text = normalize_answer(blocks[0])
            if answer_text:
                new_items.append(
                    {
                        "id": base_id,
                        "text": f"问题：{question_text} 回答：{answer_text}",
                        "metadata": entry.get("metadata", {}),
                    }
                )
                has_prefix_item = True
    
    for block in blocks:
        if not FOLLOW_UP_MARKER.search(block):
            if has_prefix_item:
                continue
            question_text = prefix.replace("问题：", "").strip()
            answer_text = normalize_answer(block)
            new_items.append(
                {
                    "id": base_id,
                    "text": f"问题：{question_text} 回答：{answer_text}",
                    "metadata": entry.get("metadata", {}),
                }
            )
            continue

        qa = extract_follow_up_question_and_answer(block, prefix.replace("问题：", "").strip())
        question_text = qa["question"]
        answer_text = qa["answer"]
        if not answer_text:
            continue
        new_items.append(
            {
                "id": f"{base_id}{suffix_index}",
                "text": f"问题：{question_text} 回答：{answer_text}",
                "metadata": entry.get("metadata", {}),
            }
        )
        suffix_index += 1

    if not new_items:
        return [entry]
    return new_items


def process_file(path: Path, output_path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    result: List[Dict[str, object]] = []
    changed = 0
    for entry in data:
        if entry.get("metadata", {}).get("type") == "qa_extra":
            rewritten = rewrite_extra_entry(entry)
            if len(rewritten) != 1 or rewritten[0].get("text") != entry.get("text"):
                changed += 1
            result.extend(rewritten)
        else:
            result.append(entry)

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Split qa_extra follow-up questions into separate embedding items.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("embedding_bagu_*.json"))
    if not files:
        print("No embedding files found in", args.input_dir)
        return 1

    for path in files:
        output_path = path if args.overwrite else path.with_name(f"fixed_{path.name}")
        changed = process_file(path, output_path)
        if changed:
            print(f"Processed {path.name}: rewritten {changed} extra entries -> {output_path.name}")
        else:
            print(f"Processed {path.name}: no changes -> {output_path.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
