# Research Brief — Browser Extension (Chrome / Edge MV3)

One-click **Save to Library**: captures the current page (Readability when possible) and posts it to the local API → Obsidian `Library/Articles/`.

## Install (unpacked)

1. Start the API:

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000
```

(From repo root: `uvicorn app.main:app --app-dir backend --port 8000`.)

2. Optional: set `LIBRARY_API_TOKEN` in `.env` (and the same value in extension options).

3. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select this `extension/` folder.

4. Open extension **Options**: confirm API base URL (`http://127.0.0.1:8000`) and token. Use **Test connection**.

## Use

- Click the toolbar icon on an article page, **or**
- Right-click → **Save to Library**

Success / failure shows as a system notification (and a short badge on the icon).

## Permissions

| Permission | Why |
|------------|-----|
| `activeTab` / `scripting` | Read current page HTML |
| `storage` | API URL + token |
| `contextMenus` | Right-click save |
| `notifications` | Toast feedback |
| host `127.0.0.1:8000` / `localhost:8000` | Call local API |

## Notes

- Prefer saving from a page you can already see (logged-in / paywalled content). Server URL-only fetch is a weaker fallback.
- Images download into `Library/Attachments/{id}/` when the option is enabled.
- Safari is out of scope for v1.
