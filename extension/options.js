const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  apiToken: "",
  downloadImages: true,
};

const form = document.getElementById("settings-form");
const statusEl = document.getElementById("status");
const testBtn = document.getElementById("test-btn");

async function load() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  document.getElementById("apiBaseUrl").value = stored.apiBaseUrl || DEFAULTS.apiBaseUrl;
  document.getElementById("apiToken").value = stored.apiToken || "";
  document.getElementById("downloadImages").checked = stored.downloadImages !== false;
}

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = kind || "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiBaseUrl = document.getElementById("apiBaseUrl").value.trim().replace(/\/$/, "");
  const apiToken = document.getElementById("apiToken").value.trim();
  const downloadImages = document.getElementById("downloadImages").checked;
  await chrome.storage.sync.set({ apiBaseUrl, apiToken, downloadImages });
  setStatus("Settings saved.", "ok");
});

testBtn.addEventListener("click", async () => {
  const apiBaseUrl = document.getElementById("apiBaseUrl").value.trim().replace(/\/$/, "");
  setStatus("Checking…");
  try {
    const resp = await fetch(`${apiBaseUrl}/api/health`);
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const auth = data.library_auth_required ? "token required" : "token optional";
    setStatus(`OK — ${data.mode || "api"} (${auth})`, "ok");
  } catch (err) {
    setStatus(
      "Cannot reach API. Start uvicorn on this base URL.",
      "bad"
    );
    console.error(err);
  }
});

load();
