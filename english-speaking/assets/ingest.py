#!/usr/bin/env python3
"""文档题库 → 纯文本抽取（文档出题第一步，机械活；拆题/对照讲次/出题是 agent 的判断活，见 references/ingest.md）。

用户给 pdf/docx/doc/rtf/html/txt/md 题库文档时跑本脚本，产出干净文本 dump，
默认落 ~/Desktop/English Writing/speaking/sources/<原文件名>.txt（溯源：任何一题都能回指原文）。

- PDF → pymupdf 逐页 get_text(sort=True)（防双栏串行）→ pypdf 兜底，带 ===== PAGE N ===== 标记
- docx → stdlib zipfile+XML 逐段抽取（表格题库每格自成行，首选）→ textutil 兜底
- doc/rtf/html → macOS 原生 textutil
- txt/md → 直读（utf-8/gbk/latin-1 回退）

硬闸门（不过 = 零输出 + exit 1）：类型不支持 / PDF 加密 / 提取全链失败 / 内容过少（疑似扫描版）。
扫描版被拒是特性不是 bug——别绕过闸门编题，把出路转述给用户。
"""
import argparse, re, subprocess, sys
from pathlib import Path

SUPPORTED = {".pdf", ".doc", ".docx", ".rtf", ".html", ".htm", ".txt", ".md", ".markdown"}
SOURCES_DIR = Path.home() / "Desktop/English Writing/speaking/sources"
EXT_HINTS = {
    ".pages": "Pages 文件请先在 Pages 里导出为 docx 或 PDF 再提供",
    ".ppt": "PPT 请先导出为 PDF 再提供", ".pptx": "PPT 请先导出为 PDF 再提供",
    ".key": "Keynote 请先导出为 PDF 再提供",
    ".png": "图片是扫描件的源头，请提供文字版文档（或直接把题目文字粘贴进对话）",
    ".jpg": "图片是扫描件的源头，请提供文字版文档（或直接把题目文字粘贴进对话）",
    ".jpeg": "图片是扫描件的源头，请提供文字版文档（或直接把题目文字粘贴进对话）",
}
SCANNED_HINT = ("三条出路：① 提供文字版 PDF ② 用 Word/Pages 打开另存为 docx "
                "③ 直接把题目文字粘贴进对话")


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def extract_pdf_pages(path: Path):
    """返回每页文本的 list。fitz 首选；异常降 pypdf；全链失败才 fail。"""
    pages = None
    try:
        import fitz
        doc = fitz.open(str(path))
        if doc.needs_pass:
            fail("❌ PDF 有密码，请先解密再提供")
        pages = [p.get_text("text", sort=True) for p in doc]
        doc.close()
    except ImportError:
        pass
    except SystemExit:
        raise
    except Exception:
        pages = None  # 落 pypdf 兜底
    if pages is None:
        try:
            from pypdf import PdfReader
        except ImportError:
            fail("❌ pymupdf 与 pypdf 都不可用（pip3 install pymupdf），或改用 docx/txt 提供题库")
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                fail("❌ PDF 有密码，请先解密再提供")
            pages = [(pg.extract_text() or "") for pg in reader.pages]
        except SystemExit:
            raise
        except Exception as e:
            fail(f"❌ PDF 解析失败: {e}\n   可尝试：换文字版 PDF / 另存为 docx / {SCANNED_HINT.split('：', 1)[1]}")
    return pages


def extract_docx(path: Path) -> str:
    # stdlib 首选（跨平台零依赖）：每个 <w:p> 一段，表格单元格内的段落也各自成行——题库 docx 常用表格
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = ["".join(t.text or "" for t in p.iter(W + "t"))
             for p in root.iter(W + "p")]
    return "\n\n".join(paras)


def extract_textutil(path: Path) -> str:
    try:
        out = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True, text=True, check=True,
        )
        return out.stdout
    except FileNotFoundError:
        fail("❌ 找不到 textutil（macOS 自带；其他系统请转存为 docx/txt）")
    except subprocess.CalledProcessError as e:
        fail(f"❌ textutil 转换失败: {(e.stderr or '').strip()}")


def read_plain(path: Path) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(enc)
        except UnicodeDecodeError:
            continue
    return ""  # latin-1 不会失败，不可达


def clean(text: str) -> str:
    # 机械清理，无猜测：行尾空白、跨行断词、3+ 空行压 2。页眉页脚/题目识别不做——判断活归 agent
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    text = re.sub(r"([A-Za-z])-\n(?=[a-z])", r"\1", text)  # 行尾连字符+下行小写开头=断词
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def assemble(pages) -> str:
    # PAGE 标记不参与断词修复，所以逐页 clean 后再拼标记；空页保留标记（扫描页信号）
    parts = []
    for i, pg in enumerate(pages):
        parts.append(f"===== PAGE {i + 1} =====\n{clean(pg)}")
    return "\n".join(parts) + "\n"


def gates_and_stats(text: str, npages: int, is_pdf: bool):
    body = re.sub(r"===== PAGE \d+ =====", "", text)
    visible = len(re.sub(r"\s", "", body))
    if visible < 100:
        fail(f"❌ 提取到的文字极少（{visible} 可见字符），疑似扫描版/无文字层文档。{SCANNED_HINT}")
    if is_pdf and npages and visible / npages < 30:
        fail(f"❌ 平均每页仅 {visible / npages:.0f} 字符，疑似扫描版（百页只淘出一页字也会被拦）。{SCANNED_HINT}")
    en_words = len(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*", body))
    cjk = len(re.findall(r"[一-鿿]", body))
    qlines = sum(1 for ln in body.splitlines() if ln.rstrip().endswith(("?", "？")))
    yss = len(re.findall(r"you should say", body, re.I))
    unit = "页" if is_pdf else "段"
    print(f"📊 {npages} {unit} · {len(body)} 字符 · 英文 {en_words} 词 · 中文 {cjk} 字 · "
          f"问句行 {qlines} · 'You should say' {yss} 处", file=sys.stderr)
    # 语言不设闸门：纯中文题库照常放行（sample/band7 由 agent 撰写）


def write_out(text: str, out_arg: str):
    if out_arg == "-":
        sys.stdout.write(text)
        print("✅ 已抽取 → stdout（统计见 stderr）", file=sys.stderr)
        return
    out = Path(out_arg).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    # 幂等 + 溯源：同内容跳过；内容变了绝不静默覆盖旧 dump，落 -N 版本
    n = 1
    while True:
        cand = out if n == 1 else Path(f"{out.with_suffix('')}-{n}.txt")
        if not cand.exists():
            break
        if cand.read_bytes() == data:
            print(f"✅ dump 已存在且内容一致，跳过 → {cand}")
            return
        n += 1
    cand.write_bytes(data)
    print(f"✅ 已抽取 → {cand}")


def main():
    ap = argparse.ArgumentParser(description="题库文档 → 纯文本 dump（出题第一步）")
    ap.add_argument("file", help="题库文档路径 (pdf/docx/doc/rtf/html/txt/md)")
    ap.add_argument("--out", help=f"输出路径（默认 {SOURCES_DIR}/<原文件名>.txt；- = stdout）")
    args = ap.parse_args()

    path = Path(args.file).expanduser()
    if not path.is_file():
        fail(f"❌ 文件不存在: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        hint = EXT_HINTS.get(suffix, "")
        fail(f"❌ 不支持的类型 {suffix or '(无扩展名)'}，支持: {', '.join(sorted(SUPPORTED))}"
             + (f"\n   {hint}" if hint else ""))

    if suffix == ".pdf":
        pages = extract_pdf_pages(path)
        text = assemble(pages)
        gates_and_stats(text, len(pages), is_pdf=True)
    else:
        if suffix == ".docx":
            try:
                text = extract_docx(path)
            except SystemExit:
                raise
            except Exception:
                text = extract_textutil(path)  # 奇形 docx 兜底；表格黏连说明走到了这条路
        elif suffix in {".txt", ".md", ".markdown"}:
            text = read_plain(path)
        else:
            text = extract_textutil(path)
        text = clean(text) + "\n"
        paras = [p for p in text.split("\n") if p.strip()]
        gates_and_stats(text, len(paras), is_pdf=False)

    write_out(text, args.out or str(SOURCES_DIR / (path.name + ".txt")))


if __name__ == "__main__":
    main()
