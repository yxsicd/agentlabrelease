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

scripts/run-maintainer-skill-agent-loop.sh \
  "$knowledge" "$run_root" "$repository" "$iterations" "$pi"

snapshot="$run_root/loop/knowledge-$iterations"
test -f "$snapshot/stage-manifest.json"

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

jq -n \
  --slurpfile loop "$run_root/loop/loop-receipt.json" \
  --slurpfile tablegit "$run_root/tablegit-sync-receipt.json" \
  --slurpfile shadow "$run_root/shadow-case-generation/shadow-receipt.json" \
  '{schema:"agentlab.maintainer_skill_local_flywheel_receipt.v1",
    loop:$loop[0],tableGit:$tablegit[0],shadow:$shadow[0]}' \
  > "$run_root/local-flywheel-receipt.json"
