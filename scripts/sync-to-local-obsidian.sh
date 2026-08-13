#!/usr/bin/env bash
# Notion Thinking DB → local Obsidian vault (direct).
#
# This does NOT go through GitHub. It calls the Thinking sync CLI and writes
# markdown into OBSIDIAN_VAULT/Thinking/.
#
# Required:
#   OBSIDIAN_VAULT  — Obsidian vault root (Manage vaults path)
#   NOTION_TOKEN + NOTION_THINKING_DATABASE_ID — via env or REPO/.env
#
# Optional:
#   RESEARCH_BRIEF_REPO — clone of this repo (code + .env + local SQLite)
#   PYTHON_BIN          — python interpreter (default: repo .venv or python3)
#   SYNC_LOG            — log file path

set -euo pipefail

REPO="${RESEARCH_BRIEF_REPO:-$HOME/Documents/research_brief}"
# Default = Obsidian Manage vaults path for “Thinking valut” (iCloud Documents root).
# Override with OBSIDIAN_VAULT if Manage vaults shows a different path.
VAULT="${OBSIDIAN_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  LOG="${SYNC_LOG:-$HOME/Library/Logs/thinking-vault-sync.log}"
else
  LOG="${SYNC_LOG:-$HOME/.cache/thinking-vault-sync.log}"
fi

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) Notion → Obsidian direct sync ===="

# Proxy policy:
# - If Clash/Surge local port is open, USE it (needed to reach Notion in many networks).
# - If not open, clear proxy env so a stale 127.0.0.1:7890 does not break SSL.
_proxy_host="${THINKING_PROXY_HOST:-127.0.0.1}"
_proxy_port="${THINKING_PROXY_PORT:-7890}"
_proxy_url=""
if command -v nc >/dev/null 2>&1 && nc -z -G 1 "$_proxy_host" "$_proxy_port" >/dev/null 2>&1; then
  _proxy_url="http://${_proxy_host}:${_proxy_port}"
elif command -v nc >/dev/null 2>&1 && nc -z -w 1 "$_proxy_host" "$_proxy_port" >/dev/null 2>&1; then
  _proxy_url="http://${_proxy_host}:${_proxy_port}"
fi
if [[ -n "$_proxy_url" ]]; then
  export http_proxy="$_proxy_url" https_proxy="$_proxy_url"
  export HTTP_PROXY="$_proxy_url" HTTPS_PROXY="$_proxy_url"
  export ALL_PROXY="$_proxy_url" all_proxy="$_proxy_url"
  echo "proxy=$_proxy_url (local agent detected)"
else
  export http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" ALL_PROXY="" all_proxy=""
  echo "proxy=(none) — no listener on ${_proxy_host}:${_proxy_port}"
fi

if [[ ! -d "$REPO/backend/app" ]]; then
  echo "ERROR: research_brief backend not found at: $REPO" >&2
  echo "Clone: git clone https://github.com/CarryLewis/research_brief.git \"$REPO\"" >&2
  exit 1
fi

if [[ ! -d "$VAULT" ]]; then
  echo "ERROR: Obsidian vault not found: $VAULT" >&2
  echo "Open Obsidian → Manage vaults and copy the exact path into OBSIDIAN_VAULT." >&2
  exit 1
fi

# Load secrets from repo .env (never commit this file)
ENV_FILE="${THINKING_ENV_FILE:-$REPO/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  echo "loaded_env=$ENV_FILE"
else
  echo "WARN: no $ENV_FILE — relying on already-exported env vars"
fi

if [[ -z "${NOTION_TOKEN:-}" || -z "${NOTION_THINKING_DATABASE_ID:-}" ]]; then
  echo "ERROR: NOTION_TOKEN and NOTION_THINKING_DATABASE_ID are required (put them in $ENV_FILE)" >&2
  exit 1
fi

# Local SQLite sync index (keep off iCloud when possible)
export DATA_DIR="${DATA_DIR:-$REPO/data}"
mkdir -p "$DATA_DIR"
export DEFAULT_VAULT_PATH="$VAULT"
export PYTHONPATH="$REPO/backend${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$REPO/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "ERROR: python3 not found" >&2
    exit 1
  fi
fi

# Ensure deps once (idempotent)
REQ="$REPO/backend/requirements.txt"
MARKER="$REPO/.venv/.thinking-sync-deps-ok"
if [[ ! -x "$REPO/.venv/bin/python" ]]; then
  echo "Creating venv at $REPO/.venv"
  "$PYTHON_BIN" -m venv "$REPO/.venv"
  PYTHON_BIN="$REPO/.venv/bin/python"
fi
if [[ ! -f "$MARKER" || "$REQ" -nt "$MARKER" ]]; then
  echo "Installing Python deps into .venv"
  "$REPO/.venv/bin/pip" install -q -r "$REQ"
  touch "$MARKER"
  PYTHON_BIN="$REPO/.venv/bin/python"
fi

echo "vault=$VAULT"
echo "python=$PYTHON_BIN"
echo "data_dir=$DATA_DIR"

set +e
"$PYTHON_BIN" -m app.cli.thinking_sync --vault "$VAULT"
sync_rc=$?
set -e

if [[ "$sync_rc" -ne 0 ]]; then
  echo "ERROR: thinking_sync exited with code $sync_rc"
  # One retry after short wait (transient SSL / proxy flaps)
  sleep 2
  if [[ -n "$_proxy_url" ]]; then
    echo "retry with proxy=$_proxy_url"
  else
    echo "retry without proxy"
  fi
  "$PYTHON_BIN" -m app.cli.thinking_sync --vault "$VAULT"
fi

echo "OK: Notion synced into $VAULT/Thinking"
echo
