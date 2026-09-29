#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 KNOWLEDGE RUN_ROOT REPOSITORY ITERATIONS PI" >&2
  exit 2
fi

knowledge=$1
run_root=$2
repository=$3
iterations=$4
pi=$5

: "${AGENTLAB_LM_GATEWAY_URL:?required}"
: "${AGENTLAB_LM_GATEWAY_KEY:?required}"
: "${AGENTLAB_MODEL:?required}"
: "${AGENTLAB_PROVIDER_ROUTE:?required}"
: "${AGENTLAB_TABLEGIT_MCP_URL:?required}"
: "${AGENTLAB_TABLEGIT_PERSON_ID:?required}"
: "${AGENTLAB_RUN_ID:?required}"

export GITHUB_RUN_ID=$AGENTLAB_RUN_ID
export GITHUB_REPOSITORY=${AGENTLAB_SOURCE_REPOSITORY:-yxsicd/agentlabrelease}
export AGENTLAB_PRODUCER_KIND=${AGENTLAB_PRODUCER_KIND:-hwlinux-local}
export AGENTLAB_PRODUCER_HOST=${AGENTLAB_PRODUCER_HOST:-$(hostname)}

mkdir -p "$run_root"
assessment=$(find "$knowledge/assessments" -maxdepth 1 -type f -name '*.json' -print0 |
  xargs -0 jq -r '[.roundIndex,input_filename] | @tsv' | sort -n | tail -1 | cut -f2-)
test -n "$assessment"
python3 examples/maintainer-knowledge-gate/agent_flywheel.py plan \
  --knowledge "$knowledge" --assessment "$assessment" --repository "$repository" \
  --output "$run_root/convergence-plan.json"

converging=false
if [[ $iterations == converge ]]; then
  converging=true
  iterations=$(jq -r '.summary.eligible' "$run_root/convergence-plan.json")
  if [[ $iterations -eq 0 ]]; then
    echo "repository has no eligible L1 scope to advance" >&2
    exit 3
  fi
  export AGENTLAB_MAX_ITERATIONS=64
fi

scripts/run-maintainer-skill-agent-loop.sh \
  "$knowledge" "$run_root" "$repository" "$iterations" "$pi"

snapshot="$run_root/loop/knowledge-$iterations"
test -f "$snapshot/stage-manifest.json"
final_assessment=$(find "$snapshot/assessments" -maxdepth 1 -type f -name '*.json' -print0 |
  xargs -0 jq -r '[.roundIndex,input_filename] | @tsv' | sort -n | tail -1 | cut -f2-)
test -n "$final_assessment"
python3 examples/maintainer-knowledge-gate/agent_flywheel.py plan \
  --knowledge "$snapshot" --assessment "$final_assessment" --repository "$repository" \
  --output "$run_root/convergence-report.json"

producer_args=(--producer-kind "$AGENTLAB_PRODUCER_KIND")
if [[ -n ${AGENTLAB_PRODUCER_URL:-} ]]; then
  producer_args+=(--producer-url "$AGENTLAB_PRODUCER_URL")
fi
if [[ -n ${AGENTLAB_PRODUCER_HOST:-} ]]; then
  producer_args+=(--producer-host "$AGENTLAB_PRODUCER_HOST")
fi

python3 scripts/maintainer-skill-tablegit.py sync \
  --base "$knowledge" --snapshot "$snapshot" --export "$knowledge" \
  --receipt "$run_root/tablegit-sync-receipt.json" \
  --run-id "$GITHUB_RUN_ID" --github-repository "$GITHUB_REPOSITORY" \
  "${producer_args[@]}"

scripts/run-case-generation-shadow.sh "$knowledge" "$run_root" "$pi"

materialization_file="$run_root/materialization.json"
printf '{}\n' > "$materialization_file"
if [[ -n ${AGENTLAB_SKILLSGIT_ROOT:-} ]]; then
  : "${AGENTLAB_SKILLSGIT_REVISION:?required when AGENTLAB_SKILLSGIT_ROOT is set}"
  python3 scripts/materialize-skillsgit-maintainer-tree.py \
    --knowledge "$knowledge" --repository "$repository" \
    --skillsgit-root "$AGENTLAB_SKILLSGIT_ROOT" \
    --skillsgit-revision "$AGENTLAB_SKILLSGIT_REVISION" \
    --output "$run_root/materialized-maintainer-tree" \
    > "$materialization_file"
elif [[ $converging == true ]]; then
  echo "converge mode requires AGENTLAB_SKILLSGIT_ROOT and AGENTLAB_SKILLSGIT_REVISION" >&2
  exit 4
fi

jq -n \
  --slurpfile loop "$run_root/loop/loop-receipt.json" \
  --slurpfile tablegit "$run_root/tablegit-sync-receipt.json" \
  --slurpfile shadow "$run_root/shadow-case-generation/shadow-receipt.json" \
  --slurpfile materialization "$materialization_file" \
  --slurpfile convergencePlan "$run_root/convergence-plan.json" \
  --slurpfile convergenceReport "$run_root/convergence-report.json" \
  '{schema:"agentlab.maintainer_skill_local_flywheel_receipt.v1",
    loop:$loop[0],tableGit:$tablegit[0],shadow:$shadow[0],
    materialization:$materialization[0],convergencePlan:$convergencePlan[0],
    convergenceReport:$convergenceReport[0]}' \
  > "$run_root/local-flywheel-receipt.json"
