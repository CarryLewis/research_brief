# Notion AI Prompt — Context as Obsidian Wikilink Vocabulary

`Context` is not free prose. It is a **small set of reusable thinking anchors** that sync into Obsidian as Wikilinks:

```text
[[Clinical communication]]; [[Vestibular language]]; [[Night shift observation]]
```

Sync rule: terms separated by `;` / `；` become `[[term]]` under `## Context`.

Paste the prompt below into Notion AI standing instructions (or use together with the main capture rules).

---

## Prompt (copy from here)

```text
【Context 字段专项规则】

Context 不是场景描写句，而是会同步成 Obsidian Wikilink 的「思考锚点词」。
同步后形态：
[[锚点A]]; [[锚点B]]; [[锚点C]]

你在填写【Context】时，必须遵守下面四条：

1) 概括性（能打开一整块思考）
- 每个词条应能唤起「一整块主题/板块」，而不是只描述当下细节。
- 好：Clinical communication / Patient language of dizziness / Night shift clinical reasoning
- 差：这个病人说头晕 / 今晚三点的事 / 我觉得奇怪

2) 标题一致性（与既有领域用语对齐）
- 优先复用我过去已经用过的、同领域的标题/锚点，不要每次换新说法。
- 若已有接近标题，沿用原词，不要近义改写造成图上分裂。
- 只有确实是新板块时，才提出新锚点，并保持可长期复用。

3) 少量词汇覆盖一个思考点的方方面面
- 每个锚点用 2–6 个词（中文可 4–12 字）压成一个可复用概念名。
- 一个锚点 = 一个可反复回来思考的节点，不是一句话解释。
- 单次 Context 通常 1–3 个锚点，最多 4 个；宁少勿滥。

4) 分隔格式
- 多个 Context 之间只用分号断开：中文「；」或英文「;」
- 不要用逗号、顿号、换行列表作为主分隔
- 不要在 Context 里写 [[ ]]（系统同步时会自动加）
- 不要在 Context 里写解释性长句

【Context 输出格式】
【Context】
锚点A；锚点B；锚点C

【自检清单】写完 Context 后默默检查：
- 每个锚点是否足够概括，能打开一大块思考？
- 是否尽量复用旧标题，而不是新造近义词？
- 是否短、稳、可做笔记名？
- 是否用分号分隔，且数量克制？

【与其它字段分工】
- Context：可复用的主题锚点（未来会变成 [[wikilink]]）
- Observation / Interpretation：这一次的具体内容
- Page Body：更细致的反思展开
- Related Information：已确认关联的页面（Relation），不是 Context 的替代品

【示例】
用户想法：今天夜班病人一直说头晕，但我不认为是 vertigo。

好的 Context：
Patient language of dizziness；Clinical communication；Vestibular clinical categories

不好的 Context：
夜班时有个病人反复说头晕让我很困惑，可能不是眩晕
```

---

## Minimal add-on (if you only want a short insert)

```text
Context 规则：写成 1–3 个可复用思考锚点；要概括、与旧标题一致、短词可覆盖整块主题；多项用「；」分隔；不要写长句；系统会同步成 [[锚点]]。
```
