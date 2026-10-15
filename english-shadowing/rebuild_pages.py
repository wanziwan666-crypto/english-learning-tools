#!/usr/bin/env python3
"""
rebuild_pages.py — 模板迭代后，把已生成课页的数据重新注入新模板（不重新下载/转录）

用法：
  python3 rebuild_pages.py [目录]     # 默认 ~/Desktop/English Learning/shadowing
"""
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_DIR = Path.home() / "Desktop" / "English Learning" / "shadowing"


def main():
    d = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_DIR
    template = (SKILL_DIR / "template.html").read_text("utf-8")
    if "{{SHADOW_DATA_JSON}}" not in template:
        sys.exit("模板里没有 {{SHADOW_DATA_JSON}} 占位符，检查 template.html")
    n = 0
    # rglob：拆期组住在 <slug>/ 子文件夹里，也要刷到
    for f in sorted(d.rglob("*-shadowing.html")):
        html = f.read_text("utf-8")
        m = re.search(r"const SHADOW_DATA = (\{.*?\});\n", html, re.S)
        if not m:
            print(f"跳过（未找到数据块）: {f.name}")
            continue
        payload = m.group(1).replace("<\\/", "</")          # 还原转义
        data = json.loads(payload)                            # 顺带校验 JSON 合法
        fresh = template.replace("{{SHADOW_DATA_JSON}}",
                                 payload.replace("</", "<\\/"))
        f.write_text(fresh, "utf-8")
        print(f"✓ {f.name}（{len(data.get('sentences', []))} 句）")
        n += 1
    print(f"共刷新 {n} 页")


if __name__ == "__main__":
    main()
