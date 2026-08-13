# Quartz site (Obsidian garden)

Public static site generated from repo [`vault/`](../vault/) with [Quartz 4](https://quartz.jzhao.xyz/).

## Commands

```bash
npm ci
npm run build        # sync vault → content/ + build → public/
npm run build:serve  # local preview
```

## Deploy

See [`docs/architecture/QUARTZ_CLOUDFLARE_DEPLOY.md`](../docs/architecture/QUARTZ_CLOUDFLARE_DEPLOY.md).

Set `QUARTZ_BASE_URL` (or edit `quartz.config.ts`) to your Cloudflare custom domain before going live.
