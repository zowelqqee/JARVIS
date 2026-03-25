#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="${1:-llm_env}"
if [[ "$PROFILE" == "llm_env" || "$PROFILE" == "llm_env_strict" ]]; then
  shift
else
  echo "Usage: scripts/run_qa_rollout_gate.sh [llm_env|llm_env_strict] [extra eval args...]" >&2
  exit 2
fi

if [[ "$PROFILE" == "llm_env" ]]; then
  DEFAULT_ARTIFACT="$ROOT_DIR/tmp/qa/openai_live_smoke_llm_env.json"
else
  DEFAULT_ARTIFACT="$ROOT_DIR/tmp/qa/openai_live_smoke_llm_env_strict.json"
fi

export JARVIS_QA_OPENAI_LIVE_ARTIFACT="${JARVIS_QA_OPENAI_LIVE_ARTIFACT:-$DEFAULT_ARTIFACT}"

exec python3 -m evals.run_qa_eval \
  --compare-profile deterministic \
  --compare-profile "$PROFILE" \
  --gate-candidate-profile "$PROFILE" \
  "$@"
