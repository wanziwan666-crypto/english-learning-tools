# 文档题库 → 练习页（用户给 PDF/Word 时必读）

用户给出题库文档路径（pdf/docx/doc/rtf/html/txt/md）要求出口语题/练习页时走本流程。产出目录、模板、验证、index 更新与课程系统路径**完全共用**（见 SKILL.md「一、生成一讲练习页」），本流程只多三件事：机械抽取、拆题、对照讲次。多个文档逐个走 Step 1，汇总后一起进 Step 3。

## Step 1 · 机械抽取（ingest.py）

```bash
python3 <skill目录>/english-speaking/assets/ingest.py <文档路径>
```

- dump 默认落 `~/Desktop/English Writing/speaking/sources/<原文件名>.txt`——**溯源**：以后核对任何一题都要能回到这份原文，别删
- 脚本 ❌（exit 1）时把 stderr 建议原样转述给用户，**禁止绕过闸门硬编题目**——扫描版被拒是特性不是 bug
- stderr 统计里英文词数异常低（如 < 200）时，先抽查 dump 头尾确认没提坏再继续

## Step 2 · 拆题（判断活）

读 dump 全文，**别假设结构**——PAGE 标记、编号、`You should say:`、中文小标题都只是常见信号，按手头文档的实际结构认边界：

- **Part 1 主题组**：一个主题下挂 4-6 个问答；题干**原文照抄不改写**（含拼写，题库原文即考点）
- **Part 2 cue card**：题干 + `You should say:` 的 3-4 个要点折进**一个** `q` 字符串——`You should say:` 前换 `\n`，每个要点行以 `• ` 开头（页面按多行渲染）。例：
  ```
  Describe a boring place you have visited.\nYou should say:\n• where it is\n• when you went there\n• what you did there\n• and explain why you found it boring
  ```
- **Part 3 延伸问**：跟在对应 Part 2 主题后，作为该讲的附加题（一讲里 cue card + Part 3 问混排没问题）
- 提取损伤（`pr oduced`、`th e` 这类明显断空格）顺手修复，但只修提取断裂，不改题目用词
- dump 很长（几十题）时按行号范围分给并行子代理拆，省主对话 context
- docx 表格题库若发现两题黏一行 = 走到了 textutil 兜底路径的信号，回头查原始 docx

## Step 3 · 对照讲次，列清单让用户选（第 0 步哲学的文档版）

1. 读 `~/Desktop/English Writing/speaking/index.html` 的讲次卡片，与文档主题模糊匹配：英文词干有实词重叠（`Singing`≈`sing`、`Parks and gardens`≈`park`）或中文标题相同即算命中
2. 输出三栏清单：
   - **已匹配**：给讲次号 NN，标注该讲当前是待生成还是已生成
   - **文档多出**：index 没有的新主题 → 追加 30+ 新卡片（NN = 现有最大号 +1 递增，slug 按英文主题生成且不得与现有 `NN-*.html` 撞名）
   - **index 有但文档没有**：列出但不动
3. **已生成的讲要重新生成，必须先问用户**：题数变了 localStorage 进度会清零（`load()` 的 length 校验弃旧状态），数据损失不能默认做
4. 追加新卡片时 index.html 同步三处：对应 h2 段内追加卡片、该段头计数 +1、`.sub` 的「N 讲」总数。新讲按 Part 类型归段（Part 1 → 第一段；Part 2 → 「Part 2 · 长答案」段；纯 Part 3 主题才考虑新段）。讲数超过 29 后，顺手把已部署各页 `const TOTAL_LESSONS = 29;` 精确替换为新总数（每文件恰一处；01-singing 是旧模板无此行，跳过）

## Step 4 · 出题（QUESTIONS schema 见 SKILL.md，风格锚 = 01-singing / 02-tidiness 的真实 QUESTIONS）

- 通用：每讲 4-6 题（Part 2 讲 = 1 张 cue card + 文档里带的 0-3 个 Part 3 延伸问）；`hints` 2 条，**中文讲解内嵌英文表达**（照 01/02 真实写法：`"用 used to 表示过去的习惯"`）；`highlights` 2-4 个，子串必须在 band7 原文**精确出现**（渲染靠子串高亮，编造就静默丢高亮），中文注释一句话说清为什么值得学
- **文档只给题目、没范文**（最常见）：`sample` = AI 写的朴素合格线范文（Part 1 3-5 句）；`band7` = 同意思润色升级版（句式/搭配升一档，个人细节保留）
- **文档带英文范文**：`sample` = 范文原文照抄（溯源，不许改写）；`band7` = 在其基础上的润色版（与课程系统 instruction/reference 映射同款）。范文是中文的 → 按无范文处理
- **Part 2 讲**：`__PART_LABEL__` 填 `Part 2`；`sample`/`band7` 为完整独白（band7 约 200-260 words，叙事结构：开场直入 → 展开细节 → 收尾感受）

## Step 5 · 生成与验证（复用主管线，注意三点）

1. 占位符 **7 个**（新增 `__PART_LABEL__`，Part 1 讲填 `"Part 1"`）；`__COURSE_LINE__` 文档来源填 `雅思口语题库 · <文档名>`
2. QUESTIONS 嵌入必须 `json.dumps(questions, ensure_ascii=False, indent=2).replace("</", "<\\/")`——`</` 转义防 `</script>` 提前闭合（题库范文里可能带 `</` 的概率不高，但转义零成本）
3. 每页生成后立即跑 playwright DOM 断言（dot 数=题数、`#first-0` 存在、console error/pageerror=0、`.qtag` 文本含 PART_LABEL）；**每完成一讲就更新一次 index.html**——半途失败也不丢已完成进度

## 已知边界（用户问起时答）

- 扫描版 PDF / 图片型文档被闸门拒绝：转文字版、另存 docx、或直接粘贴文本
- 纯中文题库可出题，但 sample/band7 由 AI 撰写
- `.pages`/`.pptx` 不支持（导出 docx/PDF 后再给）
- 页内自评清单文案（「给了 1 个理由或例子」等）偏 Part 1 语境，Part 2 讲照常显示，属可接受的近似
