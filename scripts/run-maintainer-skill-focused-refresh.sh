#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 KNOWLEDGE RUN_ROOT CANDIDATE_ID PLAN PI" >&2
  exit 2
fi

knowledge=$1
run_root=$2
candidate_id=$3
plan=$4
pi=$5
refresh_root="$run_root/focused-refresh"
source_root="$run_root/../sources"
mkdir -p "$refresh_root" "$source_root"

target/debug/agentlab-maintainer-skill-flywheel --resolve-latest-assessment \
  --base "$knowledge" --output "$refresh_root/durable-assessment-reference.json"
assessment=$(jq -r '.assessmentPath' "$refresh_root/durable-assessment-reference.json")
test -n "$assessment"

python3 examples/maintainer-knowledge-gate/focused_fact_refresh.py prepare \
  --knowledge "$knowledge" --assessment "$assessment" \
  --candidate-id "$candidate_id" --plan "$plan" --evidence-root . \
  --output "$refresh_root/focused-refresh-request.json"

mapfile -t source < <(jq -r '.repository.repository,.repository.revision' \
  "$refresh_root/focused-refresh-request.json")
repository_id=$(jq -r '.repository.id' "$refresh_root/focused-refresh-request.json")
scope_id=$(jq -r '.scope.id' "$refresh_root/focused-refresh-request.json")
scope_path=$(jq -r '.scope.pathBoundary' "$refresh_root/focused-refresh-request.json")
[[ ${#source[@]} -eq 2 && "${source[1]}" =~ ^[0-9a-f]{40}$ ]]

source_dir="$source_root/$repository_id-${source[1]}"
scripts/checkout-maintainer-scope.sh "${source[0]}" "${source[1]}" "$scope_path" "$source_dir" \
  "$refresh_root/focused-refresh-request.json"

python3 examples/maintainer-knowledge-gate/focused_fact_refresh.py run-agent \
  --request "$refresh_root/focused-refresh-request.json" --source "$source_dir" \
  --output "$refresh_root/agent" --pi "$pi" \
  --gateway "$AGENTLAB_LM_GATEWAY_URL" --model "$AGENTLAB_MODEL" \
  --provider-route "$AGENTLAB_PROVIDER_ROUTE"

python3 examples/maintainer-knowledge-gate/focused_fact_refresh.py validate \
  --request "$refresh_root/focused-refresh-request.json" \
  --proposal "$refresh_root/agent/program-fact-proposal.json" --source "$source_dir" \
  --program-facts "$knowledge/program_facts.jsonl" \
  --output "$refresh_root/candidate-program-facts.jsonl" \
  --receipt "$refresh_root/proposal-receipt.json"

parent=$(sha256sum "$assessment" | cut -d' ' -f1)
round=$(jq -r '.roundIndex + 1' "$assessment")
target/debug/agentlab-maintainer-skill-flywheel \
  --scope-skills "$knowledge/maintainer_scope_skills.jsonl" \
  --program-facts "$refresh_root/candidate-program-facts.jsonl" \
  --operation-receipts-root "$knowledge/operation-evidence" \
  --round-index "$round" --parent-assessment-sha256 "$parent" \
  --output "$refresh_root/candidate-assessment.json"
python3 examples/maintainer-knowledge-gate/focused_fact_refresh.py compare \
  --before "$assessment" --after "$refresh_root/candidate-assessment.json" \
  --scope-id "$scope_id" --output "$refresh_root/result.json"

snapshot="$refresh_root/knowledge"
python3 scripts/maintainer-skill-tablegit.py stage \
  --base "$knowledge" --candidate-program-facts "$refresh_root/candidate-program-facts.jsonl" \
  --candidate-assessment "$refresh_root/candidate-assessment.json" \
  --result "$refresh_root/result.json" --receipt "$refresh_root/proposal-receipt.json" \
  --run-id "$GITHUB_RUN_ID" --github-repository "$GITHUB_REPOSITORY" --output "$snapshot"

if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  jq '{candidateId,scopeSkillId,acceptedFactId,changeKind,addedEvidencePaths,decision,automaticPromotion}' \
    "$refresh_root/proposal-receipt.json" >> "$GITHUB_STEP_SUMMARY"
fi
if [[ -n ${GITHUB_OUTPUT:-} ]]; then
  echo "snapshot=$snapshot" >> "$GITHUB_OUTPUT"
fi
