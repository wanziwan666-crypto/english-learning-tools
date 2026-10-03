---
name: english-economist
description: "经济学人下载·拆篇·选篇目录：从 GitHub 自动更新仓下载当期 The Economist EPUB → 一篇一个 markdown（栏目/引题/标题/副题/词数/原文链接）→ navy/cream 选篇目录页 catalog.html（按期分组、栏目分组、词数徽章、点击复制路径）→ 选一篇交给 english-reading-exercises 做阅读练习。当用户说「下载经济学人」「来一期经济学人」「经济学人最新一期」「挑一篇经济学人」「下载 Economist」时触发。仅供个人英语学习，请勿传播下载物。"
read_when:
  - User says "下载经济学人", "来一期经济学人", "经济学人最新一期", "挑一篇经济学人"
  - User wants fresh long-form English reading material and mentions The Economist
  - User asks what's in the latest issue / wants to backfill an older issue
---

# English Economist — 经济学人下载 · 拆篇 · 选篇目录

阅读链路的上游供料端：**下载当期经济学人 → 拆成一篇一篇 → 目录页里挑一篇 → 交给 english-reading-exercises 生成阅读练习页**。

数据目录（懒创建）：`~/Desktop/English Learning/economist/`

```
economist/
├── catalog.html                      # 总目录页（跨期，拆分后自动重建）
└── 2026-10-03/
    ├── TheEconomist.2026.10.03.epub  # 原件（每期约 6MB）
    ├── articles.json                 # 元数据索引：栏目/标题/词数/文件/摘录
    └── articles/                     # 一篇一个 md（NN-slug.md，全局编号）
```

## 前置条件

- 仅 Python 3（三个脚本全部纯标准库，零 pip 安装）
- 网络：能访问 raw.githubusercontent.com（见下方网络现实）
- 仅供个人英语学习使用；下载物请勿传播

## 新用户环境准备（首次使用，agent 代跑）

用户全程自然语言提需求，**自检命令由 agent 自己执行**，不甩给用户跑。

```bash
python3 --version                       # 唯一硬依赖
# 网络自检：能通就直接用
curl -sI --max-time 10 -o /dev/null -w "%{http_code}\n" \
  "https://raw.githubusercontent.com/hehonghui/awesome-english-ebooks/master/01_economist/te_2026.10.03/TheEconomist.2026.10.03.epub"
```

- 返回 `200`/`302`：直接跑 Step 1。
- 超时/不通：本机若有代理，`export HTTPS_PROXY=http://127.0.0.1:<端口>` 后重试（同 english-shadowing 的网络约定）。
- **SSL 报 certificate verify failed 不用管**：python.org 版 Python 不认系统证书，`fetch_economist.py` 已内置三级自愈（certifi → /etc/ssl/cert.pem → curl 兜底）。

会话开始先懒创建（幂等）：

```bash
mkdir -p ~/Desktop/English\ Learning/economist
```

## Workflow

### Step 1: 下载一期（fetch_economist.py）

```bash
# 最新一期（缺省）
python3 <skill目录>/fetch_economist.py

# 指定期号（补档旧期也走这条；往期自动落到年份归档层去找）
python3 <skill目录>/fetch_economist.py --issue 2026-09-26

# 已存在想重下
python3 <skill目录>/fetch_economist.py --force
```

- 期号格式随意：`2026-10-03` / `2026.10.03` / `te_2026.10.03` 都认。
- 已存在且无 `--force` → 打印「已存在，跳过下载」。
- 下载是原子的（临时文件 + 校验 + 替换），中断不会留残废 epub。
- 同日最新一期的目录可能先建、EPUB 后传：报 404 时脚本会列出上游最近 5 期，提示改选。

### Step 2: 拆分成篇 + 自动重建目录（split_economist.py）

```bash
python3 <skill目录>/split_economist.py --issue 2026-10-03
# 或缺省 = 本地已下载的最新一期（不联网）
python3 <skill目录>/split_economist.py
```

- 产出：`articles/NN-slug.md`（每篇一个）+ `articles.json`（索引）+ 自动重建 `catalog.html`。
- **校验闸门**：拆分全部在内存中完成，任何硬校验不过（0 栏目 / 文章缺标题 / 保留篇数 <40 / 跳过 >15）就整期拒绝、零输出——这是上游 calibre 布局变更的报警器，报错时去检查 EPUB 里的 class 名。
- 短文（<50 词，如 cartoon、指标页）自动跳过并记入 `articles.json` 的 `skipped`，属正常现象。
- 清洗规则：剥离尾部 zlibrary 署名段（原文链接收进 md 头 `origin`）、去 ■ 结尾符、内链降为纯文本、图片丢弃（留 `> [图省略]` 位标记）、表格尽力转 pipe 表。

### Step 3: 打开目录页选篇

```bash
open ~/Desktop/English\ Learning/economist/catalog.html
```

- 按期分组（最新一期默认展开）→ 栏目分组 → 文章行（标题/引题/副题/单行摘录/词数徽章）。
- **点任意文章行 = 复制它的 md 绝对路径**（顶栏常驻「选中路径」框兜底，file:// 下自动复制失败会提示按 ⌘C）。
- 用户也可以不开页面，直接在对话里说：「Leaders 第二篇」「读那篇讲税的」「编号 47」。

### Step 4: 交给阅读练习（关键衔接）

**english-reading-exercises 没有文件输入入口**，衔接方式必须是这样：

1. 用户选定了文章（页面点选后说「读这篇文章」，或说栏目+序号/标题关键词）。
2. agent 用该期 `articles.json` 解析定位：`sections[].articles[]` 里按 `name` + 序号（栏目内第几个）或 `title` 关键词匹配，拿到 `file`（相对期目录）。
3. agent 自己 Read 那个 `.md`，**把正文（frontmatter 以下的部分）当作「用户粘贴文本」**，走 english-reading-exercises 的 **入口 1 路径 A（粘贴文本）**。
4. `title` 用 md 头部的 `title`；`source`/出处填 md 头部的 `origin` 链接；`fly`/`rubric` 可作副题素材。

### Step 5:（可选）手动重建目录

手删过文章/期之后刷新目录：

```bash
python3 <skill目录>/build_catalog.py
```

已不存在的 md 会在目录里剔除（有 stderr 警告）；坏掉的 articles.json 跳过不炸整页。

## Important Notes / 坑位

- **网络现实（实测 2026-10-03）**：raw.githubusercontent.com 直连可用；失败先 `export HTTPS_PROXY=…` 重试。GitHub contents API 未认证限 60 次/时，每次下载只调一次列表，无虞。
- **绝不 git clone 源仓库**（`hehonghui/awesome-english-ebooks` 约 15GB），只按单文件 raw URL 拉取。
- EPUB 每期约 6MB，长年累积约 300MB/年；md 是自包含的，旧 epub 可定期手动清理。
- 上游近期期刊在 `01_economist/te_YYYY.MM.DD/`，往期归档在 `01_economist/YYYY/te_YYYY.MM.DD/`，fetch 已自动处理两层。
- 备用源（**仅记录，未实现解析器**）：`github.com/Monkfishare/The_Economist`（main 分支，`TE/YYYY/YYYY-MM-DD/TE_2026-10-03.epub`），内部是另一套 `feed_N/article_M/index_uXX.html` 布局——主源失效时改写 `split_economist.py` 的解析层（class 名完全不同）。
- EPUB 内部结构是 calibre 抓 economist.com 的固定产物：`book_toc.html`（`li.sec_index_li > a.sec_toc_item`）/ 栏目索引页（`h2.section_index_title`）/ 文章页（`h1.te_article_title`、`h3.te_article_rubric`、`span.te_section_title`、`te_fly_span`、`te_article_datePublished`、`p.link_navbar`）。布局一变，Step 2 的校验闸门会先报警。
- 备份/迁移：整个 `economist/` 目录拷走即可，`articles.json` 里的 `file` 是相对期目录的路径，跨机可用（catalog 里的绝对路径由 build_catalog 现算）。

## 与生态的互通

```
english-economist（素材线：下载·拆篇·选篇）
   └─选定 md ─→ english-reading-exercises 入口1 路径A（粘贴文本）
                  └─ 划词/练习 ─→ review-all.html ─→ vocab-drill（SM2 复习）
```

## 文件一览

| 文件 | 作用 |
|---|---|
| `fetch_economist.py` | 从 awesome-english-ebooks 下载一期 EPUB（urllib + SSL 三级自愈 + curl 兜底 + 原子写） |
| `split_economist.py` | EPUB → 按篇 md + articles.json（HTMLParser 解析、校验闸门、短文跳过、自动触发目录重建） |
| `build_catalog.py` | 扫描数据目录重建 catalog.html（独立可重跑，剔除已删文件） |
| `template.html` | 目录页模板（navy/cream 手账风，`{{CATALOG_DATA_JSON}}` 占位符注入） |
