# Quartz → Cloudflare Pages（Obsidian 公开花园）

把仓库里的 `vault/` 用 [Quartz 4](https://quartz.jzhao.xyz/) 建成静态站，部署到你已有的 **Cloudflare** 域名。

站点代码在 [`site/`](../../site/)。构建时会从 `vault/` 同步内容（排除 `Archive/`、`90_Meta/`、`.obsidian/`）。

---

## 0. 改域名（必做）

编辑 [`site/quartz.config.ts`](../../site/quartz.config.ts)，把：

```ts
baseUrl: ... "example.com"
```

改成你的域名（**不要**写 `https://`，**不要**末尾 `/`），例如：

```ts
baseUrl: "notes.yourdomain.com"
```

或在 Cloudflare Pages 构建环境变量里设置：

```text
QUARTZ_BASE_URL=notes.yourdomain.com
NODE_VERSION=22
```

---

## 1. 本地预览（可选）

```bash
cd site
npm ci
npm run build:serve
# 浏览器打开终端提示的本地地址
```

`npm run build` = 同步 vault → `content/` + `npx quartz build` → 输出 `site/public/`。

---

## 2. Cloudflare Pages 连接 GitHub（推荐）

1. 打开 [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. 选择仓库 `CarryLewis/research_brief`（或你的 fork）
3. 构建配置：

| 项 | 值 |
|----|-----|
| Production branch | 你的默认分支（如 `main`；合并本 PR 之后） |
| Root directory | `site` |
| Framework preset | None |
| Build command | `npm ci && npm run build` |
| Build output directory | `public` |

4. Environment variables：

| Name | Value |
|------|--------|
| `NODE_VERSION` | `22` |
| `QUARTZ_BASE_URL` | 你的域名，如 `notes.yourdomain.com` |

5. **Save and Deploy**，等首次构建完成，会得到 `*.pages.dev` 预览域名。

---

## 3. 绑定你已有的 Cloudflare 域名

1. Pages 项目 → **Custom domains** → **Set up a custom domain**
2. 输入你的域名或子域名（如 `notes.yourdomain.com`）
3. 按提示完成 DNS（域名已在 Cloudflare 时通常自动加 CNAME）
4. SSL 保持 **Full (strict)**

之后：每次 push 到 Production branch（以及 Thinking sync commit 进 `vault/`）都会触发重新构建。

---

## 4. 和 Thinking 定时同步的关系

现有 [`.github/workflows/thinking-sync.yml`](../../.github/workflows/thinking-sync.yml) 会把 Notion 同步进 `vault/` 并 commit。

合并顺序建议：

1. 先让 Thinking sync + Quartz 代码都进默认分支  
2. 配置 Cloudflare Pages  
3. 配置 Notion secrets，跑一次 sync → vault 更新 → Pages 自动重建站点  

若 Pages 只盯 `main`，请把相关 PR 合进 `main` 后再测。

---

## 5. 公开范围

默认**不发布**：

- `vault/Archive/`
- `vault/90_Meta/`
- `.obsidian/`
- `.thinking-folder` sidecar

要改公开范围：编辑 [`site/scripts/sync-content.sh`](../../site/scripts/sync-content.sh) 的 `rsync --exclude`，以及 `quartz.config.ts` 的 `ignorePatterns`。

笔记可用 frontmatter `draft: true`（Quartz `RemoveDrafts`）临时不下线内容。

---

## 6. 故障排查

| 现象 | 处理 |
|------|------|
| 构建找不到 content | 确认 Root directory=`site`，且仓库里有 `vault/` |
| 样式/链接指向错误域名 | 检查 `QUARTZ_BASE_URL` / `baseUrl` |
| Node 版本错 | 设 `NODE_VERSION=22` |
| 想排除更多目录 | 改 `sync-content.sh` excludes |
| 图谱/反链没有 | 确认笔记里用了 `[[wikilinks]]` 且被同步进 content |
