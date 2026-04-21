#!/usr/bin/env python3
"""Clean and structure knowledge data for RAG embedding.

This script reads JSON files from the knowledge folder under the current
script directory, cleans each page into question/summary/detail/extra fields,
and optionally generates embedding-ready output.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
OUTPUT_AGGREGATE = KNOWLEDGE_DIR / "cleaned_knowledge.json"
OUTPUT_EMBED_AGGREGATE = KNOWLEDGE_DIR / "embedded_knowledge.json"

QUESTION_HEADING = re.compile(
    r"^(什么|如何|怎么|为什么|介绍|说明|区别|列举|说一说|你知道|能说|请问|解释|简述|描述|比较|有哪些)",
    re.I,
)
SECTION_HEADERS = {
    "summary": re.compile(r"(?m)^\s*(简要回答|简答|概述|回答)\s*[:：]?\s*$"),
    "detail": re.compile(r"(?m)^\s*(详细回答|详细说明|深入回答|解析)\s*[:：]?\s*$"),
    "extra": re.compile(
        r"(?m)^\s*(知识拓展|拓展|补充|延伸|面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问|问答)\s*[:：]?\s*$"
    ),
    "stop": re.compile(r"(?m)^\s*(评论|相关问题|参考链接)\s*[:：]?\s*$"),
}


def normalize_heading_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[:：]\s*$", "", text)
    text = re.sub(r"\d+$", "", text)
    return text.strip()


def get_section_label_from_heading(text: str) -> Optional[str]:
    label = normalize_heading_text(text.lstrip("#").strip())
    if label in {"简要回答", "概述", "简答", "回答"}:
        return "summary"
    if label in {"详细回答", "详细说明", "深入回答", "解析"}:
        return "detail"
    if label in {
        "知识拓展",
        "拓展",
        "补充",
        "延伸",
        "追问",
        "问答",
    } or label.startswith("面试官可能的追问") or label.startswith("面试官很能追问"):
        return "extra"
    if label in {"评论", "相关问题", "参考链接"}:
        return "stop"
    return None


def clean_extra_text(text: str) -> str:
    if not text:
        return ""
    text = normalize_text(text)
    text = re.sub(r"(?m)^.*(?:示意图如下|如下图所示).*$", "", text)
    text = re.sub(r"(?m)^[:：]\s*$", "", text)
    return normalize_text(text)


def remove_leading_answer_label(text: str) -> str:
    return re.sub(r"(?m)^(简答|回答|答案|答)\s*[:：]?\s*", "", text).strip()


def extract_question_from_line(line: str) -> Optional[str]:
    line = line.strip().strip('“”"')
    if not line:
        return None
    m = re.match(r"^(.+?[？?])\s*$", line)
    return m.group(1).strip() if m else None


def dedupe_extra_answer(answer: str, question: str) -> str:
    if not answer or not question:
        return answer
    first_token = re.split(r"[，、,？?！!。]", question)[0].strip()
    if first_token and answer.startswith(first_token + first_token):
        return answer[len(first_token) :].strip()
    return answer


def extract_extra_question_text(block: str, original_question: str) -> tuple[str, str]:
    block = block.strip()
    if not block:
        return original_question, ""

    lines = block.splitlines()
    first_line = lines[0].strip()
    follow_up_head_re = re.compile(
        r"^(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问)\s*[:：]?\s*$"
    )
    if follow_up_head_re.match(first_line):
        remaining = "\n".join(lines[1:]).strip()
        if not remaining:
            return original_question, ""
        question_line = remaining.splitlines()[0].strip()
        question = extract_question_from_line(question_line) or original_question
        answer = "\n".join(remaining.splitlines()[1:]).strip()
        answer = remove_leading_answer_label(answer)
        return question, dedupe_extra_answer(answer, question)

    match = re.match(
        r"^(拓展|知识拓展|补充|延伸)\s*[:：]?\s*(.+?[？?])\s*(.*)$",
        block,
        re.S,
    )
    if match:
        question = match.group(2).strip()
        answer = remove_leading_answer_label(match.group(3).strip())
        return question, dedupe_extra_answer(answer, question)

    question = extract_question_from_line(first_line)
    if question and len(block) > len(first_line):
        answer = "\n".join(lines[1:]).strip()
        answer = remove_leading_answer_label(answer)
        return question, dedupe_extra_answer(answer, question)

    result = remove_leading_answer_label(block)
    return original_question, dedupe_extra_answer(result, original_question)


def split_extra_blocks(text: str) -> List[str]:
    text = clean_extra_text(text)
    if not text:
        return []
    boundary_re = re.compile(r"(?m)^(面试官可能的追问\d*|面试官很能追问\d*|追问\d*|追问)\s*[:：]?\s*$")
    matches = list(boundary_re.finditer(text))
    if not matches:
        return [text]

    blocks: List[str] = []
    start = 0
    for idx, match in enumerate(matches):
        if match.start() > start:
            prefix = text[start:match.start()].strip()
            if prefix:
                blocks.append(prefix)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[match.start():end].strip()
        if block:
            blocks.append(block)
        start = end
    return blocks


CATEGORY_DIFFICULTY = {
    "base": "数据库",
    "cpp": "C++",
    "java": "Java",
    "go": "Go",
    "llm": "大模型",
}

DIFFICULTY_BY_TYPE = {
    "qa_short": "简单",
    "qa_detail": "中等",
    "qa_extra": "困难",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    text = re.sub(r"(?m)^\s*#\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_embedding_text(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    text = re.sub(r"^([^\n]+?)\n定义\n[:：]?\n?", r"\1的定义是 ", text, count=1)
    text = re.sub(r"^([^\n]+?)\n特点\n[:：]?\n?", r"\1的特点是 ", text, count=1)
    text = re.sub(r"^([^\n]+?)\n概念\n[:：]?\n?", r"\1的概念是 ", text, count=1)
    text = re.sub(r"^([^\n]+?)\n工作原理\n[:：]?\n?", r"\1的工作原理是 ", text, count=1)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([，。！？；：、,.!?;:])", r"\1", text)
    text = re.sub(r"([（(])\s+", r"\1", text)
    text = re.sub(r"\s+([)）])", r"\1", text)
    text = re.sub(r"\s+([^\x00-\x7F])", r"\1", text)
    return text.strip()


def normalize_title(title: str) -> str:
    if not title:
        return ""
    title = title.replace("#", " ")
    title = normalize_text(title)
    return title


def split_sections(text: str, headings: Optional[List[str]] = None) -> Dict[str, str]:
    text = normalize_text(text)
    if not text:
        return {"summary": "", "detail": "", "extra": ""}

    sections: Dict[str, str] = {"summary": "", "detail": "", "extra": ""}
    boundaries: List[tuple[int, str, int]] = []

    if headings:
        for heading in headings:
            section_label = get_section_label_from_heading(heading)
            if not section_label:
                continue
            heading_text = normalize_heading_text(heading.lstrip("#").strip())
            pattern = re.compile(rf"(?m)^\s*{re.escape(heading_text)}\s*[:：]?\s*$")
            match = pattern.search(text)
            if match:
                boundaries.append((match.start(), section_label, match.end()))

    if not boundaries:
        for label, pattern in SECTION_HEADERS.items():
            for match in pattern.finditer(text):
                boundaries.append((match.start(), label, match.end()))

    boundaries.sort()

    if not boundaries:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if paragraphs:
            sections["summary"] = paragraphs[0]
            sections["detail"] = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
        return sections

    for idx, (pos, label, endpos) in enumerate(boundaries):
        start = endpos
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(text)
        segment = text[start:end].strip()
        if label == "stop":
            break
        sections[label] = segment

    if not sections["summary"] and sections["detail"]:
        paragraphs = [p.strip() for p in sections["detail"].split("\n\n") if p.strip()]
        if paragraphs:
            sections["summary"] = paragraphs[0]
            sections["detail"] = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""

    return sections


def pick_question(title: str, content: str) -> str:
    title = normalize_title(title)
    if title and QUESTION_HEADING.search(title):
        return title

    content = normalize_text(content)
    first_line = ""
    if content:
        first_line = content.split("\n", 1)[0].strip()
        if QUESTION_HEADING.search(first_line):
            return first_line

    return title or first_line or ""


def guess_difficulty(entry_type: str) -> str:
    return DIFFICULTY_BY_TYPE.get(entry_type, "中等")


def build_question_item(page: Dict) -> Optional[Dict]:
    title = page.get("title", "")
    content = page.get("content", "")
    question = pick_question(title, content)
    if not question:
        return None

    sections = split_sections(content, page.get("headings", []))
    summary = sections["summary"].strip()
    detail = sections["detail"].strip()
    extra = clean_extra_text(sections["extra"].strip())

    if not summary and detail:
        summary = detail.split("\n\n", 1)[0].strip()
    if not summary and not detail:
        summary = normalize_text(content).strip()

    if not summary:
        return None

    return {
        "question": question,
        "summary": summary,
        "detail": detail,
        "extra": extra,
        "source": page.get("url", ""),
    }


def build_embedding_items(category_name: str, slug: str, questions: List[Dict]) -> List[Dict]:
    entries: List[Dict] = []
    for index, item in enumerate(questions, start=1):
        qid = f"{slug}_{index:03d}"
        category = category_name or CATEGORY_DIFFICULTY.get(slug, slug)
        question = normalize_embedding_text(item["question"])
        summary = normalize_embedding_text(item.get("summary", ""))
        detail = normalize_embedding_text(item.get("detail", ""))
        raw_extra = item.get("extra", "")

        if summary:
            entries.append(
                {
                    "id": f"{qid}_short",
                    "text": f"问题：{question} 回答：{summary}",
                    "metadata": {
                        "category": category,
                        "difficulty": guess_difficulty("qa_short"),
                        "type": "qa_short",
                    },
                }
            )
        if detail:
            entries.append(
                {
                    "id": f"{qid}_detail",
                    "text": f"问题：{question} 回答：{detail}",
                    "metadata": {
                        "category": category,
                        "difficulty": guess_difficulty("qa_detail"),
                        "type": "qa_detail",
                    },
                }
            )
        if raw_extra:
            extra_blocks = split_extra_blocks(raw_extra)
            if extra_blocks:
                for extra_index, block in enumerate(extra_blocks, start=1):
                    extra_question, extra_answer = extract_extra_question_text(block, question)
                    extra_question = normalize_embedding_text(extra_question)
                    extra_answer = normalize_embedding_text(extra_answer)
                    extra_id = f"{qid}_extra" if len(extra_blocks) == 1 else f"{qid}_extra{extra_index}"
                    if extra_answer:
                        entries.append(
                            {
                                "id": extra_id,
                                "text": f"问题：{extra_question} 回答：{extra_answer}",
                                "metadata": {
                                    "category": category,
                                    "difficulty": guess_difficulty("qa_extra"),
                                    "type": "qa_extra",
                                },
                            }
                        )
                    else:
                        entries.append(
                            {
                                "id": extra_id,
                                "text": f"问题：{extra_question} 回答：{block}",
                                "metadata": {
                                    "category": category,
                                    "difficulty": guess_difficulty("qa_extra"),
                                    "type": "qa_extra",
                                },
                            }
                        )
    return entries


def process_file(path: Path) -> Dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    slug = data.get("slug", path.stem)
    name = data.get("name", "")
    url = data.get("url", "")
    pages = data.get("pages", [])

    questions: List[Dict] = []
    for page in pages:
        item = build_question_item(page)
        if item:
            questions.append(item)

    return {
        "slug": slug,
        "name": name,
        "url": url,
        "question_count": len(questions),
        "questions": questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean knowledge folder files into structured and embedding JSON.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=KNOWLEDGE_DIR,
        help="Input folder containing raw knowledge JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=KNOWLEDGE_DIR,
        help="Output folder for structured and embedding JSON files.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate embedding-ready JSON files.",
    )
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Produce aggregate JSON files for all categories.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    aggregate: List[Dict] = []
    aggregate_embed: List[Dict] = []

    for path in sorted(args.input_dir.glob("bagu_*.json")):
        structured = process_file(path)
        out_path = args.output_dir / f"structured_{path.name}"
        out_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out_path)
        aggregate.append(structured)

        if args.embed:
            embed_items = build_embedding_items(structured["name"], structured["slug"], structured["questions"])
            out_embed = args.output_dir / f"embedding_{path.name}"
            out_embed.write_text(json.dumps(embed_items, ensure_ascii=False, indent=2), encoding="utf-8")
            print("wrote", out_embed)
            aggregate_embed.extend(embed_items)

    if args.aggregate:
        OUTPUT_AGGREGATE.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUTPUT_AGGREGATE)
    if args.embed and aggregate_embed:
        OUTPUT_EMBED_AGGREGATE.write_text(json.dumps(aggregate_embed, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUTPUT_EMBED_AGGREGATE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
