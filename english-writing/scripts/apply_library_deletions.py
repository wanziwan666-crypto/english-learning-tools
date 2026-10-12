#!/usr/bin/env python3
"""Apply the deletion list exported from my-library.html 删除模式.

Reads writing-library-deletions.json (--file, else auto-searched in
~/Desktop/English Learning/ and ~/Downloads, newest wins), backs up
library.json → library.json.bak (one generation), removes the marked
groups/terms (a term whose named group no longer matches falls back to a
unique global match), drops groups left empty, refreshes my-library.html,
then deletes the export file. --dry-run previews without touching anything.
"""
import argparse, json, shutil, subprocess, sys, datetime
from pathlib import Path

LIB = Path.home() / "Documents" / "english-writing" / "library.json"
CANDIDATES = [
    Path.home() / "Desktop" / "English Learning" / "writing-library-deletions.json",
    Path.home() / "Downloads" / "writing-library-deletions.json",
]


def norm(s):
    return "".join(ch for ch in (s or "") if ch.isalnum()).lower()


def find_file(explicit):
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"❌ 清单文件不存在: {p}")
        return p
    found = [p for p in CANDIDATES if p.exists()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="删除清单路径（缺省自动搜索 English Learning / Downloads 两处取最新）")
    ap.add_argument("--lib", help=argparse.SUPPRESS)  # 测试用：覆盖库路径
    ap.add_argument("--no-refresh", action="store_true", help="不刷新 my-library.html（测试用）")
    ap.add_argument("--keep-file", action="store_true", help="应用后保留清单文件（测试用）")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不改动任何文件")
    args = ap.parse_args()
    lib_path = Path(args.lib) if args.lib else LIB

    src = find_file(args.file)
    if src is None:
        sys.exit("❌ 找不到删除清单（writing-library-deletions.json）。在素材库浏览页进「删除模式」标记后导出。")
    if not lib_path.exists():
        sys.exit(f"❌ 素材库不存在: {lib_path}")

    data = json.loads(src.read_text("utf-8"))
    lib = json.loads(lib_path.read_text("utf-8"))
    gmark = {norm(g) for g in data.get("groups", [])}
    req_terms = data.get("terms", [])

    removed_groups = [g for g in lib["groups"] if norm(g.get("meaning_zh", "")) in gmark]
    lib["groups"] = [g for g in lib["groups"] if g not in removed_groups]
    removed_terms = 0
    skipped = []

    for t in req_terms:
        tn = norm(t.get("term", ""))
        if not tn:
            continue
        gname = t.get("group", "")
        if gname == "":  # 未分组条目
            before = len(lib.get("ungrouped", []))
            lib["ungrouped"] = [x for x in lib["ungrouped"] if norm(x.get("term", "")) != tn]
            if len(lib["ungrouped"]) < before:
                removed_terms += 1
            else:
                skipped.append(t["term"])
            continue
        gn = norm(gname)
        target = next((g for g in lib["groups"] if norm(g.get("meaning_zh", "")) == gn), None)
        if target is None:  # 组名对不上 → 全库唯一同名词条兜底
            hits = [g for g in lib["groups"] if any(norm(x.get("term", "")) == tn for x in g["items"])]
            if len(hits) == 1:
                target = hits[0]
        if target is None:
            skipped.append(t["term"])
            continue
        before = len(target["items"])
        target["items"] = [x for x in target["items"] if norm(x.get("term", "")) != tn]
        if len(target["items"]) < before:
            removed_terms += 1
        else:
            skipped.append(t["term"])

    emptied = [g for g in lib["groups"] if not g["items"]]
    lib["groups"] = [g for g in lib["groups"] if g["items"]]
    total_g = len(lib["groups"])
    total = sum(len(g["items"]) for g in lib["groups"]) + len(lib.get("ungrouped", []))
    removed_gwords = sum(len(g["items"]) for g in removed_groups)  # words inside removed groups

    verb = "将删除" if args.dry_run else "已删除"
    print(f"{'🔍 预览: ' if args.dry_run else ''}{verb} {len(removed_groups)} 个整组（含 {removed_gwords} 词）、{removed_terms} 个单独词条"
          f"（清空 {len(emptied)} 个空组）；剩 {total_g} 组 / {total} 词。")
    if skipped:
        print(f"⚠️ 跳过 {len(skipped)} 条未命中: {'; '.join(skipped[:10])}{'…' if len(skipped) > 10 else ''}")
    if args.dry_run:
        return

    shutil.copy2(lib_path, lib_path.with_name(lib_path.name + ".bak"))
    lib["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2), "utf-8")
    print(f"✅ 库已更新（备份: {lib_path.name}.bak）")

    if not args.no_refresh:
        subprocess.run([sys.executable, str(Path(__file__).parent / "build_library_view.py")], check=True)
    if not args.keep_file:
        src.unlink()
        print("✅ 删除清单文件已清理")


if __name__ == "__main__":
    main()
