#!/usr/bin/env python3
"""
Build correction review HTML: band-score trends + error analysis by IELTS dimension.

Primary data source is corrections-log.jsonl (appended by build_correction.py,
contains scores AND annotations). *-correction.html files are only scanned as a
fallback for corrections built before logging existed — their timeline entry
uses the file's mtime, which stays stable across rebuilds of this page.
"""
import json, re, sys, glob, argparse
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "review-corrections.html"
DEFAULT_DIR = Path.home() / "Desktop" / "English Learning"
# 汇总页放根目录（不进 corrections/），且每次都是删旧建新 —— 用户只关心最新状态
DEFAULT_OUT = DEFAULT_DIR / "review-corrections.html"
LOG_FILE = Path.home() / "Documents" / "english-writing" / "corrections-log.jsonl"

# Coarse view: errors grouped by the annotation's IELTS band dimension — the
# band field (TA/CC/LR/GRA) is the coarse categorisation an IELTS learner wants.
# Fine view (pattern_for / group_error_patterns): keyword rules match comment+text
# to surface concrete error patterns (双空格、冠词、人称漂移、中式直译…);
# an explicit `category` field on the annotation always wins over the rules.
BAND_CATEGORIES = [
    ("GRA", "语法 (GRA)"),
    ("LR", "词汇 (LR)"),
    ("CC", "结构与衔接 (CC)"),
    ("TA", "任务回应 (TA)"),
]

# Ordered rules — first match wins; FALLBACK_PATTERN catches the rest.
ERROR_PATTERNS = [
    ("双空格/标点", r"空格|标点|逗号"),
    ("冠词 a/an", r"冠词|a/an|an trainee|a ed-"),
    ("人称/指代漂移", r"人称|指代"),
    ("词形/拼写", r"词形|拼写|拼错"),
    ("中式直译/搭配", r"中式|直译|搭配|地道"),
    ("词义错位", r"词义错位|想说"),
    ("时态/单复数", r"时态|单复数|复数|单数"),
    ("结构/衔接/冗余", r"连接词|衔接|冗余|结构错乱"),
]
FALLBACK_PATTERN = "其他（未归类）"


def category_for(band):
    for code, name in BAND_CATEGORIES:
        if (band or "").strip().upper() == code:
            return name
    return "其他"


def pattern_for(annotation):
    explicit = (annotation.get("category") or "").strip()
    if explicit:
        return explicit
    hay = (annotation.get("comment") or "") + " " + (annotation.get("text") or "")
    for name, pat in ERROR_PATTERNS:
        if re.search(pat, hay):
            return name
    return FALLBACK_PATTERN


def extract_correction_data(html_text):
    """Extract CORRECTION_DATA JSON from a correction HTML file (legacy fallback).

    Greedy match anchored on the statement that follows the assignment, so a
    `};` occurring inside a string can't truncate the JSON; non-greedy pass as
    a second chance. json.loads is the final validator.
    """
    m = re.search(
        r'const CORRECTION_DATA\s*=\s*(\{.*\});\s*\n\s*(?:function|const|var|let)',
        html_text, re.DOTALL)
    if not m:
        m = re.search(r'const CORRECTION_DATA\s*=\s*(\{.*?\});', html_text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace('<\\/', '</'))
    except json.JSONDecodeError:
        return None


def load_log():
    """Load correction records from corrections-log.jsonl."""
    if not LOG_FILE.exists():
        return []
    records = []
    for line in LOG_FILE.read_text("utf-8").strip().split("\n"):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def normalize_record(rec):
    """Unify a log record or an HTML-extracted correction into one shape."""
    annos = rec.get("annotations", [])
    return {
        "ts": rec.get("ts", ""),
        "slug": rec.get("slug") or rec.get("id", ""),
        "topic": rec.get("topic", ""),
        "band": rec.get("band", {}),
        "errorCount": sum(1 for a in annos if a.get("severity") == "error"),
        "improveCount": sum(1 for a in annos if a.get("severity") == "improve"),
        "annotations": annos,
    }


def group_errors(history):
    """Group error annotations by IELTS band dimension, count + sample comments."""
    groups = {}
    for rec in history:
        for a in rec["annotations"]:
            if a.get("severity") != "error":
                continue
            cat = category_for(a.get("band", ""))
            g = groups.setdefault(
                cat, {"category": cat, "count": 0, "slugs": [], "comments": []})
            g["count"] += 1
            if rec["slug"] not in g["slugs"]:
                g["slugs"].append(rec["slug"])
            if a.get("comment") and len(g["comments"]) < 3:
                g["comments"].append(a["comment"])
    return sorted(groups.values(), key=lambda g: -g["count"])


def group_error_patterns(history):
    """Group error annotations into concrete patterns with every instance.

    Round numbers are per-topic positions in chronological iteration order,
    so「R3」= 该题第 3 次批改.
    """
    groups, rounds = {}, {}
    for rec in history:
        slug = rec.get("slug") or ""
        rounds[slug] = rounds.get(slug, 0) + 1
        for a in rec["annotations"]:
            if a.get("severity") != "error":
                continue
            cat = pattern_for(a)
            g = groups.setdefault(cat, {"category": cat, "count": 0, "instances": []})
            g["count"] += 1
            topic = rec.get("topic") or slug
            g["instances"].append({
                "round": rounds[slug],
                "topic": (topic[:24] + "…") if len(topic) > 24 else topic,
                "date": (rec.get("ts") or "")[:10],
                "band": a.get("band") or "",
                "text": a.get("text") or "",
                "comment": a.get("comment") or "",
            })
    # count desc, 其他 pinned last
    return sorted(groups.values(),
                  key=lambda g: (g["category"] == FALLBACK_PATTERN, -g["count"]))


def build_review(correction_dir=DEFAULT_DIR, output=None):
    correction_dir = Path(correction_dir)

    # 1. History from the log — the durable source (one entry per correction build).
    history = []
    logged_slugs = set()
    for rec in load_log():
        if not rec.get("slug"):
            continue
        logged_slugs.add(rec["slug"])
        history.append(normalize_record(rec))

    # 2. Legacy fallback: correction HTMLs built before logging existed.
    #    Recursive scan from the root — corrections now default to the
    #    corrections/ subfolder, but older flat files must still be found.
    #    mtime is the best available timestamp — and unlike datetime.now(),
    #    it doesn't drift forward on every rebuild of this page.
    for fpath in sorted(glob.glob(str(correction_dir / "**" / "*-correction.html"),
                                  recursive=True)):
        data = extract_correction_data(Path(fpath).read_text("utf-8"))
        if not data or not data.get("id") or data["id"] in logged_slugs:
            continue
        rec = normalize_record(data)
        rec["ts"] = datetime.fromtimestamp(
            Path(fpath).stat().st_mtime).isoformat(timespec="seconds")
        print(f"  ⚠ {Path(fpath).name}: 无 log 记录，按文件修改时间 {rec['ts']} 收录")
        history.append(rec)

    if not history:
        sys.exit(f"❌ 没有可用的批改记录（log: {LOG_FILE}；目录: {correction_dir}）")

    # 3. Chronological order — the template reads the last entry as “最新”.
    history.sort(key=lambda r: r["ts"])

    # 4. Error analysis + slim history for embedding (drop annotations —
    #    the page only needs scores/counts; keeps the file small).
    review_data = {
        "history": [
            {k: r[k] for k in ("ts", "slug", "topic", "band", "errorCount", "improveCount")}
            for r in history
        ],
        "errorGroups": group_errors(history),
        "errorPatterns": group_error_patterns(history),
        "correctionCount": len(history),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    template = TEMPLATE.read_text("utf-8")
    data_json = json.dumps(review_data, ensure_ascii=False).replace("</", "<\\/")
    html_output = template.replace("{{REVIEW_DATA_JSON}}", data_json)
    html_output = html_output.replace("{{TIMESTAMP}}", review_data["generated"])

    if output is None:
        output = str(DEFAULT_OUT)
    out_path = Path(output)
    if out_path.exists():
        out_path.unlink()  # 删掉上一次的汇总页，保持任一时刻只有最新一份
    out_path.write_text(html_output, "utf-8")

    print(f"\n✓ 汇总页: {output}")
    print(f"  批改记录: {len(history)} 条")
    print(f"  问题分组: {len(review_data['errorGroups'])} 组")
    print(f"  错误类型: {len(review_data['errorPatterns'])} 类 / "
          f"{sum(g['count'] for g in review_data['errorPatterns'])} 条 error")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="生成批改进度汇总页（log 为主数据源，HTML 兜底）")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="兜底扫描的根目录（递归找无 log 的旧批改页）")
    ap.add_argument("--out", default=None, help="输出 HTML 路径")
    args = ap.parse_args()
    build_review(args.dir, args.out)
