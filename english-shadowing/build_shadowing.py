#!/usr/bin/env python3
"""
build_shadowing.py — 把 媒体文件+字幕 或 视频链接 变成影子跟读训练页（*-shadowing.html）

用法 A（本地文件）：
  python3 build_shadowing.py --media video.mp4 --srt en.srt [--cn-srt zh.srt] \
      [--dict dict.json] [--title X] [--slug id] [--out path.html]

用法 B（视频直链，YouTube/B站等 yt-dlp 支持的站点）：
  python3 build_shadowing.py --url "https://www.youtube.com/watch?v=xxx" \
      [--cn] [--start 1:30 --stop 3:00] [--max-height 720] \
      [--cookies chrome] [--dedupe-roll]

用法 C（无字幕素材：本地 Whisper 转录，解锁 B 站硬字幕视频）：
  python3 build_shadowing.py --url "https://www.bilibili.com/video/BVxxx" --transcribe \
      [--whisper-model small] [--lang en]
  python3 build_shadowing.py --media video.mp4 --transcribe

行为：
  1. URL 模式：yt-dlp 下载视频（≤max-height）+ 字幕（人工字幕优先，缺失时退自动字幕），ffmpeg 裁切
  2. 解析 SRT/VTT（或 Whisper 转录产出），碎片 cue 按句末标点或最长 8s 合并成句；中文字幕按时间重叠贴进句子；
     --dedupe-roll 时先做 YouTube 滚动字幕清洗（行去重→词级时间轴断句，标点在行中也能按句收口）
  3. 媒体复制到输出 HTML 同目录（slug 前缀防撞名）；词典嵌入供离线划词
  4. 注入 template.html 生成最终页面
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = Path.home() / "Desktop" / "English Learning" / "shadowing"
BIN_DIRS = ["/opt/homebrew/bin", "/usr/local/bin"]  # yt-dlp/ffmpeg 兜底查找位置

SENT_END = tuple(".?!…")
MAX_SENT_DUR = 8.0
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac"}
# 子进程（yt-dlp/ffmpeg）的 PATH 兜底带上 brew 目录：yt-dlp 解 n-challenge 要能找到 deno。
# 注意这只影响子进程，不改变「用哪个 python3 跑本脚本」。
SUB_ENV = dict(os.environ, PATH=":".join(BIN_DIRS) + ":" + os.environ.get("PATH", ""))


def which_bin(name):
    p = shutil.which(name)
    if p:
        return p
    for d in BIN_DIRS:
        c = Path(d) / name
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    sys.exit(f"找不到 {name}，请先安装（brew install {name}）")


def sh(*cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, env=SUB_ENV, **kw)
    if r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


# ============================================================
# 字幕解析
# ============================================================
def ts2sec(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return 0.0
    sec = 0.0
    for n in nums:
        sec = sec * 60 + n
    return sec


def fmt_mmss(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def parse_ts_arg(s):
    if not s:
        return None
    parts = s.split(":")
    try:
        v = 0.0
        for p in parts:
            v = v * 60 + float(p)
        return v
    except ValueError:
        sys.exit(f"时间格式看不懂: {s}（支持 90 / 1:30 / 1:02:03）")


def parse_srt(path: Path):
    text = path.read_text("utf-8-sig", errors="replace")
    text = re.sub(r"^WEBVTT.*?\n", "", text, count=1)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    cues = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        m = None
        for i, l in enumerate(lines):
            m = re.match(r"(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", l.strip())
            if m:
                body = lines[i + 1:]
                break
        if not m or not body:
            continue
        start, end = ts2sec(m.group(1)), ts2sec(m.group(2))
        txt = " ".join(body)
        txt = re.sub(r"<[^>]+>", "", txt)  # 去掉 <i> / 位置标签
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            cues.append((start, end, txt))
    cues.sort(key=lambda c: c[0])
    return cues


def shift_cues(cues, offset):
    """按裁切起点平移字幕时间轴，丢掉裁切前的句、夹住跨界的句"""
    out = []
    for s, e, t in cues:
        s2, e2 = s - offset, e - offset
        if e2 <= 0.05:
            continue
        s2 = max(0.0, s2)
        out.append((s2, e2, t))
    return out


# ============================================================
# YouTube 滚动式自动字幕（karaoke）清洗
# ============================================================
ROLL_TS_RE = re.compile(r"(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)")
ABBREV_END = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "U.S.", "No.", "e.g.", "i.e.")


def parse_srt_lines(path: Path):
    """行感知解析：[(start, end, [行...])]。
    滚动字幕正文里混着「单独空格行」，不能像 parse_srt 那样按空行分块（会被空格行切开）。"""
    cues, cur = [], None
    text = path.read_text("utf-8-sig", errors="replace")
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = ROLL_TS_RE.match(line.strip())
        if m:
            if cur and cur[2]:
                cues.append(cur)
            cur = [ts2sec(m.group(1)), ts2sec(m.group(2)), []]
        elif cur is not None:
            s = line.strip()
            if s and not s.isdigit():
                cur[2].append(s)
    if cur and cur[2]:
        cues.append(cur)
    return cues


def dedupe_roll(path: Path):
    """YouTube 滚动式自动字幕 → 干净的行级 cue。
    滚动格式：相邻 cue 重复上一行（新行总在 cue 最后一行）、穿插 ~10ms 擦除 cue。
    清洗 = 跳过擦除 cue + 只取每 cue 最后一行 + 滤掉 [掌声]/>> 类非语音行。"""
    out = []
    for start, end, body in parse_srt_lines(path):
        if end - start < 0.05:  # 擦除 cue
            continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body[-1])).strip()
        if not txt or txt.startswith(">>") or re.match(r"^\[[^\]]+\]$", txt):
            continue
        if out and out[-1][2] == txt:
            out[-1] = (out[-1][0], end, txt)
        else:
            out.append((start, end, txt))
    return out


def split_word_sentences(cues, cap=20.0, comma_after=11.0, min_words=3):
    """行级 cue → 完整句 cue：词均摊到时间轴，按词尾标点收句。
    滚动字幕的行断与句断不对齐（句号常在行中间），通用 merge_to_sentences 靠「行尾标点」
    判句几乎不触发、退化成 8s 硬切（会切在词中间）；这里按词流收句。
    口语长句（逗号连接的流水句）在 comma_after 秒后遇逗号软切（换气单元）。"""
    words = []
    for s, e, txt in cues:
        ws = txt.split()
        if not ws:
            continue
        dur = (e - s) / len(ws) if e > s else 0.4
        for i, w in enumerate(ws):
            words.append((w, s + dur * i, s + dur * (i + 1)))
    out, buf = [], []
    for w, ts, te in words:
        buf.append((w, ts, te))
        clean = w.rstrip("\"'”’")
        dur = te - buf[0][1]
        ends = clean.endswith(SENT_END) and not clean.endswith(ABBREV_END)
        ok_len = len(buf) >= min_words or dur >= 2.0
        comma_soft = clean.endswith(",") and dur >= comma_after
        if (ends and ok_len) or comma_soft or dur >= cap:
            out.append([buf[0][1], buf[-1][2] + 0.15, " ".join(x[0] for x in buf)])
            buf = []
    if buf:
        if out and len(buf) < min_words:  # 尾巴太短并给上句
            out[-1][1] = buf[-1][2] + 0.15
            out[-1][2] += " " + " ".join(x[0] for x in buf)
        else:
            out.append([buf[0][1], buf[-1][2] + 0.15, " ".join(x[0] for x in buf)])
    for i in range(len(out) - 1):  # 句尾不越过下句起点
        out[i][1] = min(out[i][1], out[i + 1][0])
    return [tuple(c) for c in out]


def merge_to_sentences(cues):
    sents, buf = [], []
    for start, end, txt in cues:
        buf.append((start, end, txt))
        joined = " ".join(c[2] for c in buf)
        dur = buf[-1][1] - buf[0][0]
        if txt.endswith(SENT_END) and dur >= 0.6:
            sents.append((buf[0][0], buf[-1][1], joined))
            buf = []
        elif dur >= MAX_SENT_DUR:
            sents.append((buf[0][0], buf[-1][1], joined))
            buf = []
    if buf:
        sents.append((buf[0][0], buf[-1][1], " ".join(c[2] for c in buf)))
    merged = []
    for s in sents:
        if merged and (s[1] - s[0]) < 0.5:
            p = merged[-1]
            merged[-1] = (p[0], s[1], p[2] + " " + s[2])
        else:
            merged.append(list(s))
    # 句间保底 0.4s 空隙：页面 timeupdate 在 [本句end-0.06, 下句start-0.05) 窗口内触发
    # 「循环本句/逐句暂停」；句尾贴着下句起点（词级时间轴估算/whisper 连续语音常见）会把
    # 窗口压到 ~10ms，timeupdate ~250ms 一跳几乎必错过——按钮开了却永远不触发。
    for i in range(len(merged) - 1):
        merged[i][1] = min(merged[i][1], merged[i + 1][0] - 0.4)
    return [tuple(s) for s in merged]


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def merge_cn(sents, cn_cues):
    used, out = set(), []
    for s0, s1, en in sents:
        scored = sorted(
            ((overlap(s0, s1, c0, c1), j, t) for j, (c0, c1, t) in enumerate(cn_cues)),
            key=lambda x: -x[0],
        )
        pick = [(j, t) for ov, j, t in scored if ov > 0.15]
        pick.sort(key=lambda x: x[0])
        cn = " ".join(t for _, t in pick)
        for j, _ in pick:
            used.add(j)
        out.append((s0, s1, en, cn))
    return out


# ============================================================
# URL 下载（yt-dlp）
# ============================================================
SUB_LANGS = "en,en-US,en-GB,en-orig,zh,zh-Hans,zh-CN,zh-TW"


def download_from_url(url, workdir, max_height, want_cn, ytdlp_extra=()):
    ytdlp = which_bin("yt-dlp")
    sublangs = SUB_LANGS if want_cn else "en,en-US,en-GB,en-orig"
    out_tmpl = str(workdir / "media.%(ext)s")
    cmd = [
        ytdlp,
        "--ffmpeg-location", which_bin("ffmpeg"),
        *ytdlp_extra,
        "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "--merge-output-format", "mp4",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", sublangs,
        "--convert-subs", "srt",
        "--no-playlist",
        "--no-progress",
        "--no-overwrites",
        "-o", out_tmpl,
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=SUB_ENV)
    if r.returncode != 0:
        sys.exit(f"yt-dlp 下载失败:\n{r.stderr[-1500:]}")

    files = list(workdir.iterdir())
    media = next((f for f in files if f.suffix.lower() in VIDEO_EXT | AUDIO_EXT), None)
    if not media:
        sys.exit(f"下载完成但没找到媒体文件，目录内容: {[f.name for f in files]}")

    def pick_srt(prefixes, exclude=()):
        cands = []
        for f in files:
            if f.suffix.lower() != ".srt":
                continue
            low = f.name.lower()
            if any(low.endswith(p + ".srt") or f".{p}." in low for p in prefixes):
                if not any(x in low for x in exclude):
                    cands.append(f)
        # 人工字幕优先：auto 字幕常带 -orig / 语言变体后缀
        cands.sort(key=lambda f: (("-orig" in f.name or ".auto" in f.name), len(f.name)))
        return cands[0] if cands else None

    en_srt = pick_srt(["en", "en-us", "en-gb", "en-orig"])
    zh_srt = pick_srt(["zh-hans", "zh-cn", "zh", "zh-tw"], exclude=("orig",)) if want_cn else None

    # 标题
    try:
        info = json.loads(sh(ytdlp, "--skip-download", "--dump-json", "--no-playlist",
                             *ytdlp_extra, url))
        title = info.get("title") or ""
    except SystemExit:
        raise
    except Exception:
        title = ""

    return media, en_srt, zh_srt, title


def crop_media(media: Path, start: float, stop: float, out: Path):
    ffmpeg = which_bin("ffmpeg")
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if stop:
        cmd += ["-to", f"{stop:.3f}"]
    cmd += ["-i", str(media),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", str(out)]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out


def probe_duration(path: Path):
    try:
        ffprobe = which_bin("ffprobe")
        out = sh(ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(path))
        return round(float(out.strip()), 3)
    except Exception:
        return None


def partition_sentences(sents, target):
    """把句子序列按句边界切成约 target 秒的连续片段。
    返回 [(media_start, media_stop, [(start,end,text), …])]，时间轴仍为原始坐标系。"""
    parts, cur = [], []
    for s in sents:
        cur.append(s)
        if cur[-1][1] - cur[0][0] >= target:
            parts.append(cur)
            cur = []
    if cur:
        if parts and (cur[-1][1] - cur[0][0]) < target * 0.4:
            parts[-1].extend(cur)  # 尾巴太短并给上一期
        else:
            parts.append(cur)
    out = []
    for p in parts:
        ms = max(0.0, p[0][0] - 0.25)   # 留一点呼吸感
        me = p[-1][1] + 0.35
        out.append((ms, me, p))
    return out


def transcribe_media(media: Path, model_name: str = "small", lang: str = "en"):
    """faster-whisper 本地转录 → cue 列表 [(start, end, text)]。模型经 hf-mirror 下载。"""
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("需要 faster-whisper：pip3 install faster-whisper")
    print(f"  · Whisper 转录中（模型 {model_name}，CPU int8）…", file=sys.stderr)
    # 先抽 16k 单声道 wav：绕开 PyAV 对各类容器的解码怪癖，也省去 whisper 内部重采样
    audio = Path(tempfile.gettempdir()) / f"shadow16k-{media.stem}.wav"
    sh(which_bin("ffmpeg"), "-y", "-loglevel", "error", "-i", str(media),
       "-ac", "1", "-ar", "16000", str(audio))
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language=lang,
                                      word_timestamps=True, vad_filter=True)
    cues = []
    for s in segments:
        text = s.text.strip()
        if not text:
            continue
        end = s.end
        try:  # 用词级时间戳收窄句尾，避免把句间停顿算进句子
            words = [w for w in (s.words or []) if w.word and w.word.strip()]
            if words:
                end = min(end, words[-1].end + 0.15)
        except Exception:
            pass
        cues.append((s.start, end, text))
    if not cues:
        sys.exit("Whisper 转录结果为空（检查音轨/语言）")
    print(f"  · 转录完成：{len(cues)} 段，{info.duration:.0f}s 音频", file=sys.stderr)
    return cues


# ============================================================
# main
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="构建影子跟读训练页")
    ap.add_argument("--media", help="音频/视频文件路径")
    ap.add_argument("--srt", help="英文字幕 .srt/.vtt")
    ap.add_argument("--cn-srt", help="中文字幕（可选）")
    ap.add_argument("--url", help="视频直链（yt-dlp 支持的站点）")
    ap.add_argument("--cn", action="store_true", help="URL 模式：尽力拉中文字幕")
    ap.add_argument("--transcribe", action="store_true",
                    help="无字幕时用 faster-whisper 本地转录生成句级时间轴（B 站硬字幕视频的钥匙）")
    ap.add_argument("--whisper-model", default="small", help="Whisper 模型：tiny/base/small/medium（默认 small）")
    ap.add_argument("--lang", default="en", help="音频语言（默认 en）")
    ap.add_argument("--start", help="URL 模式：裁切起点（90 / 1:30）")
    ap.add_argument("--stop", help="URL 模式：裁切终点")
    ap.add_argument("--split-each", type=float, metavar="秒",
                    help="拆期：每期目标时长（如 180），在句边界智能切分，输出 <slug>-p1/p2/… 多期")
    ap.add_argument("--max-height", type=int, default=720, help="URL 模式：最高分辨率（默认 720）")
    ap.add_argument("--title", help="课名")
    ap.add_argument("--slug", help="页面 id / 文件名前缀")
    ap.add_argument("--dict", help="词典 JSON 文件 {word:释义}（可选）")
    ap.add_argument("--source", help="素材来源说明")
    ap.add_argument("--out", help="输出 HTML 路径")
    ap.add_argument("--dedupe-roll", action="store_true",
                    help="YouTube 滚动式自动字幕清洗：去重滚动行→词级时间轴断句（拉到自动字幕时的钥匙）")
    ap.add_argument("--cookies", metavar="浏览器",
                    help="yt-dlp 透传 --cookies-from-browser（如 chrome；YouTube 风控需要，首次弹钥匙串授权）")
    args = ap.parse_args()

    if not args.url and not (args.media and (args.srt or args.transcribe)):
        sys.exit("需要 --url，或 --media + --srt，或 --media + --transcribe")

    offset = 0.0
    tmpdir = None
    title_hint = args.title or ""

    if args.url:
        tmpdir = Path(tempfile.mkdtemp(prefix="shadow-dl-"))
        media, en_srt, zh_srt, dl_title = download_from_url(
            args.url, tmpdir, args.max_height, args.cn,
            ytdlp_extra=(["--cookies-from-browser", args.cookies] if args.cookies else []))
        if not en_srt and not args.transcribe:
            sys.exit("没拉到英文字幕（人工/自动都没有）——加 --transcribe 用本地 Whisper 转录，或换有字幕的素材")
        start, stop = parse_ts_arg(args.start), parse_ts_arg(args.stop)
        if start or stop:
            cropped = tmpdir / "cropped.mp4"
            crop_media(media, start or 0.0, stop or 1e9, cropped)
            offset = start or 0.0
            media = cropped
        srt_path, cn_path = en_srt, zh_srt
        if not title_hint and dl_title:
            title_hint = dl_title
        src_media = media
    else:
        srt_path = Path(args.srt).expanduser().resolve() if args.srt else None
        cn_path = Path(args.cn_srt).expanduser().resolve() if args.cn_srt else None
        src_media = Path(args.media).expanduser().resolve()
        if not src_media.exists():
            sys.exit(f"媒体文件不存在: {src_media}")
        if srt_path and not srt_path.exists():
            sys.exit(f"字幕文件不存在: {srt_path}")

    ext = src_media.suffix.lower()
    if ext in VIDEO_EXT:
        media_type = "video"
    elif ext in AUDIO_EXT:
        media_type = "audio"
    else:
        sys.exit(f"不认识的媒体类型 {ext}")

    slug = (args.slug or re.sub(r"[^\w-]+", "-", (title_hint or src_media.stem)).lower())
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")[:60] or "lesson"
    title = args.title or title_hint or slug.replace("-", " ").title()

    if args.transcribe and not srt_path:
        # 转录读的是（可能已裁切的）成品媒体，时间轴天然对齐，无需 offset
        cues = transcribe_media(src_media, args.whisper_model, args.lang)
    else:
        if args.dedupe_roll:
            cues = split_word_sentences(dedupe_roll(srt_path))
            if not cues:
                sys.exit("滚动字幕清洗结果为空——确认这是 YouTube 滚动式自动字幕（SRT）")
        else:
            cues = parse_srt(srt_path)
            if not cues:
                sys.exit("字幕解析结果为空——检查 SRT 格式")
        if offset:
            cues = shift_cues(cues, offset)
    sents = merge_to_sentences(cues)
    if cn_path:
        cn_cues = dedupe_roll(cn_path) if args.dedupe_roll else parse_srt(cn_path)
    else:
        cn_cues = []
    if cn_cues and offset:
        cn_cues = shift_cues(cn_cues, offset)

    # 拆期：--split-each N 秒，句边界切分；切不出多期则整期
    parts = None
    if args.split_each and args.split_each >= 60:
        parts = partition_sentences(sents, float(args.split_each))
        if len(parts) <= 1:
            parts = None
            print("  · 总时长在目标范围内，整期生成（不拆）", file=sys.stderr)
        else:
            spans = " / ".join(f"第{i}期 {fmt_mmss(ms)}-{fmt_mmss(me)}" for i, (ms, me, _) in enumerate(parts, 1))
            print(f"  · 拆为 {len(parts)} 期：{spans}", file=sys.stderr)

    dictionary = {}
    if args.dict:
        dictionary = json.loads(Path(args.dict).expanduser().read_text("utf-8"))

    template = (SKILL_DIR / "template.html").read_text("utf-8")

    def write_lesson(slug_i, title_i, media_file, sents_i, cn_i, out_path=None):
        out_p = (Path(out_path).expanduser().resolve() if out_path
                 else DEFAULT_OUT_DIR / f"{slug_i}-shadowing.html")
        out_p.parent.mkdir(parents=True, exist_ok=True)
        dst_name = f"{slug_i}{media_file.suffix.lower()}"
        dst = out_p.parent / dst_name
        if media_file != dst:
            shutil.copy2(media_file, dst)
        rows = merge_cn(sents_i, cn_i) if cn_i else [(a, b, c, "") for a, b, c in sents_i]
        data = {
            "id": slug_i,
            "title": title_i,
            "source": args.source or (args.url or ""),
            "media": dst_name,
            "mediaType": media_type,
            "duration": probe_duration(dst),
            "sentences": [
                {"start": round(a, 3), "end": round(b, 3),
                 "en": re.sub(r"\s+", " ", en).strip(), "cn": cn.strip()}
                for a, b, en, cn in rows
            ],
            "dictionary": dictionary,
        }
        prev_end = -1
        for i, s in enumerate(data["sentences"]):
            if not s["en"]:
                sys.exit(f"[{slug_i}] 第 {i+1} 句英文为空")
            if s["end"] <= s["start"]:
                sys.exit(f"[{slug_i}] 第 {i+1} 句时间戳异常: {s}")
            if s["start"] < prev_end - 0.35:
                print(f"warn: [{slug_i}] 第 {i+1} 句与上一句时间重叠较大", file=sys.stderr)
            prev_end = s["end"]
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        tmp_out = Path(tempfile.gettempdir()) / f".{slug_i}-shadowing.tmp"
        tmp_out.write_text(template.replace("{{SHADOW_DATA_JSON}}", payload), "utf-8")
        tmp_out.replace(out_p)
        n_cn = sum(1 for s in data["sentences"] if s["cn"])
        print(f"✓ {out_p}")
        print(f"  {len(data['sentences'])} 句 · {data['duration'] or '?'}s · {dst_name}"
              f" · 中文 {n_cn} 句 · 词典 {len(dictionary)} 词")
        return out_p

    outs = []
    if parts:
        for i, (ms, me, part_sents) in enumerate(parts, 1):
            part_file = Path(tempfile.gettempdir()) / f"shadow-part-{slug}-{i}{src_media.suffix.lower()}"
            crop_media(src_media, ms, me, part_file)
            part_sents_shift = [(a - ms, b - ms, t) for a, b, t in part_sents]
            part_cn = [(c0 - ms, c1 - ms, t) for c0, c1, t in cn_cues
                       if overlap(c0, c1, ms, me) > 0.15]
            outs.append(write_lesson(f"{slug}-p{i}", f"{title}（{i}/{len(parts)}）",
                                     part_file, part_sents_shift, part_cn))
            part_file.unlink(missing_ok=True)
    else:
        outs.append(write_lesson(slug, title, src_media, sents, cn_cues, args.out))

    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
