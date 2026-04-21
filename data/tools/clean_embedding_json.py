import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

FOLLOW_UP_MARKER = re.compile(r"(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问|Q\d+)\s*[:：]?", re.I)
QUESTION_PREFIX = r"(?:问题[:：]|Q\d+[:：]|面试官可能的追问\d*[:：]?|面试官很能追问\d*[:：]?|追问\d*[:：]?)"
QUESTION_SPLIT = re.compile(rf"(?={QUESTION_PREFIX})")


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = text.strip()
    return text


ANSWER_PREFIX = r"(?:回答[:：]|A\d+[:：]?)"


def parse_question_answer(text: str) -> tuple[str, str]:
    text = normalize_text(text)
    pattern = re.compile(rf"{QUESTION_PREFIX}(.*?){ANSWER_PREFIX}(.*)", re.S)
    m = pattern.search(text)
    if m:
        question = normalize_text(m.group(1))
        answer = normalize_text(m.group(2))
        return question, answer

    return "", text


def strip_repeated_question(question: str, answer: str) -> str:
    if not question or not answer:
        return answer
    answer = answer.strip()
    if answer.startswith(question):
        remainder = answer[len(question):].lstrip(" ：: ")
        if remainder:
            return remainder
    trimmed = question.rstrip("？?。.")
    if answer.startswith(trimmed):
        remainder = answer[len(trimmed):].lstrip(" ：: ")
        if remainder:
            return remainder
    return answer


def infer_question_from_answer(answer: str) -> str:
    answer = answer.strip()
    if not answer:
        return ""
    if answer.startswith("问题") or re.match(r"^[QA]\d+[:：]", answer):
        return ""

    title_match = re.match(r"^(.+?)(?:[:：]|详解|解析|什么是|是什么|为什么|如何|怎么)", answer)
    if title_match:
        concept = title_match.group(1).strip()
        if concept and not re.fullmatch(r"[QA]\d+", concept):
            return f"什么是{concept}？"

    defn = re.search(r"^(.+?)的定义(?:是|：)", answer)
    if defn:
        concept = defn.group(1).strip()
        if concept and not re.fullmatch(r"[QA]\d+", concept):
            return f"什么是{concept}？"

    is_match = re.match(r"^(.+?)是", answer)
    if is_match:
        concept = is_match.group(1).strip()
        if len(concept) > 1 and not re.fullmatch(r"[QA]\d+", concept):
            return f"什么是{concept}？"

    return ""


def strip_followup_prefix(question: str) -> str:
    if not question:
        return ""
    question = question.strip()
    question = re.sub(r'^(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|Q\d+)\s*[:：]?\s*', '', question)
    question = re.sub(r'^[\.\s]+', '', question)
    return question.strip()


def strip_answer_prefix(answer: str) -> str:
    if not answer:
        return ""
    answer = answer.strip()
    answer = re.sub(r'^(?:A\d+|Q\d+)\s*[:：]?\s*', '', answer)
    return answer.strip()


def split_followup_answer(answer: str) -> List[Dict[str, str]]:
    answer = normalize_text(answer)
    if not FOLLOW_UP_MARKER.search(answer):
        return [{"type": "main", "question": "", "answer": answer}]

    matches = list(FOLLOW_UP_MARKER.finditer(answer))
    parts: List[str] = []
    start = 0
    for idx, match in enumerate(matches):
        if match.start() > start:
            prefix = answer[start:match.start()].strip()
            if prefix:
                parts.append(prefix)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(answer)
        segment = answer[match.start():end].strip()
        parts.append(segment)
        start = end

    results = []
    if parts:
        first = parts[0]
        if not FOLLOW_UP_MARKER.match(first):
            results.append({"type": "main", "question": "", "answer": normalize_text(first)})
    for part in parts:
        match = FOLLOW_UP_MARKER.match(part)
        if not match:
            continue
        question = match.group(1).strip()
        body = part[match.end():].strip()
        if body:
            sub_q_match = re.match(r"^(.*?[？?])\s*(.*)$", body, re.S)
            if sub_q_match:
                candidate = sub_q_match.group(1).strip()
                if candidate and len(candidate) > 2:
                    question = candidate
                    body = sub_q_match.group(2).strip()
        results.append({"type": "followup", "question": strip_followup_prefix(question), "answer": normalize_text(body)})

    return results


def split_nested_qa(text: str) -> List[tuple[str, str]]:
    parts = [part.strip() for part in QUESTION_SPLIT.split(text) if part.strip()]
    qa_pairs = []
    for part in parts:
        q, a = parse_question_answer(part)
        if a and '问题：' in a and '回答：' in a:
            qa_pairs.extend(split_nested_qa(a))
        else:
            qa_pairs.append((q, a))
    return qa_pairs


def clean_pair(question: str, answer: str) -> tuple[str, str]:
    question = normalize_text(question)
    question = strip_followup_prefix(question)
    answer = normalize_text(answer)
    answer = strip_answer_prefix(answer)
    answer = strip_repeated_question(question, answer)

    if not question:
        question_candidate = infer_question_from_answer(answer)
        if question_candidate:
            question = question_candidate

    if question and not question.endswith(('？', '?')):
        question = question.rstrip('。．. ') + '？'

    return question.strip(), answer.strip()


def process_entry(entry: Dict[str, object]) -> List[Dict[str, object]]:
    text = normalize_text(str(entry.get("text", "")))
    if not text:
        return []

    cleaned_pairs = []
    outer_qa = [(q, a) for q, a in split_nested_qa(text) if a.strip()]
    for question, answer in outer_qa:
        answer = strip_repeated_question(question, answer)
        qa_pairs = split_followup_answer(answer)
        if len(qa_pairs) == 1 and qa_pairs[0]["type"] == "main":
            q, a = clean_pair(question, qa_pairs[0]["answer"])
            if q and a:
                cleaned_pairs.append({"question": q, "answer": a, "type": entry.get("metadata", {}).get("type", "qa")})
        else:
            main = qa_pairs[0]
            q, a = clean_pair(question, normalize_text(main["answer"]))
            if q and a:
                cleaned_pairs.append({"question": q, "answer": a, "type": entry.get("metadata", {}).get("type", "qa")})
            for followup in qa_pairs[1:]:
                fq, fa = clean_pair(followup.get("question", ""), followup.get("answer", ""))
                if not fq:
                    fq = question
                if fq and fa:
                    cleaned_pairs.append({"question": fq, "answer": fa, "type": "qa_followup"})

    return cleaned_pairs


def clean_file(path: Path, backup_dir: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    cleaned: List[Dict[str, object]] = []
    changed = 0
    for entry in data:
        original_text = normalize_text(str(entry.get("text", "")))
        cleaned_pairs = process_entry(entry)
        if not cleaned_pairs:
            continue

        base_id = str(entry.get("id", ""))
        for idx, pair in enumerate(cleaned_pairs, start=1):
            item_id = base_id if idx == 1 else f"{base_id}_{idx}"
            cleaned_text = f"问题：{pair['question']} 回答：{pair['answer']}"
            metadata = dict(entry.get("metadata", {}))
            if pair["type"] == "qa_followup":
                metadata["type"] = "qa_followup"
            cleaned.append({"id": item_id, "text": cleaned_text, "metadata": metadata})
        if len(cleaned_pairs) != 1 or cleaned[ - len(cleaned_pairs) ]["text"] != original_text:
            changed += 1

    backup_path = backup_dir / path.name
    if not backup_path.exists():
        backup_path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean QA embedding JSON files in the knowledge folder.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--backup-dir", type=Path, default=Path("data/knowledge/backup/cleaned"))
    args = parser.parse_args()

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(args.input_dir.glob("embedding_bagu_*.json"))
    if not files:
        print("No embedding files found in", args.input_dir)
        return 1

    total_changed = 0
    for path in files:
        changed = clean_file(path, args.backup_dir)
        print(f"{path.name}: cleaned {changed} entries")
        total_changed += changed

    print(f"Done. Total changed entries: {total_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
