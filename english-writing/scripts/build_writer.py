#!/usr/bin/env python3
"""Build the IELTS writing HTML (topic + user-set countdown timer) from JSON data."""
import json, sys, argparse
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "writer.html"
OUT_DIR = Path.home() / "Desktop" / "English Learning" / "writing"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="JSON string of writer data")
    ap.add_argument("--data-file", help="path to JSON file of writer data")
    ap.add_argument("--out", help="output HTML path")
    args = ap.parse_args()

    if args.data_file:
        data = json.loads(Path(args.data_file).read_text("utf-8"))
    else:
        data = json.loads(args.data)

    data.setdefault("id", "english")
    data.setdefault("topic", "（未提供题目）")
    data.setdefault("task", "task2")
    data.setdefault("minutes", 45)

    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text("utf-8").replace("{{WRITER_DATA_JSON}}", data_json)

    out = Path(args.out) if args.out else (OUT_DIR / f"{data['id']}-writer.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    print(f"✅ 写作页已生成: {out}")


if __name__ == "__main__":
    main()
