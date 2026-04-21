
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

import requests

EMBEDDING_GLOB = "embedding_bagu_*.json"
FOLLOW_UP_MARKER = re.compile(
    r"(?m)^(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问)\s*[:：]?\s*$"
)
QUESTION_SPLIT = re.compile(r"(?=问题：)")
SPECIAL_SYMBOLS = re.compile(
    r"[①-⑳•·●▪■►▶◀◁◆◇▲△▼▽♥♡♪♫→←↑↓♦✔✕✖✗✘…~`@#￥%&*+=<>\[\]{}\\|/^]"
)
LINE_BREAKS = re.compile(r"[\r\n]+")
MULTI_SPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r", "\n")
    text = LINE_BREAKS.sub(" ", text)
    text = SPECIAL_SYMBOLS.sub(" ", text)
    text = MULTI_SPACE.sub(" ", text)
    text = text.strip()
    text = text.replace("  ", " ")
    return text


def extract_qa_pairs(text: str) -> List[Dict[str, str]]:
    text = normalize_text(text)
    blocks = [block.strip() for block in QUESTION_SPLIT.split(text) if block.strip()]
    pairs: List[Dict[str, str]] = []

    for block in blocks:
        if not block:
            continue
        if "回答：" in block:
            question, answer = block.split("回答：", 1)
            question = question.strip()
            answer = answer.strip()
        else:
            m = re.match(r"(.+?[？?])\s*(.*)", block)
            if m:
                question = m.group(1).strip()
                answer = m.group(2).strip()
            else:
                question = block.strip()
                answer = ""
        question = normalize_text(question)
        answer = normalize_text(answer)
        if question or answer:
            pairs.append({"question": question, "answer": answer})

    return pairs


def split_follow_up_blocks(text: str) -> List[str]:
    text = normalize_text(text)
    matches = list(FOLLOW_UP_MARKER.finditer(text))
    if not matches:
        return [text]

    parts: List[str] = []
    start = 0
    for idx, match in enumerate(matches):
        if idx == 0 and match.start() > 0:
            prefix = text[: match.start()].strip()
            if prefix:
                parts.append(prefix)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        part = text[match.start():end].strip()
        if part:
            parts.append(part)
        start = end

    return [part for part in parts if part.strip()]


def normalize_question(question: str) -> str:
    question = question.strip()
    question = re.sub(r"^(问题：)+", "", question)
    question = re.sub(r"^(.*?问题：)\s*问题：", r"\1", question)
    return normalize_text(question)


def normalize_answer(answer: str) -> str:
    answer = answer.strip()
    answer = re.sub(r"^(回答：)+", "", answer)
    answer = normalize_text(answer)
    return answer


LLM_SERVER_URL = "http://127.0.0.1:3000/api/chat"


def print_progress(message: str, end: str = "\r") -> None:
    sys.stdout.write(message + end)
    sys.stdout.flush()


def estimate_question_count(entry: Dict[str, object]) -> int:
    text = str(entry.get("text", ""))
    if not text.strip():
        return 0

    if FOLLOW_UP_MARKER.search(text):
        parts = split_follow_up_blocks(text)
    else:
        parts = [text]

    count = 0
    for part in parts:
        count += len(extract_qa_pairs(part))
    return max(1, count)


def ask_llm(text: str) -> str:
    response = requests.post(LLM_SERVER_URL, json={"message": text}, stream=True, timeout=120)
    response.raise_for_status()

    result_text = ''
    for chunk in response.iter_content(chunk_size=4096):
        if not chunk:
            continue
        result_text += chunk.decode('utf-8', errors='ignore')

    return result_text.strip()


def llm_extract_qa_pairs(text: str) -> List[Dict[str, str]]:
    prompt = (
        "请将下面的内容拆分成适合向量检索的问答对。"
        "\n- 如果文本中包含多个问题与回答，请分别拆分成独立项。"
        "\n- 如果存在追问、面试官追问等，请将每个追问当成独立的问题。"
        "\n- 只输出一个 JSON 数组，不要添加多余文字。"
        "\n- 格式示例：[{\"question\":\"...\",\"answer\":\"...\"}, ...]。"
        "\n文本：\n" + text
    )

    response_text = ask_llm(prompt)
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, list):
            normalized: List[Dict[str, str]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                question = normalize_question(str(item.get('question', '')).strip())
                answer = normalize_answer(str(item.get('answer', '')).strip())
                if question or answer:
                    normalized.append({"question": question, "answer": answer})
            if normalized:
                return normalized
    except json.JSONDecodeError:
        pass

    return extract_qa_pairs(text)


def build_fragment(entry_id: str, question: str, answer: str, suffix: int | None = None) -> Dict[str, object]:
    item_id = entry_id if suffix is None else f"{entry_id}{suffix}"
    question = normalize_question(question)
    answer = normalize_answer(answer)
    text = f"问题：{question} 回答：{answer}".strip()
    return {"id": item_id, "text": text, "metadata": {}}


def rewrite_entry(
    entry: Dict[str, object],
    use_llm: bool = False,
    progress_callback=None,
) -> List[Dict[str, object]]:
    text = str(entry.get("text", ""))
    if not text.strip():
        return [entry]

    fragments: List[Dict[str, object]] = []
    if FOLLOW_UP_MARKER.search(text):
        parts = split_follow_up_blocks(text)
    else:
        parts = [text]

    suffix = 1
    base_id = str(entry.get("id", ""))
    for part in parts:
        qa_pairs = llm_extract_qa_pairs(part) if use_llm else extract_qa_pairs(part)
        if len(qa_pairs) > 1:
            for pair in qa_pairs:
                if not pair["question"]:
                    continue
                fragments.append(
                    {
                        "id": base_id if suffix == 1 and len(parts) == 1 else f"{base_id}{suffix}",
                        "text": build_fragment("", pair["question"], pair["answer"])["text"],
                        "metadata": entry.get("metadata", {}),
                    }
                )
                suffix += 1
                if progress_callback:
                    progress_callback()
        elif qa_pairs:
            qa = qa_pairs[0]
            fragments.append(
                {
                    "id": base_id if suffix == 1 and len(parts) == 1 else f"{base_id}{suffix}",
                    "text": build_fragment("", qa["question"], qa["answer"])["text"],
                    "metadata": entry.get("metadata", {}),
                }
            )
            suffix += 1
            if progress_callback:
                progress_callback()
        else:
            fragments.append(entry)
            if progress_callback:
                progress_callback()

    return fragments


def process_file(path: Path, overwrite: bool, use_llm: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    output_path = path if overwrite else path.with_name(f"fixed_{path.name}")
    result: List[Dict[str, object]] = []
    changed = 0

    total_questions = sum(estimate_question_count(entry) for entry in data)
    if total_questions == 0:
        print(f"    no questions found in {path.name}")
        question_counter = 0
    else:
        print(f"    processing {total_questions} questions in {path.name}")
        question_counter = 0

    def on_question_processed() -> None:
        nonlocal question_counter
        question_counter += 1
        if total_questions > 0:
            percent = question_counter * 100 // total_questions
            print_progress(
                f"      question {question_counter}/{total_questions} processed ({percent}%)"
            )
        else:
            print_progress(f"      question {question_counter} processed")

    for entry in data:
        rewritten = rewrite_entry(entry, use_llm=use_llm, progress_callback=on_question_processed)
        if len(rewritten) != 1 or rewritten[0].get("text") != entry.get("text"):
            changed += 1
        result.extend(rewritten)

    if total_questions:
        print_progress("", end="\n")

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite embedding texts into vector-retrieval fragments.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--overwrite", action="store_true", help="Overwrite original files with cleaned versions.")
    parser.add_argument("--backup", action="store_true", help="Backup original files before overwriting.")
    parser.add_argument("--llm", action="store_true", help="Use backend llm_server for semantic QA detection.")
    args = parser.parse_args()

    files = sorted(args.input_dir.glob(EMBEDDING_GLOB))
    if not files:
        print("No embedding files found in", args.input_dir)
        return 1

    if args.llm:
        print("Using backend llm_server for semantic validation of QA text.")

    if args.overwrite and args.backup:
        backup_dir = args.input_dir / "backup"
        backup_dir.mkdir(exist_ok=True)
        for path in files:
            backup_path = backup_dir / path.name
            if not backup_path.exists():
                backup_path.write_bytes(path.read_bytes())

    total_changed = 0
    total_files = len(files)
    for index, path in enumerate(files, start=1):
        print(f"[{index}/{total_files}] {path.name}")
        changed = process_file(path, overwrite=args.overwrite, use_llm=args.llm)
        total_changed += changed
        status = "updated" if changed else "no change"
        print(f"    {path.name}: {status}, {changed} entries rewritten")

    print(f"Total changed files: {total_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
