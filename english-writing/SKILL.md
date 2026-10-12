---
name: "english-writing"
description: "雅思写作练习系统：两个入口 —— (1) 范文收录：传入一篇雅思范文，或给一个含多篇范文的 pdf/docx/txt/md 文档路径批量解析成一个**单页合集**阅读页（内置目录点击切篇，每篇词典与单词本独立），划词即收进单词本（localStorage，仅存浏览器）；(2) 批改作文：给题目则生成写作页（打开时弹窗自选倒计时时长），或直接粘贴写好的作文，agent 生成按雅思四项评分标准（TA/CC/LR/GRA）的批注式批改 HTML，薄弱处高亮并推荐个人库里的更好替换词，含「重写」按钮循环练习。当用户说 '雅思作文'、'雅思写作'、'范文收录'、'批改作文'、'写作练习'、'IELTS writing'、'帮我改作文'、'生成写作页面'、'收录好词'、'导入素材库'、'删减素材库'、'应用删除'、'解析文档'、'学习这份文档'、'同步词库到写作'、'导入 vocab-drill 词库' 等时触发。"
---

# English Writing Practice

帮助用户建个人「好词好句 / 同义替换库」并循环练习雅思写作与批改。

## 前置条件

- **Python 3**：用脚本把 JSON 注入 HTML 模板（避免手工转义出错）。
- **浏览器**：生成的 HTML 用浏览器打开即可交互。
- **本 skill 目录**：脚本与模板都相对 `SKILL.md` 所在目录定位，不要写死绝对路径。
- **生成文件目录**：`~/Desktop/English Learning/`，按类型分子目录：`essays/` 范文阅读页（含 `my-library.html` 素材库浏览页）、`corrections/` 批改页、`writing/` 独立写作页；进度汇总 `review-corrections.html` 固定在根目录（每次删旧建新）。
- **目录骨架懒创建（每次会话开始先做，幂等）**：skill 安装只是复制文件、不会执行任何代码，所以「安装即有目录」落地为——**每次 english-writing 会话开始（无论用户来干什么，批改/收录/看库都算）**先跑一句，首次安装后的第一次会话就把 `English Learning` 文件夹连子目录建好，用户无需手动创建：
  ```bash
  mkdir -p ~/Desktop/English\ Writing/{essays,corrections,writing}
  ```
  各 build 脚本对输出路径另有 `mkdir -p` 兜底，双保险。

## 核心概念

- **单词本（localStorage）**：范文阅读页的划词即收录，跟 `english-reading-exercises` 一样零摩擦 — 划选即存、刷新不丢，无需任何粘贴操作。
- **两条入口互不依赖**：入口 1 往单词本里「存」好词好句，入口 2 从个人库「取」做批改建议。用户可以只用来收录、只用来批改，或两者配合。
- **个人库（library.json）**：`~/Documents/english-writing/library.json`，长期积累的同义替换库，按「汉语释义」聚成同义组。单词本是单篇范文的临时产物，个人库是跨范文的长期资产 —— 两者靠**导入素材库**这一步连接（见「导入素材库」小节）。批改时 agent 从库里取替换建议。可选，不影响收录功能。

## 接收粘贴内容的判定

agent 在对话里收到用户粘贴的内容时：

- 以 `[English 作文]`（新版写作页）或 `[IELTS 作文]`（旧版页面，同样受理）开头、含 `essay:` 块 → 来自写作页「提交」→ 走 **入口 2 批改**。
- 每行形如 `词\t释义\t例句` 的多行文本 → 来自 english-reading-exercises 的单词本导出（或手动整理的三列文本）→ 走 **导入素材库**（词源 A，见下）。
- 否则按用户的自然语言意图分流（给题目 / 给范文 / 直接贴作文）。

## 传数据给脚本：优先用 `--data-file`

所有 build 脚本都同时支持 `--data '<json>'` 和 `--data-file <path>`。**默认用 `--data-file`**：
英文作文里 `people's`、`don't` 这类撇号会截断 shell 单引号，`--data` 必然失败。先把 JSON
写到临时文件（如 `/tmp/english-<slug>.json`），再传 `--data-file`。只有短的、确定无引号的
数据（如 writer 的题目）才可以图省事用 `--data`。

---

# 入口 1：范文收录（单词本）

收录功能完全在浏览器内完成，跟 `english-reading-exercises` 一样：划词即收、无需粘贴回 agent。

### Step 1：拿到范文
用户提供一篇雅思范文，三种方式任选：**本地文件路径**（agent 直接读盘，最省事）、URL（WebFetch 抓正文）、直接粘贴文本。标题、来源一并记下。
若给的是 **pdf/docx 或一个文档里含多篇范文**，走下方「批量解析文档」小节：先解析成纯文本，再逐篇生成。

### Step 2：生成词典 + 组装阅读数据
为范文中 **非基础、值得积累** 的词与词组生成语境化中文释义（CEFR B1+ 以上，含动词/名词/形容词/副词/词组，如 "play a pivotal role", "shed light on"）。输出 `dictionary`：`{ "小写词或原样词组": "中文释义" }`。

组装阅读数据对象（与 `english-reading-exercises` 同构）：
```json
{
  "id": "从标题生成的 slug",
  "title": "范文标题",
  "source": "URL 或 '用户粘贴'",
  "content": "<p>段落1</p><p>段落2</p>...",
  "dictionary": { "term": "释义", "...": "..." }
}
```
`content` 用 `<p>` 包裹段落，保留 `<h2>/<blockquote>/<strong>` 等语义标签。

### Step 3：生成阅读页（build_reader.py）
把上面的 JSON 写入 `/tmp/english-<slug>-reader.json`，然后：
```bash
python3 "<skill>/scripts/build_reader.py" --data-file /tmp/english-<slug>-reader.json --out ~/Desktop/English\ Writing/essays/<slug>-reader.html
```
脚本把数据注入 `templates/reader.html`（`{{READER_DATA_JSON}}` 占位），写出自包含 HTML。用 `present_files` 或告知路径，让用户在浏览器打开。

阅读页行为（模板内置，无需在数据中指定）：
- 鼠标划词 → 自动查本地词典，查不到走免费翻译接口 → 翻译气泡 + **自动收进右侧单词本（localStorage）**。零摩擦，无需任何按钮。
- 单词本可单条删除。
- 单词本仅存浏览器，它是划词的即时层；沉淀进素材库走顶栏「导入素材库」按钮
  （见「导入素材库」小节），另有「导入 vocab-drill 词库」旁路。
- 底部导航条：同目录阅读页（`*-reader.html`）按首次创建顺序串成链，固定在页面底部，
  显示 上一篇/下一篇 与序号，建页时自动刷新全部页面（含老页面）；合集页阅读视图里
  原有的篇级上一篇/下一篇不受影响（见 `refresh_nav.py`）。

### 数据完全在浏览器内
- 单词本保存在 `localStorage`（key: `english_collect_<slug>`），刷新不丢。
- 划词即收录，不需要粘贴回 agent。
- 不设导出：单词本只在浏览器内积累与查看。
- 跨篇汇总：阅读页顶栏「导入素材库」按钮会汇总所有页面划过的词（file:// 共享存储），
  不限当前篇。

### 批量解析文档（一篇文档 → 单页合集阅读页）

用户上传一个含多篇范文的文档（pdf/docx/doc/rtf/html/txt/md，给路径即可）时。本流程是 skill 自带能力，任何安装者扔一个文档路径进来即可用：

1. **机械抽取**（不挑结构，只出纯文本）：
   ```bash
   python3 "<skill>/scripts/parse_document.py" --file <文档路径> --out /tmp/english-<slug>-raw.txt
   ```
   - PDF 走 PyPDF2，输出带 `===== PAGE N =====` 分页标记（范文合集常一页一篇，边界好认）；提取出的文本极少说明是扫描版 → 改用 Read 工具按页读该 PDF（无 PyPDF2 时也走这条路）。
   - docx 走 Python 标准库解 zip（跨平台零依赖，按段落保留边界）；doc/rtf/html 走 macOS `textutil`；txt/md 原样读。
2. **agent 读 raw 文本拆篇**：识别每篇的标题/题目行/正文（常见结构如「N. 中文标题 + 英文题目 + 范文正文」，但**别假设结构**——编号、分页标记、题目行、字数尾注只是常见信号，按手头文档的实际结构找每篇边界即可），**顺手修复 PDF 提取的断词**——`pr oduced`→`produced`、`film -making`→`film-making`、`th e`→`the`、压掉多余空格。篇数多时把行号范围分给并行子代理处理，省主对话 context。
3. **组装合集数据并生成单页**：全部篇目装进一个 JSON（`essays` 数组，每篇即上面 Step 2 的 reader 数据）：
   ```json
   {"id":"<slug>","title":"文档标题","source":"文件名",
    "essays":[{"id":"<slug>-01","title":"1. 中文标题","source":"… · 295 words · band 9",
               "content":"<blockquote>题目</blockquote><p>…</p>…","dictionary":{…}}]}
   ```
   - 每篇 `id` 必须全合集唯一（如 `<slug>-<NN>`）——单词本按篇 id 存 localStorage（`english_collect_<每篇id>`），跨篇或重跑都不能撞。
   - `content` 题目放开头 `<blockquote>`、正文一段一个 `<p>`；`(295 words, band 9)` 这类尾注移进该篇 `source`（目录卡片上显示），不进正文。
   - 篇数多时先把各篇分给并行子代理生成（各写各的 JSON），再合并成 `essays` 数组。
   ```bash
   python3 "<skill>/scripts/build_collection.py" --data-file /tmp/english-<slug>-collection.json --out ~/Desktop/English\ Writing/essays/<slug>-reader.html
   ```
   产物是**一个**自包含 HTML：打开先是目录，点任意篇进入阅读（URL `#e=<篇id>` 可直达/收藏），「目录」按钮或篇末「目录」返回，底部「上一篇 / 下一篇」顺序刷。每篇词典与单词本独立，划词收录行为与单篇范文完全一致。脚本自带校验（必填字段 + id 唯一）。

### Step 4：导入素材库（个人库 library.json —— 写作 skill 自己的库）

素材库 = `~/Documents/english-writing/library.json`，批改时 ★ 替换建议的唯一来源。
**与 vocab-drill 无关**（那是另一个独立功能的输入侧，见「从 vocab-drill 一键导入」）。

**这一步是可选的、用户触发的** —— 不要在生成阅读页后自动催促。当用户说「导入素材库」
「入库」「存进词汇库」「同步一下」时才做。两种词源，按用户意图选：

**词源 A：用户划过的词/词组（「导入素材库」默认指这个）**
0. **懒导入（每次 english-writing 会话开始先做，不用等口令）**：用户点「导入素材库」
   按钮（**阅读页/合集页顶栏主按钮**）就是导入意图。
   点击会汇总**所有页面**划过的词（file:// 共享 localStorage，不只当前篇）下载
   `writing-wordbank-export.txt`。保存对话框默认停在哪是浏览器自己的记忆，页面无法指定
   （沙箱限制）；用户应存进 `~/Desktop/English Learning/`。任何会话开始（批改/收录/看库，
   无论用户来干什么）先查（主位置 English Learning，`~/Downloads` 兜底——浏览器不弹窗
   直落下载文件夹时也能拾取）：
   ```bash
   ls -t ~/Desktop/English\ Writing/writing-wordbank-export.txt ~/Downloads/writing-wordbank-export.txt 2>/dev/null | head -1
   ```
   固定文件名、不用通配符（本机 zsh 下 glob 无匹配会中止整条命令，`||` 兜底也不执行）；
   两处按 mtime 全局取最新。浏览器提示「替换」时选替换，避免出现 ` (1)` 副本被漏拾取。
   对比 `~/Documents/english-writing/wordbank-import-state.json` 记录的上次导入时间
   （无此文件视为从未导入）。文件比记录新（或从未导入过且文件存在）→ **静默自动导入**
   （读词聚类走下面的步骤），完成后把新时间写回 state 文件，并向用户提一句已导入。
   导入幂等（同组同名 term 自动跳过），重复检测无害。
   **导入成功即删除该导出文件**（路径以实际命中的为准——含尾部空格等变体名）：旧文件不再
   滞留反复触发导入判断，下次点按钮是全新保存，也就不会再撞浏览器「替换」提示或冒出
   「 (1)」/变体名副本。口令触发的强制重扫（下条）同样删。文件不存在 = 无待导入，正常态。
   会话开始顺手同查**删除清单**（浏览页删除模式导出的，存在即应用）：
   ```bash
   ls -t ~/Desktop/English\ Writing/writing-library-deletions.json ~/Downloads/writing-library-deletions.json 2>/dev/null | head -1
   ```
   命中即静默跑 `apply_library_deletions.py`（自动找同两处最新文件：备份 → 删组删词 →
   刷新 my-library.html → 删清单），完成后向用户提一句结果。
1. 口令「导入素材库」仍然有效：用户说了就立即执行同一流程（不看 state，强制重扫）。
2. 完全找不到导出文件时才提示用户：打开任意阅读页点「导入素材库」，保存进
   `~/Desktop/English Learning/`。这一 click 无法省略：浏览器沙箱不允许页面悄悄写磁盘，agent 也读不到
   浏览器内部存储，localStorage → 磁盘文件必须经用户之手（阅读 skill 的「导出词本」
   按钮同理）。不要退回让用户手动复制粘贴。

**词源 B：全量词典（用户说「入库」「把这篇的词都收进素材库」）**
0. 阅读页/合集页生成时已把每篇词典内嵌进 HTML，`extract_dictionary.py` 直接从 `essays/`
   读出来（与阅读 skill 的 review-vocab.json 同构）：
   ```bash
   python3 "<skill>/scripts/extract_dictionary.py" --out /tmp/english-dict.json
   ```
   从抽出的词典里**筛值得做替换建议的词**（素材库是同义替换库，主题名词/基础词不必进）。

3. **先读已有组名**，避免把 `重要的` 和 `重要/起作用` 拆成两个近义组：
   ```bash
   python3 "<skill>/scripts/manage_library.py" --print
   ```
   合并靠 `group_meaning_zh` 的归一化字符串精确匹配（去掉非字母数字后小写比较），**不做语义判断**。
   所以复用已存在的组名是 agent 的责任：能归进已有组就用那个组的原文组名，别造新说法。

4. **聚类入库**（两种词源共用）。把词按语义归组写入 `/tmp/english-lib-add.json`
   （划词词单的第三列原句可作 `example`；词组 term 照收）：
   ```json
   {"items":[
     {"term":"crucial","pos":"adj","translation":"至关重要的","group_meaning_zh":"重要的",
      "example":"Education is crucial to social mobility.","source":"<范文标题>"}
   ]}
   ```
   ```bash
   python3 "<skill>/scripts/manage_library.py" --data-file /tmp/english-lib-add.json
   ```
   `group_meaning_zh` 留空的条目会进 `ungrouped`，批改时取不到 —— 尽量都给组名。
   同组内同名 term 自动跳过，重复入库安全。
   **聚类宁粗勿细**：共享关键词/词根的词条并进同一组（community cohesion / cultural cohesion
   → 「凝聚」，housing shortages / housing needs → 「住房」），只有找不到家族的单词条才独立成组——
   一词一组等于没聚。

5. **刷新浏览页**（可选，用户想看库时）：
   ```bash
   python3 "<skill>/scripts/build_library_view.py"
   ```
   阅读页顶栏「素材库」按钮打开的就是这个页面（同目录下的 `my-library.html`）。

6. **删减素材库（浏览页删除模式）**：`my-library.html` 顶栏「🗑 删除模式」进入——词条打 ✕、
   组头「🗑 删整组」，再点一次撤销，标记只在当前页面内存里（刷新即清）。标完点
   「⬇ 导出删除清单」下载 `writing-library-deletions.json`（固定名，存 English Learning，
   提示「替换」时选替换）。应用走 `apply_library_deletions.py`（会话开始自动查，见上；
   口令「应用删除」「删减素材库」立即执行）：
   - 整组：组名归一化精确匹配，整组删除；
   - 词条：先在清单指定的组内找；组名对不上时全库唯一同名词条兜底；组在而词不在 → 跳过并报告；
   - 删空的组自动清掉；库先备份成 `library.json.bak`（保留一代）；应用后自动刷新浏览页并删清单。

### 从 vocab-drill 一键导入词库（跨 skill 桥接）

用户说「同步词库到写作」「导入 vocab-drill 词库」时，一条命令把背诵词库沉淀进个人库：

```bash
python3 "<skill>/scripts/import_vocab_drill.py"          # 加 --dry-run 可先预览
```

- 只**读** `~/.vocab-drill-state[-名字].json`（state 只由 vocab.mjs 写，本脚本不碰写侧），合并复用 `manage_library.py` 的同义组归并与组内去重——**重复执行安全**。
- 词卡的中文释义同时作为 `group_meaning_zh`：同释义的词自动聚组；之后范文入库遇到相同释义也会并进同一组。
- 只导**有词卡**的词（无词卡的还挂在待首测，词卡生成后重跑即可补进），`source` 标为 `vocab-drill`。
- 导入后若用户想看库，顺手跑 `build_library_view.py` 刷新浏览页。

---

# 入口 2：批改作文

### 2a：给定题目（先生成写作页）
用户提供题目（如 "Some people think... To what extent do you agree?"）和题型（task1/task2，默认 task2）。
组装写作数据：
```json
{"id":"slug","topic":"题目原文","task":"task2","minutes":45}
```
`minutes` 只是弹窗的预填默认值（首次打开时用；之后记住上次选择，localStorage）。
```bash
python3 "<skill>/scripts/build_writer.py" --data '<上面的 JSON>' --out ~/Desktop/English\ Writing/writing/<slug>-writer.html
```
写作页内置：题目展示、打开时弹窗自选倒计时时长（快捷 20/40/45/60 分钟或自定义，确认后才开始计时；计时中可「改时间」/暂停/重置）、文本框、字数与段落数实时统计、「提交」按钮（复制作文到剪贴板，格式以 `[English 作文]` 开头含 `essay:` 块）。用户写完粘贴回对话框 → 走下方批改。

> 若用户直接粘贴写好的作文（不给题目），跳过写作页，直接进入批改；`topic` 留空、`task` 按用户说明或默认 task2。

### Step 2：生成批改数据
agent 对作文做四项评分标准分析（参考 `references/english-criteria.md`）：TA（任务回应）、CC（连贯衔接）、LR（词汇丰富度）、GRA（语法准确度）。

批改前先取个人库，用于「薄弱表达 → 库里更好替换」的推荐：
```bash
python3 "<skill>/scripts/manage_library.py" --print
```
用这个命令而不是直接读 `library.json`：库积累大了整份读进来会占掉大量 context。库为空或不存在时
输出空结构，此时所有 `suggestion` 留空即可，不影响批改。

产出批改数据：
```json
{
  "id": "slug",
  "topic": "题目（若有）",
  "task": "task2",
  "essay": "<用户作文原文，段落用换行分隔即可>",
  "band": {"overall": 6.5, "ta": 6, "cc": 6.5, "lr": 6, "gra": 6},
  "summary": "总体评语（2-4 句，点出最该改的 1-2 件事）",
  "annotations": [
    {
      "level": "word",            // word | phrase | sentence | paragraph
      "paragraph": 0,             // 第几段（0 起）
      "text": "good",             // 作文里被批注的原文片段（须在 essay 中能定位）
      "band": "LR",               // 关联哪项评分标准
      "severity": "improve",      // error（错误）| improve（可提升）| good（亮点）
      "comment": "偏口语/笼统，库里有更学术的替换",
      "suggestion": "beneficial", // 来自个人库的更好表达（可空）
      "category": "冠词 a/an"     // 可选：错误类型标签（汇总页高频清单优先采用，缺省按关键词规则归类）
    }
  ]
}
```
`text` 必须是作文里**逐字存在**的片段，模板靠它在正文里高亮定位。`suggestion` 优先取自个人库里语义相近的 term；命中时该批注会高亮成「库推荐」样式。

**同段内批注的片段不能相互包含**：模板定位时长片段先占位（`buildMarks()` 按 text 长度降序），被更长片段整段覆盖的短批注拿不到位置，页面上既没有高亮、也会被归到「未定位」栏里。想同时点评一个长句和它内部的某个词，就让长句批注只取该词之外的部分（如整句改引其后半句），或把两条合成一条。`validate_data.py` 会重放这个占位规则并报错，别只靠肉眼检查。

### Step 3：生成批改页（build_correction.py）
先写 `/tmp/english-<slug>-correction.json`（**必须用 `--data-file`**：作文里的撇号会截断 shell 单引号），校验后生成：
```bash
python3 "<skill>/scripts/validate_data.py" --kind correction --data-file /tmp/english-<slug>-correction.json
python3 "<skill>/scripts/build_correction.py" --data-file /tmp/english-<slug>-correction.json --out ~/Desktop/English\ Writing/corrections/<slug>-correction.html
```
模板渲染：左侧作文正文（按段，annotations 片段高亮、悬停/点击看批注），右侧批注栏（按段分组，含 band 标签与建议 chip），顶部四项分数 + 总评，底部「在原文基础上修改 / 重写」两种重写模式（带 `topic` 打开写作模板进入新一轮）。页面最底部另有跨批改页的 上一篇/下一篇 导航（`*-correction.html` 按首次创建排序，建页时自动刷新，见 `refresh_nav.py`）。

### 重写循环
批改页底部两种模式（两个按钮拉开间距，避免误点）：「✎ 在原文基础上修改」→ 打开写作页并**预填上一版作文 + 右侧批注清单**（hash 带 `&essay=...&annos=...`，只含 error/improve 批注）；清单随改随勾——正文里改掉对应片段该条自动 ✓，点击卡片在正文选中定位。「↻ 重写」→ 空白写作页。两者都带 `#topic=...&task=...`，全新计时 → 提交粘贴回对话框 → 再批改。如此循环。

### 批改进度汇总（可选）
多次批改后，可生成汇总页查看分数趋势与薄弱维度：
```bash
python3 "<skill>/scripts/build_correction_review.py"
```
- 数据源是 `~/Documents/english-writing/corrections-log.jsonl`（每次批改由 build_correction.py 自动追加，含批注明细）——log 是数据，HTML 是渲染产物，不要从批改页反解数据
- 兜底：log 功能上线前生成的旧批改页会被扫描收录，时间线取文件修改时间
- 输出 `~/Desktop/English Learning/review-corrections.html`（根目录，不进 corrections/；
  每次删掉上一份再生成，任一时刻只有最新一份）：
  - 分数折线图（Overall / TA / CC / LR / GRA；Chart.js 走 CDN，离线时自动降级，数据以下方表格为准）
  - 高频问题统计：error 批注按雅思评分维度归类（GRA 语法 / LR 词汇 / CC 结构衔接 / TA 任务回应）
  - 高频错误清单：error 批注再按关键词规则聚成具体错误类型（双空格/冠词/人称漂移/中式直译…），
    每类折叠（`<details>`），点开看全部实例（篇目 · 第几轮 · 原文 · 批注）；规则固化在
    build_correction_review.py 的 ERROR_PATTERNS，批注带显式 `category` 字段时优先采用
  - 历次批改记录表格（按时间排序）
- 可选参数：`--dir` 指定兜底扫描根目录（递归查找，默认覆盖 `corrections/` 子目录及旧的平铺文件）、`--out` 指定输出路径

---

# 重要实现注意事项

- **JSON 转义**：所有 `content`/`essay` 含 HTML 或换行，必须用 Python `json.dumps(..., ensure_ascii=False).replace("</", "<\\/")` 注入，禁止手工拼字符串。脚本已处理。
- **批注定位**：`annotations[].text` 必须能在**它自己那一段**（`paragraph` 指定的段）里按子串找到。
  模板是按段定位的，`text` 在别的段落里不算命中，会掉进「未定位批注」。段号从 0 起，按空行分段。
  批注宁可短（一个词组/一句），必要时一条段落拆成多条。
- **库推荐一致性**：`suggestion` 写进库里真实存在的 term；若库里没有合适项就留空，不要编造库中不存在的词。
  模板会给带 `suggestion` 的批注挂「★ 来自你的库」标签，编造的词会让这个标签失真。
- **词典质量**：范文词典宁多勿漏，覆盖学习者可能想积累的搭配与词组。
- **校验**：组装完批改/阅读 JSON 后，用 `scripts/validate_data.py` 跑一遍基本校验（批注 text 在 essay 中、分数范围合理、同段批注片段不相互覆盖），不通过则修正后重生成。

## 脚本一览
- `build_reader.py`：范文 → 阅读页（入口 1）。顺带在同目录刷新 `my-library.html`（每次随建随刷，避免过期）。
- `parse_document.py`：批量解析第一步，pdf/docx/doc/rtf/html/txt/md → 纯文本（PDF 带 `===== PAGE N =====` 标记，扫描版会提示改用 Read 按页读；docx 用标准库跨平台直解）。
- `build_collection.py`：多篇范文 → **单页合集**阅读页（内置目录切篇、上一篇/下一篇，校验必填字段与 id 唯一）。
- `build_writer.py`：题目 → 写作页 + 倒计时（入口 2a）。
- `build_correction.py`：批改数据 → 批改页；同时在输出目录放一份 `writer.html` 供「重写」跳转，并追加完整记录到 `corrections-log.jsonl`。`--no-log` 仅重渲染不记 log（模板微调后重新生成旧页面用，避免 log 重复记录）。
- `refresh_nav.py`：给 essays/（`*-reader.html`）或 corrections/（`*-correction.html`）目录下所有页面注入/刷新底部 上一篇/下一篇 导航（build_reader / build_collection / build_correction 建页后自动调用，也可单独跑）。顺序钉在各目录 `.nav-order.json`：新页面按 mtime 追加、删掉的自动清出、**可手工调整**——文件系统 birth time 会被原位重建与整目录拷贝重置，不能当「首次创建时间」用，清单才是唯一事实源。`my-library.html` / `writer.html` 等工具页不进链。
- `manage_library.py`：`--print` 读库（批改前取建议）｜`--data-file` 入库｜`--init` 建空库。
- `extract_dictionary.py`：从 `essays/` 的阅读页/合集页抽内嵌词典（「入库」的词源，无需用户粘贴）。
- `import_vocab_drill.py`：vocab-drill 词库 → 个人库一键导入（只读 state，`--dry-run` 预览，重复执行安全）。
- `build_library_view.py`：素材库 → `my-library.html` 浏览页（library.json 渲染：组/词统计、
  搜索、「⬇ 下载素材库」备份、删除模式标记与清单导出），`--out` 可指定路径。划词汇总入口在阅读页按钮，不在本页。
- `apply_library_deletions.py`：应用浏览页删除模式导出的 `writing-library-deletions.json`
  （缺省自动搜 English Learning / Downloads 两处取最新）：备份 `library.json.bak` → 删整组/删词条
  → 清空组 → 刷新 my-library.html → 删清单；`--file` 指定路径，`--dry-run` 预览不动盘。
- `validate_data.py`：`--kind reader|correction` 生成前校验（批注是否在对应段落、分数是否 0-9、同段批注片段是否被更长片段整段覆盖而渲染成「未定位」）。
- `build_correction_review.py`：读批改 log（旧 HTML 兜底，`--dir`/`--out` 可选）→ 生成进度汇总（分数折线图 + 按评分维度的问题统计 + 按错误类型的高频错误清单，每类折叠展开全部实例）。

## 参考文件
- `references/english-criteria.md`：雅思写作四项评分标准与常见薄弱点清单（批改时对照）。
- `references/library-schema.md`：`library.json` 完整 schema 与示例（可选，用于个人库同步）。
