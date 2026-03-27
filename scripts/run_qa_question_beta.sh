#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="${1:-llm_env_strict}"
if [[ "$PROFILE" == "llm_env" || "$PROFILE" == "llm_env_strict" ]]; then
  shift
else
  echo "Usage: scripts/run_qa_question_beta.sh [llm_env|llm_env_strict]" >&2
  exit 2
fi

# Pin the opt-in beta launcher so parent-shell overrides do not change the intended runtime path.
export JARVIS_QA_BACKEND="llm"
export JARVIS_QA_ROLLOUT_STAGE="alpha_opt_in"
export JARVIS_QA_LLM_ENABLED="true"
export JARVIS_QA_LLM_PROVIDER="openai_responses"
export JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED="true"
export JARVIS_QA_LLM_STRICT_MODE="true"

if [[ "$PROFILE" == "llm_env" ]]; then
  export JARVIS_QA_LLM_FALLBACK_ENABLED="true"
else
  export JARVIS_QA_LLM_FALLBACK_ENABLED="false"
fi

echo "Launching JARVIS question-mode beta with profile=$PROFILE"
echo "stage=alpha_opt_in; product default remains deterministic"
echo "backend=${JARVIS_QA_BACKEND} provider=${JARVIS_QA_LLM_PROVIDER} open-domain=${JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED} fallback=${JARVIS_QA_LLM_FALLBACK_ENABLED}"

exec python3 cli.py "$@"
