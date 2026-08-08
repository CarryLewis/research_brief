/**
 * Research Brief — Save to Library (MV3 service worker)
 *
 * Toolbar click / context menu → capture page HTML (Readability when possible)
 * → POST /api/library/save on the local API.
 */

const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  apiToken: "",
  downloadImages: true,
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "save-to-library",
      title: "Save to Library",
      contexts: ["page", "selection", "link"],
    });
  });
});

chrome.action.onClicked.addListener(async (tab) => {
  await saveActiveTab(tab);
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "save-to-library") {
    await saveActiveTab(tab);
  }
});

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return {
    apiBaseUrl: String(stored.apiBaseUrl || DEFAULTS.apiBaseUrl).replace(/\/$/, ""),
    apiToken: String(stored.apiToken || ""),
    downloadImages: stored.downloadImages !== false,
  };
}

async function saveActiveTab(tab) {
  if (!tab?.id) {
    notify("Save failed", "No active tab.");
    return;
  }
  if (!tab.url || !/^https?:/i.test(tab.url)) {
    notify("Save failed", "Only http(s) pages can be saved.");
    return;
  }

  const settings = await getSettings();
  setBadge(tab.id, "…", "#1a5f7a");

  try {
    const page = await capturePage(tab.id);
    if (!page?.html) {
      throw new Error("Could not capture page HTML");
    }

    const result = await postSave(settings, {
      url: page.url || tab.url,
      title: page.title || tab.title || "",
      html: page.html,
      download_images: settings.downloadImages,
      on_duplicate: "update",
    });

    const verb = result.skipped ? "Already saved" : result.updated ? "Updated" : "Saved";
    notify(verb, result.title || "Library note written");
    setBadge(tab.id, "✓", "#2d6a4f");
  } catch (err) {
    const message = friendlyError(err);
    notify("Save failed", message);
    setBadge(tab.id, "!", "#9b2226");
    console.error("[research-brief]", err);
  } finally {
    setTimeout(() => clearBadge(tab.id), 2500);
  }
}

async function capturePage(tabId) {
  // Inject Mozilla Readability, then extract cleaned article HTML (fallback: full DOM).
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["lib/Readability.js"],
    });
  } catch (err) {
    console.warn("[research-brief] Readability inject failed; using full DOM", err);
  }

  const [{ result } = {}] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const url = location.href;
      let title = document.title || "";
      let html = document.documentElement.outerHTML;
      let usedReadability = false;

      try {
        if (typeof Readability === "function") {
          const clone = document.cloneNode(true);
          const article = new Readability(clone).parse();
          if (article?.content) {
            const safeTitle = article.title || title;
            title = safeTitle;
            html =
              "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>" +
              "<title>" +
              escapeHtml(safeTitle) +
              "</title></head><body>" +
              article.content +
              "</body></html>";
            usedReadability = true;
          }
        }
      } catch (_e) {
        // keep full DOM
      }

      return { url, title, html, usedReadability };

      function escapeHtml(s) {
        return String(s)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      }
    },
  });

  return result;
}

async function postSave(settings, body) {
  const endpoint = `${settings.apiBaseUrl}/api/library/save`;
  const headers = { "Content-Type": "application/json" };
  if (settings.apiToken) {
    headers.Authorization = `Bearer ${settings.apiToken}`;
  }

  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (err) {
    const e = new Error("API unreachable — is uvicorn running on " + settings.apiBaseUrl + "?");
    e.cause = err;
    e.code = "NETWORK";
    throw e;
  }

  let data = null;
  const text = await response.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_e) {
    data = { detail: text };
  }

  if (!response.ok) {
    const detail =
      (data && (data.detail || data.message)) ||
      `HTTP ${response.status}`;
    const e = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    e.code = response.status === 401 ? "AUTH" : "HTTP";
    e.status = response.status;
    throw e;
  }

  return data;
}

function friendlyError(err) {
  const msg = String(err?.message || err || "Unknown error");
  if (err?.code === "NETWORK" || /Failed to fetch|NetworkError|API unreachable/i.test(msg)) {
    return "API not running. Start: uvicorn app.main:app --app-dir backend --port 8000";
  }
  if (err?.code === "AUTH" || /token|401|Unauthorized/i.test(msg)) {
    return "Auth failed — check LIBRARY_API_TOKEN in extension options.";
  }
  return msg.slice(0, 180);
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: `Research Brief: ${title}`,
    message: String(message || "").slice(0, 250),
    priority: 1,
  });
}

function setBadge(tabId, text, color) {
  chrome.action.setBadgeText({ tabId, text });
  chrome.action.setBadgeBackgroundColor({ tabId, color });
}

function clearBadge(tabId) {
  chrome.action.setBadgeText({ tabId, text: "" });
}
