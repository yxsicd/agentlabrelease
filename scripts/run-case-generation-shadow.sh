#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 KNOWLEDGE RUN_ROOT PI" >&2
  exit 2
fi

knowledge=$1
run_root=$2
pi=$3
shadow_root="$run_root/shadow-case-generation"
request="$shadow_root/shadow-request.json"
receipt="$shadow_root/shadow-receipt.json"
mkdir -p "$shadow_root"

python3 examples/maintainer-knowledge-gate/case_generation_shadow.py prepare \
  --knowledge "$knowledge" --loop-receipt "$run_root/loop/loop-receipt.json" \
  --runtime-target "${AGENTLAB_SHADOW_RUNTIME_TARGET:-harmony-emulator}" \
  --output "$request"

if [[ $(jq -r '.policy.shadowEligible' "$request") != true ]]; then
  python3 examples/maintainer-knowledge-gate/case_generation_shadow.py record-failure \
    --request "$request" --rounds "$knowledge/case_generation_rounds.jsonl" \
    --receipt "$receipt" --run-id "$GITHUB_RUN_ID" \
    --reason shadow-input-requires-external-hardware
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    jq '{status,candidateId,reason,roundId,automaticPromotion}' "$receipt" >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

repository_id=$(jq -r '.repository.id' "$request")
revision=$(jq -r '.repository.revision' "$request")
source_dir="$run_root/../sources/$repository_id-$revision"
test -d "$source_dir/.git"

if ! python3 examples/maintainer-knowledge-gate/case_generation_shadow.py run-agent \
  --request "$request" --source "$source_dir" --output "$shadow_root/agent" --pi "$pi" \
  --gateway "$AGENTLAB_LM_GATEWAY_URL" --model "$AGENTLAB_MODEL" \
  --provider-route "$AGENTLAB_PROVIDER_ROUTE"; then
  python3 examples/maintainer-knowledge-gate/case_generation_shadow.py record-failure \
    --request "$request" --rounds "$knowledge/case_generation_rounds.jsonl" \
    --receipt "$receipt" --run-id "$GITHUB_RUN_ID" \
    --reason shadow-construction-agent-failed
elif ! python3 examples/maintainer-knowledge-gate/case_generation_shadow.py record-success \
  --request "$request" --proposal "$shadow_root/agent/shadow-case-proposal.json" \
  --rounds "$knowledge/case_generation_rounds.jsonl" \
  --candidates "$knowledge/case_generation_candidates.jsonl" \
  --receipt "$receipt" --run-id "$GITHUB_RUN_ID"; then
  python3 examples/maintainer-knowledge-gate/case_generation_shadow.py record-failure \
    --request "$request" --rounds "$knowledge/case_generation_rounds.jsonl" \
    --receipt "$receipt" --run-id "$GITHUB_RUN_ID" \
    --reason shadow-proposal-hard-gate-rejected
fi

if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  jq '{status,candidateId,roundId,automaticPromotion}' "$receipt" >> "$GITHUB_STEP_SUMMARY"
fi
