#!/usr/bin/env python3
"""下载一期 The Economist EPUB 到本地数据目录。

源：github.com/hehonghui/awesome-english-ebooks（每日自动更新的 calibre 抓取仓，
仓库 ~15GB，**绝不整仓 clone**，只按单文件 raw URL 拉取）。
近期期刊在 01_economist/te_YYYY.MM.DD/，往期归档在 01_economist/YYYY/te_YYYY.MM.DD/。
代理：urllib 自动识别 HTTPS_PROXY 环境变量，无需额外代码。
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import quote

REPO = "hehonghui/awesome-english-ebooks"
BRANCH = "master"
API_LIST = f"https://api.github.com/repos/{REPO}/contents/01_economist"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/01_economist"
UA = "english-economist-skill/1.0"  # GitHub API 拒绝裸 urllib UA
DEFAULT_BASE = Path.home() / "Desktop" / "English Learning" / "economist"
MIN_BYTES = 1024 * 1024  # 正常一期 epub 约 5-8MB；<1MB 视为异常

PROXY_HINT = ("   若本机有代理，先 export HTTPS_PROXY=http://127.0.0.1:<端口> 再重跑"
              "（同 english-shadowing 的网络约定）。")


class NotFound(Exception):
    """HTTP 404——不重试，交给调用方换路径或提示改选期号。"""


def ssl_context() -> ssl.SSLContext:
    """python.org 版 Python 默认不认系统证书（certificate verify failed）。
    分层解析 CA：certifi（若装了）→ macOS /etc/ssl/cert.pem → 默认。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for ca in ("/etc/ssl/cert.pem",):
        if os.path.exists(ca):
            try:
                return ssl.create_default_context(cafile=ca)
            except Exception:
                pass
    return ssl.create_default_context()


_CTX = ssl_context()


def curl_download(url: str, dest_tmp: Path) -> None:
    """urllib 彻底不行时的兜底：curl 走 macOS 系统钥匙串，天然支持 HTTPS_PROXY。"""
    r = subprocess.run(["curl", "-fsSL", "--retry", "2", "--max-time", "300",
                        "-o", str(dest_tmp), url], capture_output=True, text=True)
    if r.returncode != 0:
        dest_tmp.unlink(missing_ok=True)
        if r.returncode == 22 and "404" in (r.stderr or ""):
            raise NotFound(url)
        sys.exit(f"❌ curl 兜底下载也失败: {r.stderr.strip()[:300]}\n{PROXY_HINT}")


def http_get(url: str, timeout: int = 30, retries: int = 3) -> bytes:
    last = None
    for i in range(retries):
        if i:
            time.sleep(2 if i == 1 else 5)
        req = urlreq.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
        try:
            with urlreq.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read()
        except ssl.SSLError as e:
            last = e  # 证书问题重试无意义，但统一走末尾报错（API 小响应，curl 兜底不值得）
        except HTTPError as e:
            if e.code == 404:
                raise NotFound(url)
            if e.code == 403:
                body = e.read()[:200].decode("utf-8", "ignore")
                sys.exit(f"❌ GitHub API 403（疑似限流，未认证 60 次/时，等几分钟再试）：{body}")
            last = e
        except URLError as e:
            last = e
    sys.exit(f"❌ 网络请求失败（重试 {retries} 次仍不通）：{last}\n{PROXY_HINT}")


def list_issues() -> list:
    """上游近期期刊目录名，降序（新→旧）。~440 个目录，单次 API 即可取全。"""
    data = json.loads(http_get(API_LIST))
    names = [x["name"] for x in data
             if x.get("type") == "dir" and re.fullmatch(r"te_\d{4}\.\d{2}\.\d{2}", x["name"])]
    return sorted(names, reverse=True)


def normalize_issue(arg: str):
    """te_2026.10.03 / 2026.10.03 / 2026-10-03 → ('2026-10-03', 'te_2026.10.03', 'TheEconomist.2026.10.03.epub')"""
    s = arg.strip()
    if s.startswith("te_"):
        s = s[3:]
    m = re.fullmatch(r"(\d{4})[.\-/](\d{2})[.\-/](\d{2})", s)
    if not m:
        sys.exit(f"❌ 期号格式看不懂: {arg}（支持 2026-10-03 / 2026.10.03 / te_2026.10.03）")
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}", f"te_{y}.{mo}.{d}", f"TheEconomist.{y}.{mo}.{d}.epub"


def raw_url(*segments: str) -> str:
    return RAW_BASE + "/" + "/".join(quote(seg) for seg in segments)


def download(url: str, dest: Path) -> None:
    """流式下载到临时文件，校验后原子替换（杀进程不留残废 epub）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / ("." + dest.name + ".tmp")
    req = urlreq.Request(url, headers={"User-Agent": UA})
    try:
        with urlreq.urlopen(req, timeout=60, context=_CTX) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    except HTTPError as e:
        tmp.unlink(missing_ok=True)
        if e.code == 404:
            raise NotFound(url)
        sys.exit(f"❌ 下载失败 HTTP {e.code}: {url}\n{PROXY_HINT}")
    except (URLError, ssl.SSLError) as e:
        # urllib 网络层失败 → curl 兜底（系统钥匙串 + 代理友好）
        tmp.unlink(missing_ok=True)
        print(f"↓ urllib 下载失败（{e}），改用 curl 兜底…")
        curl_download(url, tmp)

    size = tmp.stat().st_size
    if size < MIN_BYTES:
        tmp.unlink(missing_ok=True)
        sys.exit(f"❌ 下载结果只有 {size} 字节（<1MB），疑似不完整或返回了错误页，已丢弃。")
    try:
        with zipfile.ZipFile(tmp) as zf:
            if not any(n.startswith("EPUB/") for n in zf.namelist()):
                raise ValueError("zip 内没有 EPUB/ 成员")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        sys.exit(f"❌ 下载的文件不是有效的经济学人 EPUB（{e}），疑似上游结构变化。")
    os.replace(tmp, dest)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="下载 The Economist 当期 EPUB（源 awesome-english-ebooks，勿整仓 clone）")
    ap.add_argument("--issue", help="期号，如 2026-10-03 / te_2026.10.03；缺省=最新一期")
    ap.add_argument("--force", action="store_true", help="本地已存在也重新下载")
    ap.add_argument("--out-dir", default=str(DEFAULT_BASE), help="数据根目录（默认 %(default)s）")
    args = ap.parse_args()
    base = Path(args.out_dir).expanduser()

    if args.issue:
        dash, dirn, epubn = normalize_issue(args.issue)
    else:
        issues = list_issues()
        if not issues:
            sys.exit("❌ 上游 01_economist 下没有 te_YYYY.MM.DD 形式的期刊目录，仓库结构可能变了。")
        dash, dirn, epubn = normalize_issue(issues[0])

    dest = base / dash / epubn
    if dest.exists() and not args.force:
        print(f"✅ 已存在，跳过下载: {dest}")
        return

    print(f"↓ {dash} 期下载中（约 6MB）…")
    try:
        download(raw_url(dirn, epubn), dest)
    except NotFound:
        # 往期在年份归档层 01_economist/<YYYY>/te_.../（2025 年及更早的期都在那里）
        try:
            download(raw_url(dash[:4], dirn, epubn), dest)
        except NotFound:
            recent = ""
            try:
                recent = "\n上游最近的期: " + ", ".join(list_issues()[:5])
            except Exception:
                pass
            sys.exit(f"❌ 找不到 {dirn}/{epubn}（根目录与年份归档都没有）。{recent}\n"
                     f"   可能该期的 EPUB 还没推送（目录先建、文件后传），稍后再试或换个期号。")

    print(f"✅ 已下载: {dest}（{dest.stat().st_size / 1048576:.1f}MB）")


if __name__ == "__main__":
    main()
