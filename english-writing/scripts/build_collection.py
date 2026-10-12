#!/usr/bin/env python3
"""Build a single-file multi-essay reader: TOC + all essays + per-essay
dictionaries in ONE html (see SKILL.md 批量解析文档).

Data (via --data-file or --data):
{
  "id": "simon-task2",
  "title": "考官Simon雅思大作文范文（28篇）",
  "source": "文件名或来源说明",
  "essays": [
    {"id": "simon-task2-01",              // 必须全合集唯一：单词本按它存 localStorage
     "title": "1. 政府是否该支持本土电影",
     "source": "… · 295 words · band 9",  // 目录卡片上的 meta
     "content": "<blockquote>题目</blockquote><p>…</p>…",
     "dictionary": {"term": "释义", ...}},
    ...
  ]
}
Validation (required fields, unique ids) is built in — no separate
validate_data.py kind needed for collections.
"""
import json, sys, argparse, subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "collection.html"
OUT_DIR = Path.home() / "Desktop" / "English Learning" / "essays"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="JSON string of collection data")
    ap.add_argument("--data-file", help="path to JSON file of collection data")
    ap.add_argument("--out", help="output HTML path (默认 ~/Desktop/English Learning/essays/<id>-reader.html)")
    args = ap.parse_args()

    data = json.loads(Path(args.data_file).read_text("utf-8")) if args.data_file else json.loads(args.data)
    essays = data.get("essays") or []
    if not essays:
        sys.exit("❌ collection data 缺 essays（或为空）")

    seen = set()
    for i, e in enumerate(essays):
        for k in ("id", "title", "content"):
            if not e.get(k):
                sys.exit(f"❌ essays[{i}] 缺 {k}")
        if e["id"] in seen:
            sys.exit(f"❌ essays[{i}] id 重复: {e['id']}（单词本按 id 存 localStorage，必须全合集唯一）")
        seen.add(e["id"])
        e.setdefault("dictionary", {})
        e.setdefault("source", "")

    data.setdefault("id", "collection")
    data.setdefault("title", "范文合集")
    data.setdefault("source", "")

    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text("utf-8").replace("{{COLLECTION_DATA_JSON}}", data_json)

    out = Path(args.out) if args.out else (OUT_DIR / f"{data['id']}-reader.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    # the 「词汇库」button links to ./my-library.html — keep a fresh copy next
    # to every build (not only when missing) so it never goes stale.
    lib_view = out.parent / "my-library.html"
    subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "build_library_view.py"),
         "--out", str(lib_view)],
        check=False,
    )
    # 底部导航：刷新同目录全部阅读页的 上一篇/下一篇（含本页与既有老页面）
    subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "refresh_nav.py"),
         "--dir", str(out.parent), "--pattern", "*-reader.html"],
        check=False,
    )
    print(f"✅ 合集阅读页已生成: {out}（{len(essays)} 篇，{out.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
