---
name: english-shadowing
description: "影子跟读训练页生成器：把 音视频+字幕 变成单文件交互训练页（*-shadowing.html）——逐句听、单句循环、慢速、盲听、挖空/全句听写、录音跟读回放、点击收词进单词本、进度记忆。当用户说「影子跟读」「跟读练习」「shadowing」「逐句听」「听写练习」「把这个视频做成跟读课」，或提供 视频/音频+SRT 想做口语精听训练时触发。也可用 macOS say 合成场景对话直接生成练习素材。"
read_when:
  - User provides video/audio + SRT subtitle files and wants shadowing practice
  - User says "影子跟读", "跟读练习", "shadowing", "逐句听写", "精听训练"
  - User wants to turn a video with subtitles into sentence-by-sentence listening training
  - User asks to generate spoken-English practice material from a scenario (TTS path)
---

# English Shadowing — 影子跟读训练页

把「媒体文件 + 字幕」变成一个自包含训练页，复刻影子跟读产品的核心训练环：
**逐句听 → 单句循环/慢速/盲听 → 挖空·全句听写 → 录音跟读对比 → 点击收词 → 进度记忆**。

输出：`~/Desktop/English Learning/shadowing/<slug>-shadowing.html`（媒体文件同目录放置，相对路径引用）。

## 前置条件

- Python 3（构建脚本）
- 媒体文件：mp4/webm/mov 或 mp3/m4a/wav
- 字幕：`.srt` / `.vtt`（英文必需；中文可选，按时间重叠自动合并）
- 无需任何 API Key；划词翻译离线优先（内嵌词典），联网时走 MyMemory → Google 免费接口
- 录音跟读需浏览器麦克风权限（Chrome 对 file:// 页面会正常弹窗）

## 新用户环境准备（首次使用，agent 代跑）

用户全程自然语言提需求，**下面的自检与安装命令一律由 agent 自己执行**，不要把命令甩给用户跑。

**依赖随路径递增**，用到哪条装哪条：

| 路径 | 需要安装 |
|---|---|
| A 媒体 + 字幕文件 | 仅 Python 3（系统自带即可） |
| B 视频直链 `--url` | A + `yt-dlp`、`ffmpeg` |
| C Whisper 转录 `--transcribe` | B + `faster-whisper`（pip） |
| D TTS 合成场景对话 | 仅 macOS 系统自带（`say` / `afconvert`），零安装 |

agent 自检 + 缺啥装啥（macOS / Homebrew）：

```bash
# 自检：逐项打印 ok / 缺失
which ffmpeg yt-dlp; python3 -c "import faster_whisper; print('whisper ok')" 2>/dev/null || echo "faster-whisper 缺失"

# 缺什么装什么
brew install ffmpeg yt-dlp          # 路径 B/C 需要
python3 -m pip install faster-whisper   # 路径 C 需要（装进将运行构建脚本的那个 python3）
```

**坑位提示**：
- `faster-whisper` 必须装进**运行 `build_shadowing.py` 的那个 python3**。若机器上有多个 python
  （如 brew python 与系统 python 并存），用 `python3 -m pip` 而不是裸 `pip3`，避免装错解释器。
- Whisper 模型**无需手动下载**：首次转录自动经 hf-mirror 拉取（small 约 460MB，之后走本地缓存）。
  国内网络无需配置，脚本内置镜像；海外网络也兼容。
- Linux 用户的 `say/afconvert`（路径 D）没有等价物，跳过该路径即可，其余路径不受影响。

## 建课前必做：估时长 → 按需询问拆期

拿到素材**先查时长**再动手：

```bash
# URL（多 P 视频记得带 ?p=N）
yt-dlp --skip-download --print "%(duration)s" "<链接>"
# 本地文件
ffprobe -v error -show_entries format=duration -of csv=p=0 <file>
```

**单期时长参考范围**（跟读按句消化，上限针对的是整期泛听的注意力，不是硬限制）：

| 内容类型 | 理想单期 | 上限 | 说明 |
|---|---|---|---|
| 生活场景对话 | 1–2 分钟 | 3 分钟 | 越短越适合反复打磨 |
| Vlog / 播客对话 | 2–3 分钟 | 5 分钟 | |
| 访谈精听 | 2–4 分钟 | 5 分钟 | |
| **考试听力（雅思/托福）** | **一个自然 Part/篇** | 8 分钟 | Part 是完整场景，跟读按句练不吃长度；超出 8 分钟才考虑拆 |

**询问规则**（推荐项按素材类型给，别机械套 5 分钟线）：
- **≤ 5 分钟**：不问，直接整期生成。
- **5–8 分钟**：用 question 工具问用户「整期 / 拆分」，但推荐项看类型——
  **考试听力推荐整期**（Part 保持完整，题目场景对应得上），其他类型推荐拆分。
- **> 8 分钟**：默认建议拆分；考试听力优先在 **Part 边界**拆（用 --start/--stop 手工对齐，
  别在对话中间切），非考试内容用 --split-each 句边界自动拆即可。
- 用户说「拆」「分几节」等明确意愿时直接执行对应方案。

**拆分执行**：加 `--split-each <秒>`（推荐）——脚本在**句边界**智能切（不会切在话中间），
转录只跑一次、每期独立成页（`<slug>-p1/p2/…`，标题自动带「2/3」编号）。
需要精确控制区间时才用 `--start/--stop` 逐段手工裁。

## Workflow

### 路径 A — 用户给了媒体 + 字幕

1. 确认文件：媒体（视频/音频）、英文字幕 SRT；问清是否有中文字幕 SRT（双语体验更好）。
2. （推荐）为字幕里的非基础词生成离线词典（LLM 一步）：
   ```json
   { "latte": "拿铁", "oat": "燕麦的", "receipt": "收据" }
   ```
   存临时文件后用 `--dict` 传入——离线划词即时出释义，不依赖网络。
3. 构建：
   ```bash
   python3 <本 skill 目录>/build_shadowing.py \
     --media /path/to/video.mp4 \
     --srt /path/to/en.srt \
     --cn-srt /path/to/zh.srt \
     --dict /tmp/dict.json \
     --title "课名" --slug lesson-id \
     --source "素材来源说明"
   ```
4. `open` 生成的 HTML 交付。

### 路径 B — 视频直链（yt-dlp，已安装于 /opt/homebrew/bin）

```bash
python3 <本 skill 目录>/build_shadowing.py --url "<视频链接>" [--cn] \
  [--start 1:30 --stop 3:00] [--max-height 720] [--dict /tmp/dict.json] \
  [--cookies chrome] [--dedupe-roll] \
  --title "课名" --slug lesson-id
```

自动：yt-dlp 下载视频 + 拉字幕（人工字幕优先、缺失退自动字幕，转 SRT）→
`--start/--stop` 用 ffmpeg 裁切并自动平移字幕时间轴（长视频拆期练）→ 构建。

**本机网络现实（2026-10 实测，重要）**：
- YouTube / Vimeo 直连不通（yt-dlp 请求 API 会挂死，杀进程换代理，别等）；挂代理（127.0.0.1:7890）
  设 `HTTPS_PROXY` 后**还需 `--cookies chrome`**——2026-10 起代理出口 IP 被 YouTube 风控
  （429 + "Sign in to confirm you're not a bot"，换 ios/tv/android_vr 等客户端参数也没用）。
  首次读 Chrome cookies 会弹 macOS 钥匙串授权框，让用户点「**始终允许**」（点一次永久生效，
  只点「允许」下次还弹）；之后偶报 "The page needs to be reloaded"，重试一两次即过。
- yt-dlp 的 TED.com 提取器已坏（官网改版，playerData 字段没了）——TED 素材走 YouTube 源。
- **B 站可达但英语内容基本是烧录硬字幕**（CC 列表只有弹幕，CGTN/BBC搬运/教学号均实测无英文 CC），
  `--url` 对 B 站大概率因「没拉到英文字幕」退出。B 站素材的正确姿势：下载视频后走 **Whisper 转录**
  （faster-whisper + `HF_ENDPOINT=https://hf-mirror.com` 下模型）或让用户在字幕站下载 SRT 后走路径 A。

### 路径 C — 无字幕素材：本地 Whisper 转录（B 站硬字幕视频 / 裸音频的通用钥匙）

```bash
# B 站等视频页链接（yt-dlp 能解析的）
python3 <本 skill 目录>/build_shadowing.py --url "<B站链接>" --transcribe [--whisper-model small]
# 本地裸视频/音频（不需要 SRT，只给媒体文件就行）
python3 <本 skill 目录>/build_shadowing.py --media video.mp4 --transcribe
# 音频/视频文件直链（.mp3/.m4a/.wav 等以媒体文件结尾的 URL，2026-09 实测可用）
python3 <本 skill 目录>/build_shadowing.py --url "https://…/listening.mp3" --transcribe
```

- faster-whisper（已 pip 装好）本地 CPU 转录，模型自动经 hf-mirror 下载（首次 ~460MB，之后走缓存）
- 实测 358s 音频 → small int8 转录约 1-2 分钟，断句质量好（BBC Real Easy English 验证）
- 模型档位：tiny 最快质量差 / base 快（短句清晰音频够用）/ **small 默认推荐** / medium 更准但慢 3 倍
- 转录只有英文文本，无中文句译（页面划词翻译照常可用）；长视频用 --split-each 拆期
- 注意：直接跑脚本不要把 /opt/homebrew/bin 抢先放 PATH（brew 的 python3.13 没有 faster-whisper，
  用系统 python3；脚本内部自动找 /opt/homebrew/bin 下的 yt-dlp/ffmpeg）

**雅思/托福听力素材**：找**直链**音频（URL 以 .mp3/.m4a/.wav 结尾、浏览器打开直接播放的那种），
`--url <直链> --transcribe` 一步成课。备考网站内嵌播放器里的音频（URL 不是媒体文件本身）yt-dlp
不一定能解析——失败就手动下载音频文件后走 `--media` 本地路径，效果一样。真题音频有版权，自用即可别传播。

### 路径 D — 没有素材，想要某场景的跟读课（macOS TTS 合成）

无外部依赖，用系统自带能力合成任意场景对话：

1. 和用户定场景（点咖啡/酒店入住/机场值机…）和 6-10 句对话（每句配中文翻译）。
2. 逐句 `say -v Samantha -r 190 -o sN.wav --data-format=LEI16@22050 "句子"`，
   Python `wave` 模块拼接（句间插 0.4s 静音）→ `afconvert -f m4af -d aac in.wav out.m4a`。
3. 拼接时天然得到每句精确时间戳 → 直接写 SRT（中英各一份）→ 走路径 A 构建。
4. 注意 `say` 语速 `-r` 建议 175-200，贴近真实对话。

### 字幕质量注意

- SRT 碎片 cue（无标点的短行）会被自动合并成句：遇句末标点收口，否则最长 8 秒切一句。
- **YouTube 自动字幕是滚动式**（karaoke：相邻 cue 重复上一行、穿插 ~10ms 擦除 cue、句号常落在行中间），
  通用解析会行间重复 + 断句切在词中间——加 `--dedupe-roll` 清洗：行去重 → 词级时间轴按词尾标点收句、
  长句按逗号换气点软切。TED 演讲实测断句质量好（2026-10，87 句/10.5 分钟）。中文字幕同走清洗。
  有人工字幕时仍然优先人工（不用此开关）。

## 页面功能（template.html 内置）

| 功能 | 说明 |
|------|------|
| 逐句听/跳句 | 点列表任意句跳转；←/→ 切句，空格播放暂停，R 重播，L 循环 |
| 单句循环 / 逐句模式 | 循环本句；逐句模式播完自动停（方便跟读） |
| 慢速播放 | 0.5×–1.25× |
| 字幕模式 | 双语 / 仅英文 / 仅中文 / 盲听（可点击偷看 2.6s） |
| 挖空听写 | 每句自动挑 ~1/3 实词挖空，逐空判对错 |
| 全句听写 | 整句默写，LCS 词级 diff，准确率 ≥90% 记通过 |
| 录音跟读 | MediaRecorder 录音 → 回听 → 原声对比（先放原句再放录音） |
| 单词本 | 点击字幕任意单词 → 释义 tooltip → 自动收词（含原句语境） |
| 进度记忆 | 播完的句自动打勾，重开页面恢复到上次位置 |

## 与生态的互通（重要设计决策）

- 单词本 localStorage 键用 **`er_wordbank_<id>` 前缀**，与 english-reading-exercises 同族：
  页面「导出单词库」按钮汇总所有 `er_wordbank_*` 词本下载 `wordbank-export.txt`
  （词/释义/原句 三列）→ english-reading-exercises 的懒导入会自动把它灌进 vocab-drill SM2 调度。
  **用户无需任何额外操作**，跟读页收的词自动进入间隔重复闭环。
- 翻译失败时词先进本（标「待翻译」），下次点到自动回填释义；导出时跳过仍无释义的词。
- 与阅读页同款 MyMemory → Google 免费翻译 fallback。

## 常见问题

- **录音按钮没反应**：浏览器不支持或没给麦克风权限；Chrome 打开 file:// 页面首次点击会弹权限框。
- **字幕对不齐**：检查 SRT 时间轴；构建脚本对重叠 >0.35s 的相邻句会打 warning。
- **媒体 404**：媒体文件必须和 HTML 同目录（构建脚本自动复制并加 slug 前缀防撞名）。

## 文件一览

- `template.html`：训练页模板（占位符 `{{SHADOW_DATA_JSON}}`）。
- `build_shadowing.py`：构建脚本（SRT 解析/合并、中英合并、词典注入、媒体落位）。
