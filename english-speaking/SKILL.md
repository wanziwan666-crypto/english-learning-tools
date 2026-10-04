---
name: english-speaking
description: 雅思口语题库练习页生成 + 本地信箱批改闭环。当用户说「生成口语练习页/口语网页版/口语第 N 讲网页」「铺下一讲口语」「把口语题库做成网页」，或单字「批」要求批改信箱里的口语作答，或说「起信箱/信箱掉了/信箱离线」要求恢复本地批改服务，或问到口语练习页/信箱服务怎么用时触发。产出单文件 HTML（语音转文字作答、TTS 朗读、两轮打磨、自评清单、Band 7 目标样例、AI 批改直连），信箱服务由 launchd 常驻托管（127.0.0.1:8765）实现网页提交→AI 批改→自动回填，无手动模式。与 english-writing（写作）同家族，本 skill 只管口语。
---

# 雅思口语 · 网页练习页生成与批改闭环

## 全景

用户在 `~/Desktop/English Writing/speaking/` 下维护一组单文件练习页（每讲一个 HTML）+ 一个共享信箱服务 + 一个 `index.html` 总目录（用户的日常入口：29 讲清单、已生成/待生成状态、信箱在线徽章）。分工：**网页负责练（高频、离线、语音），对话里的 AI 负责批（个性化反馈经信箱自动回流网页）**。这个分工是用户三轮反馈打磨出来的结论，不要动摇：

1. 不接外部 LLM API——要 key、非离线，批改质量不如直接回对话
2. 页内只放「题库样例」和「Band 7 目标样例」，**针对学生的批改只从信箱来**——页内任何内容都不许冒充批改结果
3. 批改**以第二遍为准**（第一遍→第二遍之间只有自评清单，没有 AI 参与，对第一遍的详细反馈是马后炮）；第一遍数据仍收集，用于内部对比哪些错学生自己消灭了、哪些是顽固问题，在【点评】里带一句

## 一、生成一讲练习页

### 第 0 步：先列清单让用户选

用户通常不知道有哪些讲、哪些已生成。触发生成时**必须先列清单**，不要凭空猜测讲次：

1. 扫描 `~/Desktop/English Writing/speaking/` 下已有的 `NN-*.html`（index.html 除外）
2. 与全集对照（读 `index.html` 的讲次卡片，或课程系统 `course-edit_read`），输出「已生成 / 待生成」两栏清单，让用户挑
3. 用户只说「下一讲」时，取已生成讲次的最大号 +1

### 数据来源（按优先级）
1. **课程系统题库**：`course-edit_read` 读对应课节（如「雅思口语 2026年9-12月题库」course-20260822-d54mga），每个 activity 的 step content 里有 `instruction`（含题目与参考范文）、`reference`（Band 7 润色版）、`hints`
2. 用户直接给的题目/范文
3. PDF 题库（analyze-material 解析）

### 步骤

1. 复制 `assets/template.html` 到 `~/Desktop/English Writing/speaking/NN-slug.html`（NN=两位讲次号，如 `02-tidiness.html`）
2. 替换 6 个占位符：
   - `<title>` 与 `<h1>` 里的 `__LESSON_TITLE__`（如 `Part 1 · Tidiness 整洁`）
   - `__LESSON_ID__`：`L{NN}-{slug}`（如 `L02-tidiness`），必须全系列唯一——它是 localStorage key 和信箱路由的派生源
   - `__COURSE_LINE__` / `__LESSON_NO__` / `__TOTAL_LESSONS__`
   - `__QUESTIONS_JSON__`：题库数组（schema 见下），用 `json.dumps(questions, ensure_ascii=False, indent=2)` 生成后嵌入
3. 确保信箱服务在跑（见下），`open` 页面交付
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
- `python3 -m http.server 8741 --directory <speaking目录>` 起静态服务，playwright **DOM 断言**（别只看截图——脚本死没死肉眼看不出）：`#flowbar .dot` 数量 === 题数、`#first-0` 存在、console error / pageerror 为 0（favicon 404 豁免）。教训：02-tidiness 曾因 `.sub` 缺 `id="submeta"`，脚本在 `render()` 前 null 赋值抛错、整页空白，而静态标题看着一切正常
- 若信箱在跑，确认 fb-zone 显示「🤖 交 AI 批改本题」而非手动模式

## 二、信箱服务（launchd 常驻）

- 脚本：`~/Desktop/English Writing/speaking/mailbox.py`（skill 的 `assets/mailbox.py` 是母本；目录里没有就拷一份过去。**改了母本后同样要拷过去并重启 launchd 才生效**，流程见下）
- **已装 LaunchAgent**：`~/Library/LaunchAgents/com.fangyiwan.english-speaking-mailbox.plist`——开机自启 + KeepAlive 崩溃自动拉起，**正常情况下永远在线，没有手动模式**（页面离线时只显示恢复指引 + 重试按钮）
- 协议：`GET /ping`、`POST /submit`（网页提交作答）、`GET /feedback?ts=`（网页轮询批改）、`POST /grade`（agent 批改写回：追加 feedbacks + 按 ts 删本次处理的 submissions，全部在服务器进程内串行完成——**agent 永远不要直接改写 mailbox.json**，与服务器并发整读整写会互相覆盖、静默丢提交）
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
2. 逐题批改，格式见 `references/grading.md`（**必须先读它**）——三段式【点评】【你的润色版】【亮点】，语音识别同音误差先还原
3. 批改写回：**必须走 `POST /grade`**（读 mailbox.json 只读无害，写回绝不直接改文件）。`/grade` 在服务器进程内一次完成「追加 feedbacks（服务器自动盖当前时间戳，天然大于网页水位）+ 按 `ts` 删掉本次已处理的 submissions」，不存在并发覆盖窗口
4. 回复用户「好了，网页上看」，并点出 1-2 个最值得注意的修正

写回脚本骨架：

```python
import json, urllib.request
payload = {"ts_done": [<本次已批 submissions 的 ts 原值列表>],
           "feedbacks": [{"lesson": "L02-tidiness", "qi": 0, "text": "【点评】…"}]}
req = urllib.request.Request("http://127.0.0.1:8765/grade",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=5).read().decode())  # {"ok": true, "feedbacks": N, "submissions": M}
```

## 四、已知边界（用户问起时答）

- 语音识别（STT）用浏览器原生 API：Chrome 走 Google 服务需联网；Safari 14.1+ 可用。都不支持时按钮会提示，退化为打字
- 录音仅会话内存，刷新丢失（答案文本和批改持久化在 localStorage）
- file:// 协议直接双击打开即可；信箱跨域由 CORS `*` 处理，并带 Origin 校验：curl（无 Origin）与 file:// 页面（`Origin: null`）放行，浏览器里其他网页一律 403——仅监听回环挡不住它们
- 批改只有一种获取方式：信箱直连。页面离线 = 异常状态（红色指引 + 重试按钮），不要建议手动复制粘贴——用户已明确否决手动模式
- 自评清单里的「高频复发」项源自该生写作批改记录（冠词、人称漂移、中式直译），口语批改中发现新顽固错误时应建议更新清单
