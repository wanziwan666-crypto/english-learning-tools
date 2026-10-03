#!/usr/bin/env python3
"""把一期 The Economist EPUB 拆成一篇一个 markdown + articles.json 索引。

EPUB 是 calibre 抓 economist.com 的产物，结构固定（2026-10 实测）：
  EPUB/book_toc.html            顶层栏目 TOC（li.sec_index_li > a.sec_toc_item）
  栏目索引页                     h2.section_index_title + li.sec_index_li > a（a 的 id 在 href 前）
  文章页                         span.te_section_title / te_fly_span、h1.te_article_title、
                                h3.te_article_rubric、span.te_article_datePublished、正文 <p>、
                                尾部 p.link_navbar（zlibrary 署名垃圾段，剥掉但收走 origin 链接）

校验闸门：全部在内存中判断，不过就零输出（不写半截目录）。
解析用 html.parser（正文有嵌套行内标签，正则解析嵌套正是要防的 bug 类型）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_BASE = Path.home() / "Desktop" / "English Learning" / "economist"

MIN_WORDS = 50       # 正文低于此词数 → 跳过并记录（指标页/cartoon 常态就是几十词）
MIN_ARTICLES = 40    # 保留篇数低于此 → 整期 abort（常态 60–90 篇）
MAX_SKIPPED = 15     # 跳过数高于此 → 整期 abort
MAX_SLUG = 50


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def word_count(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’-]+", s))


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "").replace("'", "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = s[:MAX_SLUG].rsplit("-", 1)[0].strip("-") if len(s) > MAX_SLUG else s
    return s or "article"


def table_to_md(rows: list) -> str:
    if not rows:
        return "> [表格省略]"
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]

    def cell(c):
        return norm_ws(c).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(c) for c in rows[0]) + " |",
             "| " + " | ".join("---" for _ in rows[0]) + " |"]
    lines += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


class IndexParser(HTMLParser):
    """book_toc / 栏目索引页通用：收集 li.sec_index_li 下 <a href> 的文本，保持 li 顺序。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h2_title = ""
        self.entries = []  # [(href, text)]
        self._in_li = self._in_a = self._in_h2 = False
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        cls = (dict(attrs).get("class") or "").split()
        if tag == "li" and "sec_index_li" in cls:
            self._in_li = True
        elif tag == "h2" and "section_index_title" in cls:
            self._in_h2 = True
        elif tag == "a" and self._in_li:
            self._href = dict(attrs).get("href")
            self._text = []
            self._in_a = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
        elif tag == "li" and self._in_li:
            if self._href:
                self.entries.append((self._href, "".join(self._text).strip()))
            self._in_li = False
            self._href = None
        elif tag == "h2":
            self._in_h2 = False

    def handle_data(self, data):
        if self._in_h2:
            self.h2_title += data
        if self._in_a:
            self._text.append(data)


META_CLASS = {  # class 名 → 字段
    "te_section_title": "section",
    "te_fly_span": "fly",
    "te_article_title": "title",
    "te_article_rubric": "rubric",
    "te_article_datePublished": "date",
}


class ArticleParser(HTMLParser):
    """一篇文章页 → 元信息 + markdown 段落列表。

    行内规则：strong/b→**，em/i→*，a→只留文本，br→空格，
    span.span_ufinish→吞内容（去 ■ 结尾符），img→计数不输出。
    p.link_navbar 不进正文（origin 链接在它的 a.origin_link 里收走）。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.paragraphs = []
        self.image_count = 0
        self.origin = ""
        self._meta_key = None
        self._meta_buf = None
        self._in_p = False
        self._p_nav = False
        self._p_img = False
        self._buf = []
        self._strong = self._em = 0
        self._suppress = 0
        self._in_table = False
        self._rows = []
        self._row = None
        self._cell = None

    # ---- 表格模式（指标页偶发；本_issue 实测没有，保险起见支持） ----
    def _table_start(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def _table_end(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._in_table = False
            self.paragraphs.append(table_to_md(self._rows))

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = (d.get("class") or "").split()
        if tag == "table":
            self._flush_para()
            self._in_table = True
            self._rows, self._row, self._cell = [], None, None
            return
        if self._in_table:
            self._table_start(tag, attrs)
            return
        if tag == "p":
            self._flush_para()
            self._in_p = True
            self._p_nav = "link_navbar" in cls
            self._p_img = False
            self._buf = []
        elif tag == "img":
            self.image_count += 1
            if self._in_p:
                self._p_img = True
        elif tag == "a":
            if "origin_link" in cls:
                self.origin = d.get("href") or ""
        elif tag in ("strong", "b"):
            if self._in_p:
                self._strong += 1
                self._buf.append("**")
        elif tag in ("em", "i"):
            if self._in_p:
                self._em += 1
                self._buf.append("*")
        elif tag == "br":
            if self._in_p:
                self._buf.append(" ")
        elif tag == "span":
            if "span_ufinish" in cls:
                self._suppress += 1
            key = next((k for c, k in META_CLASS.items() if c in cls), None)
            if key and self._meta_key is None:
                self._meta_key = key
                self._meta_buf = []
        elif tag in ("h1", "h2", "h3"):
            key = next((k for c, k in META_CLASS.items() if c in cls), None)
            if key and self._meta_key is None:
                self._meta_key = key
                self._meta_buf = []

    def handle_endtag(self, tag):
        if self._in_table:
            self._table_end(tag)
            return
        if tag == "p":
            self._flush_para()
        elif tag in ("strong", "b"):
            if self._strong:
                self._strong -= 1
                self._buf.append("**")
        elif tag in ("em", "i"):
            if self._em:
                self._em -= 1
                self._buf.append("*")
        elif tag in ("span", "h1", "h2", "h3"):
            if tag == "span" and self._suppress:
                self._suppress -= 1
            if self._meta_key:
                self.meta[self._meta_key] = norm_ws("".join(self._meta_buf))
                self._meta_key, self._meta_buf = None, None

    def handle_data(self, data):
        if self._in_table:
            if self._cell is not None:
                self._cell.append(data)
            return
        if self._meta_key is not None:
            self._meta_buf.append(data)
            return
        if self._in_p and not self._suppress and not self._p_nav:
            self._buf.append(data)

    def _flush_para(self):
        if not self._in_p:
            return
        self._in_p = False
        if self._p_nav:
            self._buf = []
            return
        txt = norm_ws("".join(self._buf))
        if self._p_img and not txt:
            self.paragraphs.append("> [图省略]")
        elif txt:
            self.paragraphs.append(txt)
        self._buf = []
        self._p_img = False
        self._strong = self._em = 0


def read_member(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8", errors="replace")


def member(href: str) -> str:
    h = href.split("?")[0].lstrip("./")
    return h if h.startswith("EPUB/") else "EPUB/" + h


def parse_article(html: str) -> dict:
    p = ArticleParser()
    p.feed(html)
    p.close()
    m = dict(p.meta)
    if m.get("fly"):
        m["fly"] = re.sub(r"^[\s|]+", "", m["fly"]).strip()
    m["paragraphs"] = p.paragraphs
    m["image_count"] = p.image_count
    m["origin"] = p.origin
    return m


def excerpt_of(paragraphs: list) -> str:
    for para in paragraphs:
        if para.startswith(">"):
            continue
        t = para.replace("**", "").replace("*", "")
        return t[:140] + ("…" if len(t) > 140 else "")
    return ""


def md_content(issue: str, a: dict, words: int) -> str:
    fm = ["---", f"issue: {json.dumps(issue, ensure_ascii=False)}"]
    for key in ("section", "fly", "title", "rubric", "date", "origin"):
        if a.get(key):
            fm.append(f"{key}: {json.dumps(a[key], ensure_ascii=False)}")
    fm.append(f"words: {words}")
    fm.append("---")
    body = list(a["paragraphs"])
    if body and body[0] == "> [图省略]":  # 头图标记不进正文
        body = body[1:]
    return "\n".join(fm) + "\n\n" + "\n\n".join(body) + "\n"


def split_epub(epub: Path, issue: str, issue_dir: Path) -> Path:
    zf = zipfile.ZipFile(epub)
    names = set(zf.namelist())
    if "EPUB/book_toc.html" not in names:
        sys.exit("❌ 拆分校验未过：EPUB 里没有 EPUB/book_toc.html（上游 calibre 布局可能变了）")

    toc = IndexParser()
    toc.feed(read_member(zf, "EPUB/book_toc.html"))
    sections = [(text, href) for href, text in toc.entries if "ad_page" not in href]
    if not sections:
        sys.exit("❌ 拆分校验未过：book_toc 解析出 0 个栏目（检查 sec_index_li / sec_toc_item class）")

    seen = set()
    out_sections, skipped, problems = [], [], []
    for sec_name, sec_href in sections:
        target = member(sec_href)
        if target in seen:
            continue
        seen.add(target)
        sec_html = read_member(zf, target)
        idx = IndexParser()
        idx.feed(sec_html)
        if idx.entries:
            items = [(ahref, parse_article(read_member(zf, member(ahref))))
                     for ahref, _ in idx.entries if "ad_page" not in ahref and member(ahref) not in seen
                     and not seen.add(member(ahref))]
        elif "te_article_title" in sec_html:
            items = [(sec_href, parse_article(sec_html))]  # 栏目页本身就是一篇文章（少见）
        else:
            problems.append(f"栏目「{sec_name}」的索引页既无文章链接也无标题（{target}）")
            continue

        arts = []
        for ahref, a in items:
            title = (a.get("title") or "").strip()
            if not title:
                problems.append(f"「{sec_name}」有文章缺 title（{ahref}）")
                continue
            words = word_count(" ".join(a["paragraphs"]))
            if words < MIN_WORDS:
                skipped.append({"href": ahref, "reason": f"正文仅 {words} 词（<{MIN_WORDS}）"})
                continue
            arts.append((a, words))
        if arts:
            out_sections.append({"name": norm_ws(sec_name), "articles": arts})

    if problems:
        sys.exit("❌ 拆分校验未过: " + problems[0] + f"（共 {len(problems)} 处，疑似 calibre 布局变更，检查 class 名）")
    kept = sum(len(s["articles"]) for s in out_sections)
    if kept < MIN_ARTICLES:
        sys.exit(f"❌ 拆分校验未过：整期只拆出 {kept} 篇（<{MIN_ARTICLES}，常态 60–90），疑似布局变更。")
    if len(skipped) > MAX_SKIPPED:
        sys.exit(f"❌ 拆分校验未过：跳过 {len(skipped)} 篇短文（>{MAX_SKIPPED}），疑似把正文拆丢了。")

    # ---- 校闸全过，才开始写盘（暂存目录 → 原子替换） ----
    articles_dir = issue_dir / "articles"
    staging = issue_dir / f"articles.tmp-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    n, total_words, used_slugs = 0, 0, {}
    json_sections = []
    for sec in out_sections:
        rows = []
        for a, words in sec["articles"]:
            n += 1
            total_words += words
            slug = slugify(a["title"])
            if slug in used_slugs:
                used_slugs[slug] += 1
                slug = f"{slug}-{used_slugs[slug]}"
            else:
                used_slugs[slug] = 1
            fname = f"{n:02d}-{slug}.md"
            (staging / fname).write_text(md_content(issue, a, words), encoding="utf-8")
            rows.append({
                "order": n, "file": f"articles/{fname}", "title": a["title"],
                "fly": a.get("fly", ""), "rubric": a.get("rubric", ""),
                "date": a.get("date", ""), "words": words,
                "excerpt": excerpt_of(a["paragraphs"]), "origin": a.get("origin", ""),
            })
        json_sections.append({"name": sec["name"], "articles": rows})

    data = {
        "issue": issue,
        "epub": epub.name,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "counts": {"articles": n, "words": total_words, "skipped": len(skipped)},
        "sections": json_sections,
        "skipped": skipped,
    }
    (staging.parent / "articles.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    shutil.rmtree(articles_dir, ignore_errors=True)
    os.rename(staging, articles_dir)
    return articles_dir


def latest_local_issue(base: Path):
    cands = [d for d in base.iterdir()
             if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
             and any(d.glob("*.epub"))]
    if not cands:
        return None
    return max(cands, key=lambda d: d.name)


def main() -> None:
    ap = argparse.ArgumentParser(description="把一期经济学人 EPUB 拆成按篇 markdown + 索引")
    ap.add_argument("--issue", help="期号（如 2026-10-03）；缺省=本地已下载的最新一期，不联网")
    ap.add_argument("--epub", help="直接指定本地 epub 路径（调试用）")
    ap.add_argument("--base", default=str(DEFAULT_BASE), help="数据根目录（默认 %(default)s）")
    args = ap.parse_args()
    base = Path(args.base).expanduser()

    if args.epub:
        epub = Path(args.epub).expanduser()
        if not epub.is_file():
            sys.exit(f"❌ 找不到 epub: {epub}")
        m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", epub.stem)
        issue = args.issue or (f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "")
        if not issue:
            sys.exit("❌ 从文件名推不出期号，请用 --issue 指定")
        issue_dir = epub.parent
    else:
        issue = args.issue or ""
        if not issue:
            d = latest_local_issue(base)
            if not d:
                sys.exit(f"❌ {base} 下没有已下载的期，先跑 fetch_economist.py")
            issue = d.name
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", issue):
            sys.exit(f"❌ 期号格式应为 YYYY-MM-DD: {issue}")
        issue_dir = base / issue
        epubs = sorted(issue_dir.glob("*.epub"))
        if not epubs:
            sys.exit(f"❌ {issue_dir} 下没有 epub 文件，先跑 fetch_economist.py")
        epub = epubs[0]

    print(f"✂️ 拆分中: {epub.name}", flush=True)
    articles_dir = split_epub(epub, issue, issue_dir)
    data = json.loads((issue_dir / "articles.json").read_text(encoding="utf-8"))
    c = data["counts"]
    print(f"✅ 拆分完成: {articles_dir}（{c['articles']} 篇 · {c['words']} 词 · 跳过 {c['skipped']} 短文）", flush=True)

    # 自动刷新总目录（仿 build_reader 自动刷 my-library 的先例）
    r = subprocess.run([sys.executable, str(SKILL_DIR / "build_catalog.py"), "--base", str(base)],
                       check=False)
    if r.returncode != 0:
        print("⚠️ 目录页自动重建失败，可手动跑 build_catalog.py", file=sys.stderr)


if __name__ == "__main__":
    main()
