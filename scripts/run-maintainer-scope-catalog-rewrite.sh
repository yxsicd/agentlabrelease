#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 KNOWLEDGE_DIR RUN_ROOT" >&2
  exit 2
fi

knowledge=$1
run_root=$2
source_root="${run_root}-sources"
scope_catalog="$knowledge/maintainer_scope_skills.jsonl"
common_review="$knowledge/decomposition-reviews/code-workshop-common.json"
component_review="$knowledge/decomposition-reviews/code-workshop-features-componentlibrary.json"
common_id=skill-scope-code-workshop-common
component_id=skill-scope-code-workshop-features-componentlibrary

[[ ! -e $run_root && ! -e $source_root ]] || {
  echo "rewrite run paths already exist" >&2
  exit 2
}
mkdir -p "$run_root" "$source_root"

scope_field() {
  local scope_id=$1
  local field=$2
  jq -r --arg id "$scope_id" --arg field "$field" \
    'select(.id == $id) | .[$field]' "$scope_catalog"
}

repository=$(scope_field "$common_id" repository)
revision=$(scope_field "$common_id" sourceRevision)
common_boundary=$(scope_field "$common_id" pathBoundary)
component_repository=$(scope_field "$component_id" repository)
component_revision=$(scope_field "$component_id" sourceRevision)
component_boundary=$(scope_field "$component_id" pathBoundary)
[[ -n $repository && $repository == "$component_repository" ]]
[[ $revision =~ ^[0-9a-f]{40}$ && $revision == "$component_revision" ]]

scripts/checkout-maintainer-scope.sh \
  "$repository" "$revision" "$common_boundary" "$source_root/common"
scripts/checkout-maintainer-scope.sh \
  "$repository" "$revision" "$component_boundary" "$source_root/componentlibrary"

python3 examples/maintainer-knowledge-gate/apply_scope_decomposition_review.py \
  --scope-skills "$scope_catalog" --review "$common_review" \
  --repository "$source_root/common" --output "$run_root/after-common.jsonl" \
  > "$run_root/common-rewrite-receipt.json"
python3 examples/maintainer-knowledge-gate/apply_scope_decomposition_review.py \
  --scope-skills "$run_root/after-common.jsonl" --review "$component_review" \
  --repository "$source_root/componentlibrary" --output "$run_root/candidate-scope-skills.jsonl" \
  > "$run_root/componentlibrary-rewrite-receipt.json"

assessment=$(find "$knowledge/assessments" -maxdepth 1 -type f -name '*.json' -print0 |
  xargs -0 jq -r '[.roundIndex,input_filename] | @tsv' | sort -n | tail -1 | cut -f2-)
[[ -n $assessment ]]
round=$(jq -r '.roundIndex + 1' "$assessment")
parent=$(sha256sum "$assessment" | cut -d' ' -f1)
target/debug/agentlab-maintainer-skill-flywheel \
  --scope-skills "$run_root/candidate-scope-skills.jsonl" \
  --program-facts "$knowledge/program_facts.jsonl" \
  --round-index "$round" --parent-assessment-sha256 "$parent" \
  --output "$run_root/candidate-assessment.json"

python3 scripts/maintainer-skill-tablegit.py stage-scope-rewrite \
  --base "$knowledge" \
  --candidate-scope-skills "$run_root/candidate-scope-skills.jsonl" \
  --candidate-assessment "$run_root/candidate-assessment.json" \
  --rewrite-receipt "$run_root/common-rewrite-receipt.json" \
  --rewrite-receipt "$run_root/componentlibrary-rewrite-receipt.json" \
  --run-id "$GITHUB_RUN_ID" --github-repository "$GITHUB_REPOSITORY" \
  --output "$run_root/staged-knowledge"

if [[ -n ${GITHUB_OUTPUT:-} ]]; then
  printf 'snapshot=%s\n' "$run_root/staged-knowledge" >> "$GITHUB_OUTPUT"
fi
jq '{totals,decision,nextRoundObjectives}' "$run_root/candidate-assessment.json"
