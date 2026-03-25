#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="${1:-}"
if [[ "$PROFILE" == "llm_env" || "$PROFILE" == "llm_env_strict" ]]; then
  shift
else
  PROFILE=""
fi

DEFAULT_ARTIFACT="$ROOT_DIR/tmp/qa/openai_live_smoke.json"
if [[ "$PROFILE" == "llm_env" ]]; then
  DEFAULT_ARTIFACT="$ROOT_DIR/tmp/qa/openai_live_smoke_llm_env.json"
  export JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED="${JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED:-1}"
  export JARVIS_QA_OPENAI_LIVE_STRICT_MODE="${JARVIS_QA_OPENAI_LIVE_STRICT_MODE:-${JARVIS_QA_LLM_STRICT_MODE:-1}}"
elif [[ "$PROFILE" == "llm_env_strict" ]]; then
  DEFAULT_ARTIFACT="$ROOT_DIR/tmp/qa/openai_live_smoke_llm_env_strict.json"
  export JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED="${JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED:-0}"
  export JARVIS_QA_OPENAI_LIVE_STRICT_MODE="${JARVIS_QA_OPENAI_LIVE_STRICT_MODE:-${JARVIS_QA_LLM_STRICT_MODE:-1}}"
else
  export JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED="${JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED:-0}"
  export JARVIS_QA_OPENAI_LIVE_STRICT_MODE="${JARVIS_QA_OPENAI_LIVE_STRICT_MODE:-1}"
fi
export JARVIS_QA_OPENAI_LIVE_ARTIFACT="${JARVIS_QA_OPENAI_LIVE_ARTIFACT:-$DEFAULT_ARTIFACT}"
mkdir -p "$(dirname "$JARVIS_QA_OPENAI_LIVE_ARTIFACT")"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required." >&2
  exit 1
fi

if [[ -z "${JARVIS_QA_OPENAI_CA_BUNDLE:-}" && -z "${SSL_CERT_FILE:-}" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  CERTIFI_BUNDLE="$(python3 - <<'PY'
try:
    import certifi
except Exception:
    print("")
else:
    print(certifi.where())
PY
)"
  if [[ -n "$CERTIFI_BUNDLE" ]]; then
    export JARVIS_QA_OPENAI_CA_BUNDLE="$CERTIFI_BUNDLE"
  fi
fi

export JARVIS_QA_OPENAI_LIVE_SMOKE=1
exec python3 -m unittest tests.smoke_openai_responses_provider_live "$@"
