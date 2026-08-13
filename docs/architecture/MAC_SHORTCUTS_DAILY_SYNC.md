# 每天早上 6:00 自动同步（快捷指令 / LaunchAgent）

目标：退出原来的「每 15 分钟」任务后，改为 **每天 06:00** 把 Notion Thinking 同步到 iCloud Obsidian。

底层仍调用：

```bash
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
```

---

## 方案 A — Apple 快捷指令（按你的要求）

### 1. 先保证手动同步可用

```bash
~/Documents/research_brief/scripts/sync-to-local-obsidian.sh
tail -20 ~/Library/Logs/thinking-vault-sync.log
```

### 2. 新建快捷指令

1. 打开 **快捷指令** App  
2. 点 **+** → 命名为 `Thinking Vault 同步`  
3. 添加操作：**运行 Shell 脚本**（Run Shell Script）  
4. 脚本内容填：

```bash
export OBSIDIAN_VAULT="/Users/carrylewis/Library/Mobile Documents/iCloud~md~obsidian/Documents"
/Users/carrylewis/Documents/research_brief/scripts/sync-to-local-obsidian.sh
```

5. Shell：`/bin/bash`；输入：`to stdin` 可不管  
6. 保存  

首次运行若提示权限：允许 **运行脚本**、访问文件/网络。

也可改为运行：

```bash
open "/Users/carrylewis/Documents/research_brief/scripts/macos/run-thinking-sync.command"
```

### 3. 做成每天 6:00 的自动化

1. 快捷指令 App → 顶部 **自动化**（Automation）  
2. **+** → **个人自动化**  
3. 选择 **一天中的时间**（Time of Day）  
4. 时间设为 **06:00**，重复 **每天**  
5. 下一步 → 选择快捷指令 **Thinking Vault 同步**  
6. **关闭**「运行前询问」（Ask Before Running）——否则不会静默执行  
7. 完成  

### 4. 注意

- Mac 在 6:00 **睡着**时，快捷指令常会等到唤醒后才跑（或错过）。  
- 系统设置 → 隐私与安全性 → 自动化 / 完全磁盘访问：必要时给「快捷指令」权限。  
- 若不稳定，改用下面的方案 B。

---

## 方案 B — 每天 6:00 LaunchAgent（更稳，推荐）

不依赖快捷指令 UI，同样是每天 6 点跑同一脚本：

```bash
# 关掉旧的 15 分钟任务
launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync.plist

# 安装每日 6:00
cd ~/Documents/research_brief && git pull
chmod +x scripts/sync-to-local-obsidian.sh scripts/macos/run-thinking-sync.command
mkdir -p ~/Library/LaunchAgents
cp scripts/macos/com.carrylewis.thinking-vault-sync-daily.plist.example \
   ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync-daily.plist

launchctl bootout gui/$(id -u)/com.carrylewis.thinking-vault-sync-daily 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.carrylewis.thinking-vault-sync-daily.plist
```

查看是否已加载：

```bash
launchctl print gui/$(id -u)/com.carrylewis.thinking-vault-sync-daily 2>&1 | head -20
```

日志：`~/Library/Logs/thinking-vault-sync.log`

---

## 两种方案可并存吗？

可以，但不建议：会在 6:00 跑两次。选 **快捷指令** 或 **LaunchAgent 每日** 其一即可。
