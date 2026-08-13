# Notion AI Prompt — Page Types (Type / Folder)

Paste this into Notion AI so it follows the **Type vs Status** contract used by GitHub Actions sync.

Related: [NOTION_AI_THINKING_CAPTURE_RULES_PROMPT.md](NOTION_AI_THINKING_CAPTURE_RULES_PROMPT.md)

---

## Prompt (copy from here)

```text
【Thinking Vault — Page Types 合同】

Type（Select，必填；缺省视为 thinking）：
- thinking — 个人思考条目 → vault/Thinking/{Name}.md
- folder — Obsidian 真实文件夹 → vault/Thinking/{Name}/（无 .md 索引）
- book / article — 可标记，当前同步运行时跳过（不写 Information/）

Status（Select，只表示成熟度）：
- raw | developing | connected

禁止再用 Status=folder（已废除；若仍出现会按 Type=folder 兼容）。

folder：
- Related Information = 成员列表
- 一页最多属于一个 folder；冲突则留在 Thinking/ 根目录并告警
- 仅 Type=thinking 的成员会物理放进文件夹
- 可嵌套：父 folder 的 Related 可包含子 folder
- 其它属性 / 页面正文不同步

thinking：
- 同步属性章节 + 页面正文（## Extended Reflection）+ 页底 #Tags
- 若被唯一 folder 收录：Thinking/{FolderName}/{Name}.md
```
