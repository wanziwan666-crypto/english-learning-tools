---
name: english-speaking
description: 雅思口语题库练习页生成 + 本地信箱批改闭环。当用户说「生成口语练习页/口语网页版/口语第 N 讲网页」「铺下一讲口语」「把口语题库做成网页」「把 PDF/Word 题库做成口语练习页」「用这个文档出口语题」，或单字「批」要求批改信箱里的口语作答，或说「起信箱/信箱掉了/信箱离线」要求恢复本地批改服务，或问到口语练习页/信箱服务怎么用时触发。产出单文件 HTML（语音转文字作答、TTS 朗读、两轮打磨——第一遍作答即交 AI 批改、按批改练第二遍再交一次拿两遍对比、Band 7 目标样例），信箱服务由 launchd 常驻托管（127.0.0.1:8765）实现网页提交→AI 批改→自动回填，无手动模式。用户给 pdf/docx/doc/rtf/html/txt/md 文档路径时走 assets/ingest.py 抽取 + references/ingest.md 流程出题（自包含，不依赖课程系统）。与 english-writing（写作）同家族，本 skill 只管口语。
---

# 雅思口语 · 网页练习页生成与批改闭环

## 全景

用户在 `~/Desktop/English Learning/speaking/` 下维护一组单文件练习页（每讲一个 HTML）+ 一个共享信箱服务 + 一个 `index.html` 总目录（用户的日常入口：29 讲清单、已生成/待生成状态、信箱在线徽章）。分工：**网页负责练（高频、离线、语音），对话里的 AI 负责批（个性化反馈经信箱自动回流网页）**。这个分工是用户三轮反馈打磨出来的结论，不要动摇：

1. 不接外部 LLM API——要 key、非离线，批改质量不如直接回对话
2. 页内只放「题库样例」和「Band 7 目标样例」，**针对学生的批改只从信箱来**——页内任何内容都不许冒充批改结果
3. **两遍各自交 AI 批改**（gen-6 起的用户决定，取代旧的「以第二遍为准、两遍之间无 AI」）：第一遍写完页面即提交，学生拿着第一遍批改练第二遍（第二遍作答区在第一遍批改到达后解锁），第二遍再交、批改含两遍对比（内化 vs 顽固）。自评清单环节已删除

## 一、生成一讲练习页

### 第 0 步：先列清单让用户选

用户通常不知道有哪些讲、哪些已生成。触发生成时**必须先列清单**，不要凭空猜测讲次：

1. 扫描 `~/Desktop/English Learning/speaking/` 下已有的 `NN-*.html`（index.html 除外）
2. 与全集对照（读 `index.html` 的讲次卡片，或课程系统 `course-edit_read`），输出「已生成 / 待生成」两栏清单，让用户挑
3. 用户只说「下一讲」时，取已生成讲次的最大号 +1
4. 用户给文档（PDF/Word 等）时，清单步骤换成 `references/ingest.md` Step 3 的文档主题对照清单（先抽取拆题，再列「已匹配 / 文档多出 / index 有文档没有」三栏）

### 数据来源（按优先级）
1. **课程系统题库**：`course-edit_read` 读对应课节（如「雅思口语 2026年9-12月题库」course-20260822-d54mga），每个 activity 的 step content 里有 `instruction`（含题目与参考范文）、`reference`（Band 7 润色版）、`hints`
2. 用户直接给的题目/范文
3. **PDF/Word 题库文档**（pdf/docx/doc/rtf/html/txt/md）：`assets/ingest.py` 机械抽取 + `references/ingest.md` 流程（**必须先读它**）——自包含能力，不依赖课程系统；用户直接给文档路径时优先走这条

**代拟记录（2026-10-13）**：原 20-29 讲（讲次重排后为 36-45 号文件，LESSON_ID 仍 L20-L29）原只有 Part 2 cue card 单题，用户要求补齐「Part 2 + Part 3 追问」多题口径（对齐 46-90）；题库三来源均无这些话题的 Part 3 题，经用户确认按 46-90 风格 AI 代拟——每讲 3 题（sample 朴素 4-5 句、band7 口语升级、hints 2 条中文夹英文、highlights 2-4 个子串精确落 band7），cue card 与范文仍为题库原文。页内 QUESTIONS 块上方有 `/* 本讲第 2-4 题为 Part 3 追问，AI 代拟（2026-10-13…）*/` 注释标记；批改/口径讨论引用这些题时须知其非题库原文。

**讲次重排记录（2026-10-14）**：文件序号曾按历史生成批次穿插（02-15 Part 1、16-29 Part 2/3、30-45 Part 1、46-90 Part 2），目录组内序号断档（15 后接 30、29 后接 46），用户要求连续并合并 Part 2 两组。现结构：「Part 1 · 日常问答」01-31 连续、「Part 2/3 · 长答案 + 深入讨论」32-90 连续（旧 30-45→16-31、旧 16-19→32-35、旧 20-29→36-45，01-15 与 46-90 未动）。**只改文件名前缀与页内 LESSON_NO（显示用）；16-45 号文件的 LESSON_ID/KEY 保留旧号（如 16-travelling.html 内是 L30-travelling）——那是 localStorage 进度与信箱批改路由的键，勿「修正」成与文件名一致，改了会丢用户进度、断历史批改回填。**

### 步骤

1. 复制 `assets/template.html` 到 `~/Desktop/English Learning/speaking/NN-slug.html`（NN=两位讲次号，如 `02-tidiness.html`）
2. 替换 7 个占位符：
   - `<title>` 与 `<h1>` 里的 `__LESSON_TITLE__`（如 `Part 1 · Tidiness 整洁`）
   - `__LESSON_ID__`：`L{NN}-{slug}`（如 `L02-tidiness`），必须全系列唯一——它是 localStorage key 和信箱路由的派生源
   - `__PART_LABEL__`：`Part 1 / Part 2 / Part 3`（题卡标签；Part 2 cue card 讲必改）
   - `__COURSE_LINE__` / `__LESSON_NO__` / `__TOTAL_LESSONS__`
   - `__QUESTIONS_JSON__`：题库数组（schema 见下），用 `json.dumps(questions, ensure_ascii=False, indent=2).replace("</", "<\\/")` 生成后嵌入（`</` 转义防 `</script>` 提前闭合）
3. 确保信箱服务在跑（见下），`open "http://127.0.0.1:8765/NN-slug.html"` 交付——**别用 file:// 直开**：Chrome 对 file:// 源不记忆麦克风授权（每次录音都弹窗），对 127.0.0.1 记一次永久生效。页面 head 里有升级脚本，用户 file:// 双击也会自动跳到同源 http 并带走 localStorage 进度
4. **更新 `speaking/index.html` 总目录**：把该讲从灰色待生成卡片换成 `<a class="lesson" href="NN-slug.html">`。目录页是用户的日常入口（不经过对话），漏更新 = 用户以为这讲不存在。新增讲次卡片也照此维护

### QUESTIONS schema

```json
[{
  "q": "Were you a tidy person as a child?",
  "hints": ["toys scattered around（玩具扔得到处都是）画面感强", "…"],
  "sample": "题库参考范文原文（第一遍后的折叠兜底）",
  "band7": "Band 7 目标样例（唯一展开的样例）",
  "highlights": [["clean up after me", "跟在后面收拾（某人的烂摊子）"], ["…", "…"]]
}]
```

highlights 由 AI 从 band7 里挑 2-4 个：优先固定搭配（如 `attention to detail`）、口语衔接（`That said,`）、画面感动词短语（`descends into chaos`）。子串必须在 band7 原文中精确出现（渲染靠子串高亮），注释用中文、一句话说清为什么值得学。

### 生成后验证（必做）
- `python3 -m http.server 8741 --directory <speaking目录>` 起静态服务，playwright **DOM 断言**（别只看截图——脚本死没死肉眼看不出）：`#flowbar .dot` 数量 === 题数、`#first-0` 存在、`.qtag` 文本含 PART_LABEL、console error / pageerror 为 0（favicon 404 豁免）。教训：02-tidiness 曾因 `.sub` 缺 `id="submeta"`，脚本在 `render()` 前 null 赋值抛错、整页空白，而静态标题看着一切正常
- 若信箱在跑，确认 fb-zone 显示「🤖 交 AI 批改本题」而非手动模式

## 二、信箱服务（launchd 常驻）

- 脚本：`~/Desktop/English Learning/speaking/mailbox.py`（skill 的 `assets/mailbox.py` 是母本；目录里没有就拷一份过去。**改了母本后同样要拷过去并重启 launchd 才生效**，流程见下）
- **已装 LaunchAgent**：`~/Library/LaunchAgents/com.fangyiwan.english-speaking-mailbox.plist`——开机自启 + KeepAlive 崩溃自动拉起，**正常情况下永远在线，没有手动模式**（页面离线时只显示恢复指引 + 重试按钮）
- 协议：`GET /ping`、`POST /submit`（网页提交作答）、`GET /feedback?ts=`（网页轮询批改）、`POST /grade`（agent 批改写回：追加 feedbacks + 按 ts 删本次处理的 submissions，mailbox.json 的读改写全在 `_BOX_LOCK` 内串行完成——**agent 永远不要直接改写 mailbox.json**，与服务器并发整读整写会互相覆盖、静默丢提交）、`POST /stt`（本地语音转文字兜底：body 为浏览器识别失败时上传的录音裸字节 webm/mp4，服务器用 faster-whisper small int8 CPU 本地转写返回 `{ok, text}`，不依赖网络；模型懒加载常驻，`_STT_LOCK` 串行排队；未装 faster-whisper 或模型未缓存返回 503+原因，页面 toast 提示回对话说一声（依赖随 english-shadowing skill 装的 faster-whisper 与 ~/.cache/huggingface 缓存模型；缺了只影响 /stt，其余端点不受影响）。服务器是多线程 ThreadingHTTPServer——转写要跑几十秒，不能堵 /ping、/feedback）、`GET /` 与 `GET /NN-*.html`（静态托管练习页，同源 http 打开；`Cache-Control: no-store` 就地重生成后浏览器立拿新版；Host 为 localhost 时 302 到 127.0.0.1 统一源，防 localStorage/麦克风授权分裂；只放行目录内扁平 `*.html`，无路径穿越）
- 数据文件：同目录 `mailbox.json`（`{submissions: […], feedbacks: […]}`）。**网页会拉走全部 feedbacks——测试后必须清掉测试数据或删掉整个 mailbox.json**，否则会污染用户页面
- 用户说「起信箱 / 信箱掉了 / 信箱离线」时，按序排查：
  1. `curl -s -m 3 http://127.0.0.1:8765/ping` 通了 → 问题在页面侧，让用户刷新
  2. 不通 → `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.fangyiwan.english-speaking-mailbox.plist 2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.fangyiwan.english-speaking-mailbox.plist` 再 ping 验证
  3. 还不通 → 看 `/tmp/ielts-mailbox.err.log`，多半是 python3 路径变了（改 plist 里 ProgramArguments）
- 故意停服务（测试离线提示）：`launchctl bootout gui/$(id -u) ...plist`；恢复用上面的 bootstrap
- **杀端口进程必须加 `-sTCP:LISTEN`**（如 `lsof -ti:8765 -sTCP:LISTEN | xargs kill`）——裸 `lsof -ti:PORT` 会把与该端口有连接的用户浏览器一起杀掉（练习页每 3 秒轮询信箱，Chrome 几乎总有连接）。血的教训，勿再犯。而且信箱归 launchd 管后，正常流程用 bootout/bootstrap，根本不需要 kill

## 三、「批」——批改流程

用户说「批」（或「批一下口语」）时：

1. 读 `mailbox.json` 的 `submissions`；空则告诉用户信箱无待批（可能网页没提交或服务没跑）
2. 逐条批改，格式见 `references/grading.md`（**必须先读它**）——按 submission 的 `round` 分流：`round:1` 批第一遍——**只出【还原（如需）+ 点评】，无对比段、无润色版、无亮点**（第一遍就给润色版等于替学生把第二遍做了，用户 2026-10-14 定的口径），建议要能立刻用于第二遍修改；`round:2` 批第二遍——全量四段：【点评】含两遍对比（内化 vs 顽固），润色版以 second 为底；语音识别同音误差先还原；同题同轮重复提交取 ts 最新一条
3. 批改写回：**必须走 `POST /grade`**（读 mailbox.json 只读无害，写回绝不直接改文件）。`/grade` 在服务器进程内一次完成「追加 feedbacks（服务器自动盖当前时间戳，天然大于网页水位）+ 按 `ts` 删掉本次已处理的 submissions」，不存在并发覆盖窗口
4. 回复用户「好了，网页上看」，并点出 1-2 个最值得注意的修正

写回脚本骨架：

```python
import json, urllib.request
payload = {"ts_done": [<本次已批 submissions 的 ts 原值列表，含同题同轮被取代的旧提交>],
           "feedbacks": [{"lesson": "L02-tidiness", "qi": 0, "round": 1, "text": "【点评】…"}]}
req = urllib.request.Request("http://127.0.0.1:8765/grade",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=5).read().decode())  # {"ok": true, "feedbacks": N, "submissions": M}
```

`round` 必须与所批 submission 一致——页面靠它把批改渲染到第一遍区（解锁第二遍）还是第二遍区；漏写会被当第二轮。

## 四、已知边界（用户问起时答）

- 语音识别（STT）用浏览器原生 API：Chrome 走 Google 服务需联网；Safari 14.1+ 可用。都不支持时按钮会提示，退化为打字。识别会话由页内 `dict` 会话对象管理：浏览器自己断流（静音超时/网络抖动/continuous 上限）会换新实例自动续听、不打断作答，长静音约 8 轮后放弃并提示；点一次按钮=开始、再点=结束，启动等待期间再点=取消；识别服务连不上时（Chrome 需能访问 Google，连不上会话会僵死：start 后零事件、stop 也无响应）由 9 秒无事件看门狗识别——**录音通常是好的，此时不掐录音**：拆掉僵死识别实例、按钮转「■ 录音中…（自动转文字）」继续录，且**边说边转**：听写录音按 4s 切片（MediaRecorder timeslice，最终 blob=全部切片拼接、与整录等价），纯录音模式下每片拼上 webm 初始化段（首个 Cluster ID 0x1F43B675 前的字节）成独立可解码小段，增量 POST `/stt` 转写追加显示——文字约 5-6 秒延迟逐段出现（本地 faster-whisper，用户网络永远连不上 Google 也照常出字；Safari mp4 分片拆不出初始化段则自动放弃边说边转、只留收尾整段）；说完点停后整段重转一遍【替换】这些临时文字（replaceBase，非叠加），整段转写才是最终版；录音条目另有手动「🔍 本地转文字」按钮，转过一次收起防重复追加。自动转写只在整段一个字都没出过时触发（有字说明浏览器识别正常），且要求录音 >2KB（双击取消产生的空壳录音不触发）。点停止 2 秒无响应同样强制收摊——按钮不会卡死
- 录音仅会话内存，刷新丢失（答案文本和批改持久化在 localStorage）
- 练习页日常走 `http://127.0.0.1:8765/` 同源打开（麦克风授权 Chrome 只记这一次）。file:// 双击仍可用——页面 head 的升级脚本会在信箱在线时自动跳到 http，跳转把 file:// 侧 localStorage 的作答进度经 `#migrate=` 带过去、仅补缺不覆盖；信箱离线时留在 file:// 原样可练，只是 Chrome 对 file:// 每次录音都重新弹授权窗（Chrome 的既定行为，无解，别再找设置项）。信箱跨域由 CORS `*` 处理，并带 Origin 校验：curl（无 Origin）、file:// 页面（`Origin: null`）与同源 http 页面放行，浏览器里其他网页一律 403——仅监听回环挡不住它们
- 批改只有一种获取方式：信箱直连。页面离线 = 异常状态（红色指引 + 重试按钮），不要建议手动复制粘贴——用户已明确否决手动模式
