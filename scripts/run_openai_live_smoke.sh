#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

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
