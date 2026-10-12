#!/usr/bin/env python3
"""Build the IELTS correction HTML from JSON data, and place a writer.html
alongside it so the 「重写」 button can open a fresh writing page.
Also appends the full record (scores + annotations) to corrections-log.jsonl,
which build_correction_review.py reads as its primary data source."""
import json, sys, argparse, shutil, datetime, subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "correction.html"
WRITER_TEMPLATE = SKILL_DIR / "templates" / "writer.html"
OUT_DIR = Path.home() / "Desktop" / "English Learning" / "corrections"
LOG_FILE = Path.home() / "Documents" / "english-writing" / "corrections-log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="JSON string of correction data")
    ap.add_argument("--data-file", help="path to JSON file of correction data")
    ap.add_argument("--out", help="output HTML path")
    ap.add_argument("--no-log", action="store_true",
                    help="re-render only: skip appending to corrections-log.jsonl "
                         "(use when regenerating an existing correction after a template tweak)")
    args = ap.parse_args()

    if args.data_file:
        data = json.loads(Path(args.data_file).read_text("utf-8"))
    else:
        data = json.loads(args.data)

    for k in ("id", "essay"):
        if k not in data:
            sys.exit(f"❌ correction data 缺少字段: {k}")

    data.setdefault("topic", "")
    data.setdefault("task", "task2")
    data.setdefault("band", {})
    data.setdefault("summary", "")
    data.setdefault("annotations", [])

    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text("utf-8").replace("{{CORRECTION_DATA_JSON}}", data_json)

    out = Path(args.out) if args.out else (OUT_DIR / f"{data['id']}-correction.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, "utf-8")
    # copy writer template next to correction so 重写 works via relative link.
    # replace the build placeholder with {} so the standalone file is valid JS
    # (it reads topic/task from the URL hash instead).
    writer_html = WRITER_TEMPLATE.read_text("utf-8").replace("{{WRITER_DATA_JSON}}", "{}")
    (out.parent / "writer.html").write_text(writer_html, "utf-8")

    # --- append to corrections-log.jsonl for progress tracking ---
    # Full record incl. annotations: the log is the durable data source,
    # the HTML is just a rendering of it (review reads the log, not the HTML).
    annos = data.get("annotations", [])
    record = {
        "slug": data["id"],
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "topic": data.get("topic", ""),
        "task": data.get("task", ""),
        "band": data.get("band", {}),
        "errorCount": sum(1 for a in annos if a.get("severity") == "error"),
        "improveCount": sum(1 for a in annos if a.get("severity") == "improve"),
        "annotations": [
            {k: a.get(k, "") for k in ("text", "comment", "band", "severity", "suggestion")}
            for a in annos
        ],
    }
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_log:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 底部导航：刷新同目录全部批改页的 上一篇/下一篇（含本页与既有老页面）
    subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "refresh_nav.py"),
         "--dir", str(out.parent), "--pattern", "*-correction.html"],
        check=False,
    )
    print(f"✅ 批改页已生成: {out}")
    print(f"✅ 写作页副本已放置: {out.parent / 'writer.html'}")
    print(f"✅ 追加记录到 {LOG_FILE}" if not args.no_log else "⏭ 已按 --no-log 跳过 log 追加")


if __name__ == "__main__":
    main()
