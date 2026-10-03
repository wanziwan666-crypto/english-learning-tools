# English Learning Tools

一套五个 AI Agent Skill，覆盖英文学习的完整闭环：**遇见生词 → 初步学习 → 练习巩固 → 长期记忆**，外加素材线（经济学人供料）与听力线（影子跟读）。

```
┌────────────────────┐   选定一篇 md    ┌──────────────────┐  import_review_vocab  ┌────────────┐
│ english-economist  │ ─────────────→ │ english-reading- │ ────────────────────→ │ vocab-drill│
│ 经济学人·下载拆篇选篇  │  （当粘贴文本）    │ exercises        │  （单向词流输送带）      │ SM2·防遗忘  │
└────────────────────┘                │ 读文章 · 遇见生词  │                       └────────────┘
                                      └──────────────────┘
┌────────────────────┐
│ english-shadowing  │   （听力线，独立无依赖）
│ 影子跟读 · 逐句精听   │
└────────────────────┘
┌────────────────────┐
│ english-writing    │   （写作线，独立无依赖）
│ 雅思写作 · 批改 · 范文库│
└────────────────────┘
```

## Skills

### [english-reading-exercises](english-reading-exercises/)

双入口：把英文文章变成交互式阅读练习页（划词即译、自动单词本、六种练习：单词释义 / 句型改写 / 摘要完形 / 句子重排 / 概念图 / 背诵段落），以及跨文章汇总复习页（Anki 式翻卡、句型运用）。

- 输入：文章 URL / 粘贴文本 / Notion LR Materials 数据库
- 输出（`~/Desktop/English Learning/`）：`articles/*-reading.html`（单文件，浏览器打开即用）→ 根目录 `review-all.html` + `review-vocab.json`

### [english-economist](english-economist/)

阅读链路的素材供料端：从 GitHub 自动更新仓下载当期 The Economist EPUB，拆成一篇一个 markdown（栏目 / 引题 / 副题 / 词数 / 原文链接），生成选篇目录页 `catalog.html`（按期 · 按栏目分组、词数徽章、点击复制路径），选定后交给 english-reading-exercises 当「粘贴文本」做阅读练习。

- 输入：自然语言（「下载经济学人」「来一期经济学人」，可指期号补档）
- 输出（`~/Desktop/English Learning/economist/`）：`<期号>/articles/*.md` + `articles.json` 索引 + 根目录 `catalog.html`
- 零第三方依赖（纯标准库），仅供个人英语学习

### [vocab-drill](vocab-drill/)

独立通用记忆引擎：SM2 间隔重复调度，管「今天该复习哪几个词」。词源不限于阅读——自带 GRE / SAT / TOEFL / IELTS 词表，也可从任意文章提词或直接报词单。词卡带 quirky 例句和情境故事，学习记录落本地。

- **它不知道 reading 的存在**。整个套件里唯一的连接点是 reading 侧的 `import_review_vocab.py`，把复习汇总导出的词表单向灌进来。

### [english-writing](english-writing/)

雅思写作练习，独立无依赖：范文收录（划词进个人词库）+ 四项评分标准批改（TA/CC/LR/GRA 批注式批改页、个人库替换词推荐、重写循环）。

### [english-shadowing](english-shadowing/)

影子跟读训练页生成器，听力线独立无依赖：把「音视频 + 字幕」变成单文件交互训练页——逐句听、单句循环/慢速/盲听、挖空·全句听写、录音跟读回放、点击收词、进度记忆；也支持 yt-dlp 下载、Whisper 转录、macOS TTS 合成场景对话。

- 输入：视频/音频 + SRT/VTT 字幕（或 `--url` 直链、TTS 场景）
- 输出（`~/Desktop/English Learning/shadowing/`）：`<slug>-shadowing.html`（媒体同目录相对引用）

## 安装

整套 clone（或复制）到你的 Agent skills 目录：

```bash
git clone https://github.com/wanziwan666-crypto/english-learning-tools.git \
  ~/.agents/skills/english-learning-tools
```

五个 skill 保持 `english-learning-tools/<skill>/` 的兄弟布局 —— `import_review_vocab.py` 靠相对路径找 `vocab-drill/vocab.mjs`，必须整套安装这个桥才通。

skill 安装本身不执行任何代码：english-writing 的产出目录 `~/Desktop/English Writing/`（含 `essays/`、`corrections/`、`writing/` 子目录）、english-reading-exercises 的 `~/Desktop/English Learning/articles/`、english-economist 的 `~/Desktop/English Learning/economist/` 都会在安装后的第一次 skill 会话里由 agent 自动创建，无需手动建目录。

## 更新

已 clone 的用户在仓库目录跑一句即可（也可以让 agent 代跑）：

```bash
git pull
```

clone 过旧仓库名 `english-reading-skills` 的同样直接 pull —— GitHub 会对旧地址自动重定向，无需改 remote。通过 Download ZIP 或手动复制安装的是静态快照，更新需重新下载覆盖。

## 共享架构

五个 skill 由同一套模式构成（vocab-drill 是 Node，其余同款）：

- **Python 脚本 + HTML 模板**：数据 JSON 用 `json.dumps(..., ensure_ascii=False).replace("</", "<\\/")` 注入模板占位符（`</` 转义防止 `</script>` 提前闭合），生成自包含单文件 HTML，浏览器打开即用，无需服务器。
- **生成前校验**：`validate_data.py` 检查「原文逐字存在」「批注落在对应段落」等约束 —— LLM 编造不在原文中的句子是实测最高频 bug，校验不过不许出文件。
- **浏览器侧状态**：单词本 / 词本存 localStorage，按页面 slug 分 key；长期记忆类状态（vocab-drill 调度、雅思个人库）落本地 JSON 文件。
- **视觉**：navy / cream 手绘笔记本风，同一套 CSS 变量。
