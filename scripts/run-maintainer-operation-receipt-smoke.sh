#!/usr/bin/env bash
# Read-only candidate qualification; never imports knowledge or promotes a case.
set -euo pipefail
if [[ $# -ne 7 ]]; then
  echo 'usage: SCOPE_JSONL FACT_JSONL RECEIPT_ROOT RECEIPT_PATH RECEIPT_SHA256 SCOPE_ID NEW_OUTPUT_DIR' >&2
  exit 2
fi
scopes=$1
facts=$2
receipt_root=$3
receipt_path=$4
receipt_sha=$5
scope_id=$6
out=$7
base=$(dirname "$scopes")
baseline_path=$(jq -sr 'max_by(.roundIndex).assessment.path' "$base/maintainer_skill_refresh_rounds.jsonl")
round=$(jq '.roundIndex' "$base/$baseline_path")
baseline_parent=()
if [[ $round -gt 1 ]]; then
  parent_sha=$(jq -r '.parentAssessmentSha256' "$base/$baseline_path")
  baseline_parent=(--parent-assessment-sha256 "$parent_sha")
fi
gate=${AGENTLAB_OPERATION_GATE:-target/debug/agentlab-maintainer-skill-flywheel}
mkdir -p "$(dirname "$out")"
mkdir "$out" # A retained experiment is never overwritten.
file_sha() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 "$1" | cut -d ' ' -f 1
  fi
}
"$gate" --scope-skills "$scopes" --program-facts "$facts" \
  --operation-receipts-root "$receipt_root" --round-index "$round" "${baseline_parent[@]}" --output "$out/before.json"
"$gate" --scope-skills "$scopes" --program-facts "$facts" \
  --prepare-operation-fact "$scope_id" --operation-receipts-root "$receipt_root" \
  --operation-receipt "$receipt_path" --operation-receipt-sha256 "$receipt_sha" \
  --output "$out/candidate-facts.jsonl"
"$gate" --scope-skills "$scopes" --program-facts "$out/candidate-facts.jsonl" \
  --operation-receipts-root "$receipt_root" --round-index "$((round + 1))" \
  --parent-assessment-sha256 "$(file_sha "$out/before.json")" --output "$out/after.json"
"$gate" --compare-operation-round --before "$out/before.json" --after "$out/after.json" \
  --selected-scope "$scope_id" --output "$out/operation-result.json"
"$gate" --stage-operation-round --base "$base" --program-facts "$out/candidate-facts.jsonl" \
  --before "$out/before.json" --after "$out/after.json" \
  --operation-receipts-root "$receipt_root" --selected-scope "$scope_id" \
  --run-id receipt-replay --allow-baseline-reassessment --output "$out/stage"
"$gate" --scope-skills "$out/stage/maintainer_scope_skills.jsonl" \
  --program-facts "$out/stage/program_facts.jsonl" \
  --operation-receipts-root "$out/stage/operation-evidence" --round-index "$((round + 1))" \
  --parent-assessment-sha256 "$(file_sha "$out/before.json")" --output "$out/portable-reassessment.json"
cmp "$out/after.json" "$out/portable-reassessment.json"
# A replay must preserve candidate bytes and yield no new scope maturity.
"$gate" --scope-skills "$scopes" --program-facts "$out/candidate-facts.jsonl" \
  --prepare-operation-fact "$scope_id" --operation-receipts-root "$receipt_root" \
  --operation-receipt "$receipt_path" --operation-receipt-sha256 "$receipt_sha" \
  --output "$out/replayed-facts.jsonl"
cmp "$out/candidate-facts.jsonl" "$out/replayed-facts.jsonl"
"$gate" --scope-skills "$scopes" --program-facts "$out/replayed-facts.jsonl" \
  --operation-receipts-root "$receipt_root" --round-index "$((round + 2))" \
  --parent-assessment-sha256 "$(file_sha "$out/after.json")" --output "$out/replay.json"
"$gate" --compare-operation-round --before "$out/after.json" --after "$out/replay.json" \
  --selected-scope "$scope_id" --output "$out/replay-result.json"
jq -e '.decision == "review-proposed-operation-knowledge" and .maintenanceReadyDelta == 1 and .authorityWritePerformed == false' "$out/operation-result.json"
jq -e '.decision == "no-change" and .maintenanceReadyDelta == 0 and .authorityWritePerformed == false' "$out/replay-result.json"
if "$gate" --stage-operation-round --base "$out/stage" --program-facts "$out/replayed-facts.jsonl" \
  --before "$out/after.json" --after "$out/replay.json" \
  --operation-receipts-root "$receipt_root" --selected-scope "$scope_id" \
  --run-id rejected-replay --output "$out/rejected-replay-stage"; then
  echo 'no-change unexpectedly staged an authority round' >&2
  exit 1
fi
test ! -e "$out/rejected-replay-stage"
