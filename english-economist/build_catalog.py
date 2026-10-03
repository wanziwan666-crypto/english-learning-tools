#!/usr/bin/env python3
"""重建经济学人选篇目录页 catalog.html。

扫描数据目录下所有期的 articles.json（拆分脚本产物），裁剪成轻量 payload
注入 template.html。可独立重跑：手删过文章/期之后刷新目录用。
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
TEMPLATE = SKILL_DIR / "template.html"
DEFAULT_BASE = Path.home() / "Desktop" / "English Learning" / "economist"


def collect(base: Path) -> dict:
    """收集所有期的 articles.json → CATALOG_DATA payload。"""
    issues = []
    total_articles = 0
    for aj in sorted(base.glob("*/articles.json"), key=lambda p: p.parent.name, reverse=True):
        issue_dir = aj.parent
        try:
            data = json.loads(aj.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ 跳过坏掉的 articles.json: {aj}（{e}）", file=sys.stderr)
            continue

        sections, n_articles, n_words = [], 0, 0
        for sec in data.get("sections", []):
            rows = []
            for a in sec.get("articles", []):
                p = (issue_dir / a["file"]).resolve()
                if not p.exists():
                    print(f"⚠️ 文章文件已不存在，目录中剔除: {p}", file=sys.stderr)
                    continue
                rows.append({
                    "order": a["order"], "title": a["title"], "fly": a.get("fly", ""),
                    "rubric": a.get("rubric", ""), "words": a["words"],
                    "excerpt": a.get("excerpt", ""), "path": str(p),
                })
            if rows:
                sections.append({"name": sec.get("name", "?"), "articles": rows})
                n_articles += len(rows)
                n_words += sum(r["words"] for r in rows)
        if not sections:
            print(f"⚠️ 该期已无有效文章，目录中剔除: {issue_dir.name}", file=sys.stderr)
            continue
        issues.append({
            "issue": data.get("issue", issue_dir.name),
            "articles": n_articles, "words": n_words,
            "skipped": data.get("counts", {}).get("skipped", 0),
            "sections": sections,
        })
        total_articles += n_articles

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totalArticles": total_articles,
        "issues": issues,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="重建经济学人选篇目录 catalog.html")
    ap.add_argument("--base", default=str(DEFAULT_BASE), help="数据根目录（默认 %(default)s）")
    ap.add_argument("--out", default=None, help="输出 html 路径（默认 <base>/catalog.html）")
    args = ap.parse_args()

    base = Path(args.base).expanduser()
    if not base.is_dir():
        sys.exit(f"❌ 数据目录不存在: {base}（先跑 fetch_economist.py 下载一期）")
    out = Path(args.out).expanduser() if args.out else base / "catalog.html"

    data = collect(base)
    if not data["issues"]:
        sys.exit(f"❌ {base} 下没有任何有效的 articles.json——先跑 fetch_economist.py + split_economist.py")

    template = TEMPLATE.read_text(encoding="utf-8")
    if "{{CATALOG_DATA_JSON}}" not in template:
        sys.exit("❌ template.html 里找不到 {{CATALOG_DATA_JSON}} 占位符")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = template.replace("{{CATALOG_DATA_JSON}}", payload)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("." + out.name + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, out)
    print(f"✅ 目录已生成: {out}（{len(data['issues'])} 期 · {data['totalArticles']} 篇）")


if __name__ == "__main__":
    main()
