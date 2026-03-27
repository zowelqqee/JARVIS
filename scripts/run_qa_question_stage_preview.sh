#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

STAGE="${1:-beta_question_default}"
if [[ "$STAGE" == "beta_question_default" || "$STAGE" == "stable" ]]; then
  shift
else
  echo "Usage: scripts/run_qa_question_stage_preview.sh [beta_question_default|stable]" >&2
  exit 2
fi

export JARVIS_QA_ROLLOUT_STAGE="$STAGE"
unset JARVIS_QA_BACKEND
export JARVIS_QA_LLM_ENABLED="true"
export JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED="true"
export JARVIS_QA_LLM_FALLBACK_ENABLED="false"
export JARVIS_QA_LLM_PROVIDER="openai_responses"
export JARVIS_QA_LLM_STRICT_MODE="true"

echo "Launching JARVIS question-mode stage preview with rollout_stage=$STAGE"
echo "question default follows rollout stage; command path remains deterministic"

exec python3 cli.py "$@"
