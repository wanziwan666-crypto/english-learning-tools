#!/usr/bin/env python3
"""Extract the dictionaries embedded in reader/collection HTMLs under
essays/ (the same data the 划词 tooltip reads), so 「入库」 can pull words
straight from disk — the browser's localStorage wordbank stays unreadable.

Output: one JSON object per line-ish merged map
  {"<essayId>": {"title": "...", "source": "...", "dictionary": {term: 释义}},
   ...}
Prints to stdout; --out writes it to a file instead. Reader pages contribute
their single dictionary; collection pages contribute every essay inside.
"""
import json, re, sys, argparse, glob
from pathlib import Path

ESSAYS_DIR = Path.home() / "Desktop" / "English Learning" / "essays"


def extract_data(html_text):
    """Pull the COLLECTION_DATA / READER_DATA JSON out of a built page.

    Greedy match anchored on the statement that follows the assignment, so a
    `};` inside a string can't truncate the JSON; non-greedy pass as a second
    chance. json.loads is the final validator.
    """
    for pattern in (
        r'const (?:COLLECTION|READER)_DATA\s*=\s*(\{.*\});\s*\n\s*(?:function|const|var|let)',
        r'const (?:COLLECTION|READER)_DATA\s*=\s*(\{.*?\});',
    ):
        m = re.search(pattern, html_text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).replace('<\\/', '</'))
            except json.JSONDecodeError:
                continue
    return None


def main():
    ap = argparse.ArgumentParser(
        description="抽取 essays/ 下阅读页/合集页内嵌的词典，供「入库」直接使用")
    ap.add_argument("files", nargs="*",
                    help="HTML 文件（默认自动扫 essays/*-reader.html）")
    ap.add_argument("--out", help="写入文件（默认打印到 stdout）")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(str(ESSAYS_DIR / "*-reader.html")))
    if not files:
        sys.exit(f"❌ 没找到阅读页（{ESSAYS_DIR}/*-reader.html），先用 build_reader/build_collection 生成")

    merged = {}
    for fpath in files:
        data = extract_data(Path(fpath).read_text("utf-8"))
        if not data:
            print(f"  ⚠ {Path(fpath).name}: 解析不出数据，跳过", file=sys.stderr)
            continue
        essays = data.get("essays") or [data]  # collection → every essay; reader → itself
        for e in essays:
            if e.get("id") and e.get("dictionary"):
                merged[e["id"]] = {
                    "title": e.get("title", ""),
                    "source": e.get("source", "") or data.get("source", ""),
                    "dictionary": e["dictionary"],
                }
        print(f"  ✓ {Path(fpath).name}: {len(essays)} 篇", file=sys.stderr)

    if not merged:
        sys.exit("❌ 没抽到任何词典（页面里 dictionary 为空？）")

    total = sum(len(v["dictionary"]) for v in merged.values())
    out = json.dumps(merged, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out, "utf-8")
        print(f"✅ {len(merged)} 篇 / {total} 词 → {args.out}", file=sys.stderr)
    else:
        print(out)
        print(f"\n# {len(merged)} 篇 / {total} 词", file=sys.stderr)


if __name__ == "__main__":
    main()
