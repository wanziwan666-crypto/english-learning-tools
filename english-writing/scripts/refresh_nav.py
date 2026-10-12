#!/usr/bin/env python3
"""跨页面「上一篇 / 下一篇」底部导航。

阅读页（essays/*-reader.html）与批改页（corrections/*-correction.html）都是
独立静态 HTML，互相不知道对方存在。本脚本给一个目录里所有匹配页面注入 /
刷新底部导航条，由各 build 脚本在建页后自动调用，也可以单独跑：

    python3 refresh_nav.py --dir ~/Desktop/English\ Learning/essays --pattern '*-reader.html'
    python3 refresh_nav.py --dir ~/Desktop/English\ Learning/corrections --pattern '*-correction.html'

顺序钉在 <dir>/.nav-order.json（文件名数组 = 创建顺序）：
- 磁盘上有但清单里没有 → 新页面，按 mtime 追加到末尾；
- 清单里有但磁盘上没有 → 移除；
- 已在清单里的文件无论重建多少次顺序都不动。
  （不用文件系统 birth time：页面在原位重建/整目录拷贝都会重置它，
  「第一次创建时间」只有清单说了算；清单是普通 JSON，可手工调整顺序。）

导航条是自包含 HTML 块（样式 + 数据 + 渲染 JS），用 <!--nb:start--><!--nb:end-->
注释对标记，重复执行幂等替换；老页面没有标记就在 </body> 前插入。
页面标题从各自内嵌的 READER/COLLECTION/CORRECTION_DATA JSON 里取。
"""
import argparse
import json
import os
import re
from pathlib import Path

ORDER_FILENAME = ".nav-order.json"
MARK_START = "<!--nb:start-->"
MARK_END = "<!--nb:end-->"
DATA_RE = re.compile(r"const (?:READER|COLLECTION|CORRECTION)_DATA = ")


def _json_literal(obj):
    """嵌入 <script> 的 JSON：转义 </ 防 </script> 提前闭合（与 build 脚本同款）。"""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def extract_title(html, fallback):
    """从页面内嵌数据 JSON 里取标题：reader/collection 取 title，correction 取 topic。"""
    m = DATA_RE.search(html)
    if not m:
        return fallback
    try:
        data, _ = json.JSONDecoder().raw_decode(html[m.end():])
    except ValueError:
        return fallback
    title = (data.get("title") or data.get("topic") or "").strip()
    return title or fallback


def load_order(nav_dir: Path):
    order_file = nav_dir / ORDER_FILENAME
    if order_file.exists():
        try:
            order = json.loads(order_file.read_text("utf-8"))
            if isinstance(order, list):
                return [f for f in order if isinstance(f, str)], order_file
        except ValueError:
            pass
    return [], order_file


def build_block(nav):
    prev, nxt = nav["prev"], nav["next"]
    return f"""{MARK_START}
<style>
#nb-bar{{position:fixed;left:0;right:0;bottom:0;z-index:900;display:flex;gap:10px;align-items:center;padding:8px 14px calc(8px + env(safe-area-inset-bottom));box-sizing:border-box;background:rgba(250,250,251,.94);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-top:1px solid rgba(15,23,42,.08);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
#nb-bar .nb-btn{{display:flex;flex-direction:column;gap:1px;min-width:0;max-width:42%;padding:7px 13px;border-radius:10px;border:1px solid rgba(15,23,42,.1);background:#fff;color:#0f172a;text-decoration:none;box-shadow:0 1px 2px rgba(15,23,42,.06);transition:transform .08s,box-shadow .08s}}
#nb-bar .nb-btn:hover{{transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,23,42,.14)}}
#nb-bar .nb-cap{{font-size:11px;color:#6b7280}}
#nb-bar .nb-title{{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}}
#nb-bar .nb-next{{margin-left:auto;align-items:flex-end;text-align:right}}
#nb-bar .nb-pos{{font-size:12px;color:#9ca3af;flex:none;padding:0 4px}}
@media (prefers-color-scheme: dark){{
  #nb-bar{{background:rgba(21,22,36,.94);border-top-color:rgba(255,255,255,.09)}}
  #nb-bar .nb-btn{{background:#252640;color:#e5e7eb;border-color:rgba(255,255,255,.12);box-shadow:0 1px 2px rgba(0,0,0,.3)}}
  #nb-bar .nb-cap{{color:#9ca3af}}
}}
</style>
<nav id="nb-bar" aria-label="页面导航"></nav>
<script>
(function(){{
  var NAV = {_json_literal(nav)};
  var bar = document.getElementById('nb-bar');
  if (!NAV || NAV.total < 2 || (!NAV.prev && !NAV.next)) {{ bar.remove(); return; }}
  function mk(item, capText, cls) {{
    var a = document.createElement('a');
    a.href = item.file; a.className = 'nb-btn ' + cls; a.title = item.title;
    var cap = document.createElement('span'); cap.className = 'nb-cap'; cap.textContent = capText;
    var t = document.createElement('span'); t.className = 'nb-title'; t.textContent = item.title;
    a.appendChild(cap); a.appendChild(t);
    return a;
  }}
  if (NAV.prev) bar.appendChild(mk(NAV.prev, '← 上一篇', 'nb-prev'));
  else {{ var sp = document.createElement('span'); sp.style.flex = '1'; bar.appendChild(sp); }}
  var pos = document.createElement('span'); pos.className = 'nb-pos';
  pos.textContent = NAV.pos + ' / ' + NAV.total; bar.appendChild(pos);
  if (NAV.next) bar.appendChild(mk(NAV.next, '下一篇 →', 'nb-next'));
  else {{ var sp2 = document.createElement('span'); sp2.style.flex = '1'; bar.appendChild(sp2); }}
  var cs = getComputedStyle(document.body), pad = parseFloat(cs.paddingBottom) || 0;
  document.body.style.paddingBottom = (pad + 62) + 'px';
}})();
</script>
{MARK_END}"""


def inject(page: Path, block: str):
    html = page.read_text("utf-8")
    if MARK_START in html and MARK_END in html:
        i, j = html.index(MARK_START), html.index(MARK_END) + len(MARK_END)
        new = html[:i] + block + html[j:]
    elif "</body>" in html:
        new = html.replace("</body>", block + "\n</body>", 1)
    else:
        print(f"⚠ {page.name}: 找不到 </body>，跳过导航注入")
        return False
    if new != html:
        page.write_text(new, "utf-8")
    return True


def refresh_directory(nav_dir: Path, pattern: str):
    """给目录里所有匹配页面刷新导航；返回 (页面数, 是否改了顺序清单)。"""
    nav_dir = Path(nav_dir).expanduser()
    pages = sorted(p for p in nav_dir.glob(pattern) if p.is_file())
    if not pages:
        return 0, False

    order, order_file = load_order(nav_dir)
    known = set(order)
    fresh = [p for p in pages if p.name not in known]
    if fresh:  # 新页面按 mtime 排到末尾
        order += [p.name for p in sorted(fresh, key=lambda p: p.stat().st_mtime)]
    on_disk = {p.name for p in pages}
    order = [f for f in order if f in on_disk]  # 清掉已删除的
    prev_text = order_file.read_text("utf-8") if order_file.exists() else None
    new_text = json.dumps(order, ensure_ascii=False, indent=2) + "\n"
    if prev_text != new_text:
        order_file.write_text(new_text, "utf-8")

    titles = {}
    for p in pages:
        titles[p.name] = extract_title(p.read_text("utf-8"), p.stem)

    n = len(order)
    for idx, name in enumerate(order):
        nav = {
            "pos": idx + 1,
            "total": n,
            "prev": ({"file": order[idx - 1], "title": titles[order[idx - 1]]}
                     if idx > 0 else None),
            "next": ({"file": order[idx + 1], "title": titles[order[idx + 1]]}
                     if idx < n - 1 else None),
        }
        inject(nav_dir / name, build_block(nav))
    return n, prev_text != new_text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, help="页面所在目录")
    ap.add_argument("--pattern", required=True, help="页面文件名 glob，如 '*-reader.html'")
    args = ap.parse_args()
    n, _ = refresh_directory(args.dir, args.pattern)
    print(f"✅ 导航已刷新: {args.dir}（{n} 个页面）")


if __name__ == "__main__":
    main()
