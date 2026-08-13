# 完整指南：快捷指令每天 06:00 同步 Notion → Obsidian

## 0. 脚本如何分工（先理解再搭）

```text
┌─────────────────────────────────────────────────────────────┐
│ 触发层（二选一）                                              │
│  • Apple 快捷指令「自动化：每天 06:00」                         │
│  • 或 LaunchAgent StartCalendarInterval 06:00                 │
└───────────────────────────┬─────────────────────────────────┘
                            │ 调用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 入口脚本（很薄）                                              │
│  scripts/macos/run-thinking-sync.command                      │
│  或快捷指令里直接写的几行 bash                                 │
│  作用：设好 OBSIDIAN_VAULT，再调用主脚本                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────�脚本                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 主脚本                                                        │
│  scripts/sync-to-local-obsidian.sh                            │
│  • 读 ~/Documents/research_brief/.env（NOTION_TOKEN 等）       │
│  • 检测 Clash 7890（有则走代理）                               │
│  • 用仓库 .venv 跑 python -m app.cli.thinking_sync            │
│  • 写入 iCloud Obsidian 的 Thinking/                          │
│  • 日志：~/Library/Logs/thinking-vault-sync.log               │
└─────────────────────────────────────────────────────────────┘
```

**你不需要在快捷指令里重写同步逻辑。**  
快捷指令只负责：**到点 → 跑主脚本**。

| 文件 | 角色 |
|------|------|
| `~/Documents/research_brief/.env` | 密钥（token、database id），永不提交 Git |
| `scripts/sync-to-local-obsidian.sh` | 真正同步 |
| `scripts/macos/run-thinking-sync.command` | 双击/快捷指令友好包装 |
| 快捷指令「Thinking Vault 同步」 | 手动点一次 / 被自动化调用 |
| 自动化「每天 06:00」 | 闹钟式触发 |

---

## 1. 一次性前置条件（终端）

```bash
# 1) 仓库与脚本
cd ~/Documents/research_brief
git -c http.version=HTTP/1.1 pull
chmod +x scripts/sync-to-local-obsidian.sh scripts/macos/run-thinking-sync.command

# 2) .env（若已有可跳过）
cat > ~/Documents/research_brief/.env <<'EOF'
NOTION_TOKEN=ntn_你的token
NOTION_THINKING_DATABASE_ID=51e7fdfd-46f8-4d85-a813-f68b56131615
EOF

# 3) 关掉旧的「每 15 分钟」任务（避免打架）
launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync.plist

# 4) 手动验证主脚本一次
export OBSIDIAN_VAULT="/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents"
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
tail -30 ~/Library/Logs/thinking-vault-sync.log
```

日志里应出现 `OK: Notion synced into .../Thinking`。  
**主脚本不通时，先不要做快捷指令。**

---

## 2. 搭建快捷指令本体

### 2.1 打开 App

1. 打开 macOS **快捷指令**（Spotlight 搜「快捷指令」或 Shortcuts）  
2. 左侧选 **所有快捷指令**  
3. 右上角 **+**

### 2.2 命名

标题改为：`Thinking Vault 同步`

### 2.3 添加「运行 Shell 脚本」

1. 右侧搜索栏搜：`运行 Shell 脚本` 或 `Run Shell Script`  
2. 点选加入画布  
3. 若提示需开启「允许运行脚本」：  
   - 快捷指令 → 设置（或 系统设置 → 隐私）→ 打开 **允许运行脚本**

### 2.4 粘贴脚本（推荐完整版）

在 Shell 脚本框中**全部替换为**：

```bash
#!/bin/bash
set -euo pipefail

export RESEARCH_BRIEF_REPO="/Users/carrylewis/Documents/research_brief"
export OBSIDIAN_VAULT="/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents"

# 可选：若 Clash 固定 7890，主脚本会自动检测；此处无需再 export 代理
LOG="$HOME/Library/Logs/thinking-vault-sync.shortcuts.log"
echo "==== Shortcuts trigger $(date) ====" >>"$LOG"

/bin/bash "$RESEARCH_BRIEF_REPO/scripts/sync-to-local-obsidian.sh"
rc=$?
echo "exit=$rc at $(date)" >>"$LOG"
exit $rc
```

设置建议：

| 项 | 值 |
|----|-----|
| Shell | `/bin/bash` |
| 输入 | `传递到 stdin`（默认即可） |
| 输入为 | 不重要（本脚本不读 stdin） |

### 2.5 简化版（二选一）

若你更想极简，可只写：

```bash
/Users/carrylewis/Documents/research_brief/scripts/macos/run-thinking-sync.command
```

### 2.6 首次手动运行

1. 在快捷指令编辑页点 **▶ 运行**  
2. 允许：访问文稿 / 网络 / 自动化（按系统弹窗全部允许）  
3. 看结果无报错后，再查日志：

```bash
tail -40 ~/Library/Logs/thinking-vault-sync.log
```

---

## 3. 做成「每天早上 6:00」自动化

1. 快捷指令 App 顶部切换到 **自动化**  
2. 点 **+** → **新建个人自动化**（New Personal Automation）  
3. 选择 **一天中的时间**（Time of Day）  
4. 配置：  
   - 时间：**06:00**  
   - 重复：**每天**（Daily）  
   - （可选）日出/日落不要选，用固定时间  
5. **下一步**  
6. 添加操作：搜 **运行快捷指令** → 选择 **Thinking Vault 同步**  
   - 或直接「执行快捷指令」指向同名项  
7. **下一步**  
8. **关闭「运行前询问」**（Ask Before Running）——非常关键  
   - 开着的话每天都会弹窗，不点就不跑  
9. macOS 较新版本若有 **「即时运行」**：打开它  
10. **完成**

---

## 4. 权限清单（第一次必查）

| 位置 | 做什么 |
|------|--------|
| 快捷指令 App 设置 | 允许运行脚本 |
| 系统设置 → 隐私与安全性 → **自动化** | 允许「快捷指令」控制相关 App（若弹出） |
| 系统设置 → 隐私与安全性 → **完全磁盘访问权限** | 若写 iCloud Obsidian 失败，给「快捷指令」勾选 |
| 系统设置 → 隐私与安全性 → **文件与文件夹** | 确保能访问文稿 / iCloud Drive |

---

## 5. 如何验收

### 立刻测快捷指令

在快捷指令里点 ▶，然后：

```bash
tail -40 ~/Library/Logs/thinking-vault-sync.log
ls -lt "/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thinking" | head
```

### 测 6:00 自动化（不必真等到明天）

临时把自动化时间改成 **当前时间 + 2 分钟**，等它跑完再改回 06:00。

### 成功信号

- 日志有 `OK: Notion synced into ...`  
- Obsidian `Thinking/` 下笔记 `updated` 日期或 `## Context` 有变化  

---

## 6. 睡眠与网络

| 情况 | 结果 |
|------|------|
| 6:00 Mac 清醒 | 准时跑 |
| 6:00 睡眠 | 常延后到唤醒；偶发跳过 |
| Notion 需代理且 Clash 未开 | 可能 SSL 失败（见日志） |

想更稳：合盖也尽量跑 → 用电源适配 + 系统设置里允许网络唤醒；或改用 LaunchAgent 每日任务（见下节）。

---

## 7. 备选：不用快捷指令 UI（LaunchAgent 每天 6:00）

与快捷指令**不要同时开**。

```bash
mkdir -p ~/Library/LaunchAgents
cp ~/Documents/research_brief/scripts/macos/com.carrylewis.thinking-vault-sync-daily.plist.example \
   ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync-daily.plist
launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync-daily 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync-daily.plist
```

---

## 8. 卸载 / 暂停

**只停快捷指令自动化：**  
自动化列表 → 该条 → 关闭开关，或删除。

**不停快捷指令、只停 LaunchAgent：**

```bash
launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync-daily 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync-daily.plist
```

手动同步永远可用：

```bash
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
```
