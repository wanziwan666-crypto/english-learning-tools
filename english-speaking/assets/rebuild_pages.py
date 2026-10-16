#!/usr/bin/env python3
"""
rebuild_pages.py — 模板迭代后，把已生成口语练习页的题库数据重新注入新模板（不重新搬题）

每页就地重写：从旧页正则抠出 QUESTIONS JSON 与本讲配置（LESSON_ID/TITLE/COURSE_LINE/
PART_LABEL/LESSON_NO/TOTAL_LESSONS），代入 assets/template.html 母本后覆盖原文件。
QUESTIONS 原文直传（含 </ 转义原样保留），不解析重组，零漂移。

用法：
  python3 rebuild_pages.py [目录]     # 默认 ~/Desktop/English Learning/speaking
"""
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_DIR = Path.home() / "Desktop" / "English Learning" / "speaking"


def main():
    d = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_DIR
    template = (SKILL_DIR / "template.html").read_text("utf-8")
    if "__QUESTIONS_JSON__" not in template:
        sys.exit("模板里没有 __QUESTIONS_JSON__ 占位符，检查 assets/template.html")
    n, ids = 0, {}
    for f in sorted(d.glob("[0-9][0-9]-*.html")):   # 只认练习页，index.html 不动
        html = f.read_text("utf-8")
        mq = re.search(r"const QUESTIONS = (.*?);\n\n/\* ===== 状态", html, re.S)
        cfg = {k: re.search(r'const %s = "(.*?)";' % k, html) for k in
               ("LESSON_ID", "LESSON_TITLE", "COURSE_LINE", "PART_LABEL")}
        mno = re.search(r"const LESSON_NO = (\d+);", html)
        mtotal = re.search(r"const TOTAL_LESSONS = (\d+);", html)
        if not (mq and mno and mtotal and all(cfg.values())):
            print(f"跳过（抠不出数据/配置）: {f.name}")
            continue
        payload = mq.group(1)
        try:
            json.loads(payload.replace("<\\/", "</"))   # 顺带校验 JSON 合法
        except ValueError as e:
            print(f"跳过（QUESTIONS JSON 解析失败 {e}）: {f.name}")
            continue
        fresh = (template
                 .replace("__QUESTIONS_JSON__", payload)
                 .replace("__LESSON_ID__", cfg["LESSON_ID"].group(1))
                 .replace("__LESSON_TITLE__", cfg["LESSON_TITLE"].group(1))
                 .replace("__COURSE_LINE__", cfg["COURSE_LINE"].group(1))
                 .replace("__PART_LABEL__", cfg["PART_LABEL"].group(1))
                 .replace("__LESSON_NO__", mno.group(1))
                 .replace("__TOTAL_LESSONS__", mtotal.group(1)))
        f.write_text(fresh, "utf-8")
        lid = cfg["LESSON_ID"].group(1)
        ids.setdefault(lid, []).append(f.name)
        print(f"✓ {f.name}（{lid}）")
        n += 1
    dup = {k: v for k, v in ids.items() if len(v) > 1}
    if dup:
        print(f"⚠ LESSON_ID 重复（作答与录音会互相串，必须改唯一）: {dup}")
    print(f"共刷新 {n} 页")


if __name__ == "__main__":
    main()
