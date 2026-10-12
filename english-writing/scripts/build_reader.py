#!/usr/bin/env python3
"""Build the IELTS model-essay reader HTML from a JSON data blob."""
import json, sys, argparse, subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "reader.html"
OUT_DIR = Path.home() / "Desktop" / "English Learning" / "essays"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="JSON string of reader data")
    ap.add_argument("--data-file", help="path to JSON file of reader data")
    ap.add_argument("--out", help="output HTML path")
    args = ap.parse_args()

    if args.data_file:
        data = json.loads(Path(args.data_file).read_text("utf-8"))
    else:
        data = json.loads(args.data)

    for k in ("id", "title", "content"):
        if k not in data:
            sys.exit(f"❌ reader data 缺少字段: {k}")
    if "dictionary" not in data:
        data["dictionary"] = {}

    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text("utf-8").replace("{{READER_DATA_JSON}}", data_json)

    out = Path(args.out) if args.out else (OUT_DIR / f"{data['id']}-reader.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    # the reader's 「词汇库」button links to ./my-library.html — keep a fresh
    # copy next to every build (not only when missing) so it never goes stale.
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
    print(f"✅ 阅读页已生成: {out}")


if __name__ == "__main__":
    main()
