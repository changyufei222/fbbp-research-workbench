#!/usr/bin/env bash

set -euo pipefail

if [[ -n "${FBBP_WORKSPACE_ROOT_B64:-}" ]]; then
  WORKSPACE_ROOT="$(printf '%s' "$FBBP_WORKSPACE_ROOT_B64" | base64 --decode)"
  SCRIPT_DIR="$WORKSPACE_ROOT/scripts"
elif [[ -n "${FBTP_WORKSPACE_ROOT_B64:-}" ]]; then
  WORKSPACE_ROOT="$(printf '%s' "$FBTP_WORKSPACE_ROOT_B64" | base64 --decode)"
  SCRIPT_DIR="$WORKSPACE_ROOT/scripts"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

if [[ -n "${FBBP_REPO_ROOT_B64:-}" ]]; then
  REPO_ROOT="$(printf '%s' "$FBBP_REPO_ROOT_B64" | base64 --decode)"
elif [[ -n "${FBTP_REPO_ROOT_B64:-}" ]]; then
  REPO_ROOT="$(printf '%s' "$FBTP_REPO_ROOT_B64" | base64 --decode)"
else
  REPO_ROOT="$(cd "$WORKSPACE_ROOT/.." && pwd)"
fi

if [[ -d "$REPO_ROOT/fbbp-mcp-rag-server" ]]; then
  MCP_ROOT="$REPO_ROOT/fbbp-mcp-rag-server"
else
  MCP_ROOT="$REPO_ROOT/fbtp-mcp-rag-server"
fi
RAGKB_ROOT="$REPO_ROOT/llm-rag-knowledge-base"
MODELS_ROOT="$REPO_ROOT/models"
RUNTIME_ROOT="${FBBP_WSL_RUNTIME_ROOT:-${FBTP_WSL_RUNTIME_ROOT:-/tmp/fbbp_http_mcp_runtime}}"

mkdir -p "$RUNTIME_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required inside WSL."
  exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
SITE_PACKAGES="$MCP_ROOT/.venv_wsl/lib/python${PYTHON_VERSION}/site-packages"
mkdir -p "$SITE_PACKAGES"

load_env_keys() {
  local file="$1"
  shift

  if [[ ! -f "$file" ]]; then
    return
  fi

  while IFS='=' read -r raw_key raw_value; do
    raw_key="${raw_key%%$'\r'}"
    raw_value="${raw_value%%$'\r'}"
    [[ -z "$raw_key" ]] && continue
    [[ "$raw_key" =~ ^[[:space:]]*# ]] && continue

    for wanted in "$@"; do
      if [[ "$raw_key" == "$wanted" ]]; then
        export "$raw_key=$raw_value"
        break
      fi
    done
  done <"$file"
}

export PYTHONPATH="$SITE_PACKAGES:$MCP_ROOT/src:$RAGKB_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

MISSING_MODULES="$("$PYTHON_BIN" - <<'PY'
import importlib.util

required = [
    "mcp",
    "langgraph",
    "langchain_postgres",
    "psycopg",
    "pgvector",
    "openai",
    "yaml",
    "docx",
    "FlagEmbedding",
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
print(" ".join(missing))
PY
)"

if [[ -n "$MISSING_MODULES" ]]; then
  "$PYTHON_BIN" -m pip install --upgrade pip --break-system-packages
  "$PYTHON_BIN" -m pip install --target "$SITE_PACKAGES" --break-system-packages \
    "mcp[cli]>=1.26.0" \
    langgraph \
    langchain-postgres \
    "psycopg[binary]" \
    pgvector \
    sqlalchemy \
    pydantic \
    python-docx \
    python-dotenv \
    pyyaml \
    openai \
    FlagEmbedding \
    "transformers<5" \
    fastapi \
    uvicorn \
    pandas \
    matplotlib \
    pypdf
fi

load_env_keys "$RAGKB_ROOT/.env" \
  OPENAI_API_KEY \
  BASE_URL \
  OPENAI_BASE_URL \
  OPENAI_API_BASE \
  LLM_PROVIDER \
  LLM_MODEL \
  ANSWER_MODE \
  EVIDENCE_MODE \
  MIN_SCORE \
  BGE_M3_USE_FP16 \
  BGE_M3_BATCH_SIZE \
  BGE_M3_MAX_LENGTH \
  HF_HUB_OFFLINE \
  TRANSFORMERS_OFFLINE

load_env_keys "$MCP_ROOT/.env" \
  OPENAI_API_KEY \
  BASE_URL \
  OPENAI_BASE_URL \
  OPENAI_API_BASE \
  LLM_PROVIDER \
  LLM_MODEL \
  ANSWER_MODE \
  EVIDENCE_MODE \
  MIN_SCORE \
  BGE_M3_USE_FP16 \
  BGE_M3_BATCH_SIZE \
  BGE_M3_MAX_LENGTH \
  HF_HUB_OFFLINE \
  TRANSFORMERS_OFFLINE

export PGHOST=127.0.0.1
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-ragkb}"
export PGUSER="${PGUSER:-ragkb}"
export PGPASSWORD="${PGPASSWORD:-ragkb}"
export PGTABLE="${PGTABLE:-rag_documents_bge_m3}"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-5}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-bge_m3}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-$MODELS_ROOT/bge-m3-local}"
export EMBEDDING_DIM="${EMBEDDING_DIM:-1024}"
export ANSWER_MODE="${ANSWER_MODE:-openai}"
export EVIDENCE_MODE="${EVIDENCE_MODE:-table}"
export LLM_PROVIDER="${LLM_PROVIDER:-openai}"
export LLM_MODEL="${LLM_MODEL:-DeepSeek-V3.2}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

OUT_LOG="$RUNTIME_ROOT/http_mcp.out.log"
ERR_LOG="$RUNTIME_ROOT/http_mcp.err.log"
mkdir -p "$(dirname "$OUT_LOG")"

pkill -f "fbbp_mcp_server.server --transport streamable-http" || true
pkill -f "fbtp_mcp_server.server --transport streamable-http" || true
rm -f "$OUT_LOG" "$ERR_LOG"

nohup "$PYTHON_BIN" -m fbbp_mcp_server.server --transport streamable-http --host 0.0.0.0 --port 8000 \
  >"$OUT_LOG" 2>"$ERR_LOG" < /dev/null &

for _ in $(seq 1 20); do
  if ss -ltnp | grep ':8000' >/dev/null 2>&1; then
    ss -ltnp | grep ':8000' || true
    exit 0
  fi
  sleep 2
done

echo "FBBP HTTP MCP failed to bind port 8000"
echo "--- stderr ---"
tail -n 80 "$ERR_LOG" || true
exit 1
