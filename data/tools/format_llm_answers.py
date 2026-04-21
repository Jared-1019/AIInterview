import argparse
import json
import re
from pathlib import Path


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = text.replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def format_answer(answer: str) -> str:
    answer = normalize_text(answer)
    answer = re.sub(r"^回答[:：]\s*", "", answer)
    answer = re.sub(r"\bA\d+[:：]?\s*", "", answer)
    answer = re.sub(r"\bQ\d+[:：]?\s*", "", answer)
    answer = re.sub(r"(。|！|？)(\s*)(?=[^\n])", r"\1\n", answer)
    answer = re.sub(r"(；)(\s*)(?=[^\n])", r"\1\n", answer)
    answer = re.sub(r"(\n\s*)+", "\n", answer)
    answer = re.sub(r"\s+([，。：；！？])", r"\1", answer)
    answer = answer.strip()
    return answer


def process_file(path: Path, backup_dir: Path) -> int:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    changed = 0
    for item in data:
        text = str(item.get("text", ""))
        if "回答：" not in text:
            continue
        parts = text.split("回答：", 1)
        if len(parts) != 2:
            continue
        question = normalize_text(parts[0])
        answer = parts[1]
        formatted_answer = format_answer(answer)
        new_text = f"{question}回答：{formatted_answer}"
        if new_text != text:
            item["text"] = new_text
            changed += 1

    backup_path = backup_dir / path.name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Format answers in the llm knowledge JSON file.")
    parser.add_argument("--path", type=Path, default=Path("data/knowledge/embedding_bagu_llm.json"))
    parser.add_argument("--backup-dir", type=Path, default=Path("data/knowledge/backup/formatted"))
    args = parser.parse_args()

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    changed = process_file(args.path, args.backup_dir)
    print(f"Formatted {changed} answers in {args.path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
