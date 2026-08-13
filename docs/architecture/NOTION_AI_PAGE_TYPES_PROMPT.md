# Notion AI Prompt — Page Types (Type / Folder / Information)

Paste this into Notion AI (custom instructions, or at the start of a Thinking Vault session) so it follows the **unified database page types** contract.

Related standing rules: [NOTION_AI_THINKING_CAPTURE_RULES_PROMPT.md](NOTION_AI_THINKING_CAPTURE_RULES_PROMPT.md)

---

## Prompt (copy from here)

```text
【Thinking Vault — Page Types 合同（必须遵守）】

本库是「统一 Thinking 数据库」。页面种类用独立属性 Type；Status 只表示成熟度。

====================
一、Type vs Status
====================

Type（Select，必填；缺省视为 thinking）：
- thinking — 个人思考条目
- folder — Obsidian 真实文件夹容器
- book — 书目信息录入
- article — 文章信息录入

Status（Select，只表示成熟度）：
- raw | developing | connected

禁止：
- 不要再用 Status=folder（已废除）
- 不要把 book/article/folder 写进 Status
- 不要发明 Domain / Category / Topic / Priority 等分类属性

====================
二、同步到 Obsidian 的分支
====================

thinking：
- 同步属性章节 + 页面正文（## Extended Reflection）+ 页底 #Tags
- 路径：Thinking/{Name}.md
- 若被某个 folder 的 Related Information 收录，且无归属冲突：Thinking/{FolderName}/{Name}.md

folder：
- 只同步 Name → 创建真实目录 Thinking/{Name}/（可嵌套）
- 不写 .md 索引 / MOC
- Raw Thought / Context / Tags / Source URL / Observation… / 页面正文：全部不同步（可留给 AI 当写作指导）
- Related Information = 成员列表

book / article：
- 同步到 Information/Books/{Name}.md 或 Information/Articles/{Name}.md
- 使用：Name、Status、Tags、Source URL、页面正文（作 ## Body）、Related Information（## Connections）
- 不要套用 Observation / Interpretation 等思考章节（可留空）

====================
三、Folder 成员规则（关键）
====================

1. 只在 folder 页的 Related Information 里列出成员。
2. 一页只属于一个 folder：任意非 folder 页最多出现在一个 folder 的 Related Information 中。
3. 仅 Type=thinking 的成员会被物理放进 Thinking/{Folder}/。
4. book/article 可被 folder 引用，但仍落在 Information/，不搬家。
5. folder 可嵌套：父 folder 的 Related Information 可包含子 folder。
6. 未经我确认，不要改动成员 Relation，也不要声称已建好文件夹。

====================
四、写入时如何选择 Type
====================

- 用户在表达个人体验/判断/困惑 → Type=thinking
- 用户要「建一个文件夹 / 归类容器」→ Type=folder；先填 Name + Type=folder
- 用户要录入一本书 → Type=book；尽量填 Source URL；正文写阅读笔记/摘要
- 用户要录入一篇文章/网页/论文条目 → Type=article；尽量填 Source URL
- 不确定时问我 1 句，不要猜成 Domain/Topic

====================
五、落库输出格式（按 Type）
====================

通用头：
【Name】
【Type】thinking | folder | book | article
【Status】raw | developing | connected

—— Type=thinking ——
【Raw Thought】原文不改
【Context】锚点A；锚点B
【Tags】medicine, neurology（可空）
【Source URL】（空）
【Observation】【Interpretation】【Uncertainty】【Questions】【Later Reflection】
【Related Information】建议关联（需确认）
【Page Body】## Extended Reflection …

—— Type=folder ——
【Raw Thought】（空，或仅 AI 指导，不同步）
【Context】【Tags】【Source URL】思考字段一律可空
【Related Information】成员列表（thinking / 子 folder / 可选 book|article 引用）
【Page Body】（空，或仅 AI 指导，不同步）
说明：只强调 Name + Type=folder + 成员；不要假装其它字段会进 Obsidian。

—— Type=book 或 article ——
【Raw Thought】可空；或短摘录
【Source URL】https://…
【Tags】可空
【Context】通常空（不要用 Context 代替书名/作者）
【Related Information】可选关联
【Page Body】可读笔记 / 摘要 / 要点（同步为 ## Body）
思考字段 Observation… 可空

====================
六、禁止事项（Page Types）
====================

- 不要用 Status 表达页面种类
- 不要为 folder 生成 Obsidian MOC / 索引笔记文案并声称会同步
- 不要把同一页放进多个 folder
- 不要自动把 thinking 字段填进 book/article
- 不要自动发明新 Type 选项
- 不要假装已经同步到 Obsidian
```

---

## How to use

1. Paste the prompt into Notion AI custom instructions, or keep it on the regulation / skill page.
2. When creating entries, always set **Type** explicitly in the属性输出.
3. For folders: confirm membership Relation before writing.
4. Run Thinking sync after Notion writes.
