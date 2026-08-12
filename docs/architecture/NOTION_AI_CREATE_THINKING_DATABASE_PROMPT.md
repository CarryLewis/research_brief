# Notion AI Prompt — Create Thinking Database

Copy everything inside the box below into Notion AI (on a blank page or workspace).  
Goal: create the Thinking Database that Thinking Vault V1 syncs from.

Property **display names** must match exactly (English), unless you later change `thinking_vault.property_names` in the backend config.

---

## Prompt (copy from here)

```text
请帮我创建一个 Notion Database，用作个人思考库「Thinking Vault」。

要求如下，请严格按字段名与类型创建，不要擅自增加分类/标签体系。

# 目标
- Database 名称：Thinking
- 用途：捕捉、澄清、保存个人思考；之后会单向同步到 Obsidian 的 Thinking/ 文件夹
- 内容权威在「属性列」，不是页面正文
- 这是思考索引，不是知识分类系统

# 必须创建的属性（显示名必须完全一致）

1. Name — Title（标题；若默认标题不叫 Name，请改名为 Name）
2. Created — Created time
3. Updated — Last edited time
4. Status — Select
   选项仅这四个（不要更多）：
   - raw
   - developing
   - connected
   - folder  （Obsidian 真实目录；Related = 成员；其它属性/正文仅 Notion AI 用）
5. Raw Thought — Text / Rich text
   说明：保存用户原始表达；AI 永远不要用润色后的摘要覆盖它
6. Context — Text / Rich text
7. Observation — Text / Rich text
8. Interpretation — Text / Rich text
9. Uncertainty — Text / Rich text
10. Questions — Text / Rich text
11. Later Reflection — Text / Rich text
12. Tags — Multi-select（受控过滤标签；不要改成 Text / Relation）
    选项从现有词表起步，例如：
    medicine, ai, neuroscience, cardiology, neurology, technology,
    economics, biology, research, clinical, important, todo, review, stroke, ecg
    说明：同步到 Obsidian 页底 #tag；与 Context（[[wikilink]]）严格区分
13. Related Information — Relation
    - 允许关联本 Thinking 数据库中的其他条目
    - 如果工作区已有 Information / Library 类数据库，也允许关联那些页面
    - 不要做成 Rollup，不要用 Relation 代替 Tags

# 明确不要创建的属性
不要添加：
- Domain / Category / Subcategory / Topic / Subtopic
- Priority / Maturity / Knowledge type
- Workspace / Project / Concept
- 大量自由 Tags / 未受控标签体系
- 任何复杂工作流状态机（除了上面的 Status 四选项）

允许：一个受控 Multi-select「Tags」（过滤用）。不要发明 Domain/Topic 分类树。

# 视图
请至少提供一个默认 Table 视图，列顺序建议：
Name | Status | Raw Thought | Context | Tags | Observation | Interpretation | Uncertainty | Questions | Later Reflection | Related Information | Created | Updated

可再加一个 Board 视图，按 Status 分组（raw / developing / connected / folder）。

# 一条示例条目（用于验收字段）
请创建 1 条示例 page：
- Name: Dizziness is not Vertigo
- Status: developing
- Raw Thought: 今天夜班碰到一个患者，他一直说头晕，但是我感觉他根本不是我们说的 vertigo。
- Context: Neurology night shift；Clinical communication
- Tags: medicine, neurology, clinical
- Observation: 患者反复使用「头晕」描述症状
- Interpretation: 患者的「头晕」可能不等于临床分类上的 vertigo
- Uncertainty: 尚未区分是前庭性、非前庭性，还是语言习惯问题
- Questions:
  - 患者具体是旋转感还是头重脚轻？
  - 临床沟通中「头晕」如何被误分类？
- Later Reflection: （留空）
- Related Information: （暂不关联）

# 完成后请告诉我
1. Database 已创建，并列出所有属性名与类型
2. 如何复制 database id（URL 中那串 id）以便配置同步
3. 提醒：属性列保存结构化短字段；更细致的反思写在页面正文（会同步为 Obsidian ## Extended Reflection）
4. 提醒：Tags → Obsidian 页底 #tag；Context → ## Context 的 [[wikilink]]；两者不要混用
5. 提醒：之后和 Notion AI 对话可以先澄清，但要同步的内容必须写入属性列和/或页面正文
```

---

## After Notion AI finishes

1. Share the database with your Notion integration (for API sync).
2. Put the database id into `.env` as `NOTION_THINKING_DATABASE_ID`.
3. Put the integration secret into `.env` as `NOTION_TOKEN`.
4. Run: `python -m app.cli.thinking_sync --vault <path>`

See also: [NOTION_THINKING_DATABASE_CHECKLIST.md](NOTION_THINKING_DATABASE_CHECKLIST.md)
