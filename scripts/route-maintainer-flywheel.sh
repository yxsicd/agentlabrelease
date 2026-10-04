#!/usr/bin/env bash
# One gap-selected dispatch. Children retain their own exact authority gates.
set -euo pipefail
[[ $# == 4 ]] || { echo 'usage: KNOWLEDGE REPOSITORY FRESH_OUTPUT plan|dispatch' >&2; exit 2; }
knowledge=$1
repository_selector=$2
output=$3
mode=$4
[[ $mode == plan || $mode == dispatch ]]
test ! -e "$output" && test ! -L "$output"
mkdir "$output"
gate=${AGENTLAB_FLYWHEEL_GATE:-target/debug/agentlab-maintainer-skill-flywheel}
"$gate" --resolve-latest-assessment --base "$knowledge" --output "$output/durable.json"
assessment=$(jq -er .assessmentPath "$output/durable.json")
parent=()
if jq -e '.parentAssessmentSha256 != null' "$assessment" >/dev/null; then
  parent=(--parent-assessment-sha256 "$(jq -er .parentAssessmentSha256 "$assessment")")
fi
# These are implemented children, not a declaration that all operation kinds run.
"$gate" --plan-next-round --scope-skills "$knowledge/maintainer_scope_skills.jsonl" \
  --program-facts "$knowledge/program_facts.jsonl" \
  --operation-receipts-root "$knowledge/operation-evidence" \
  --round-index "$(jq -er .roundIndex "$assessment")" ${parent[@]+"${parent[@]}"} \
  --available-lane semantic-refresh --available-lane operation-verification \
  --available-operation-kind source-only --batch-size 1 --repository "$repository_selector" \
  --output "$output/plan.json"
lane=$(jq -r .nextLane "$output/plan.json")
if [[ $(jq -r .decision "$output/plan.json") != propose-next-batch ]]; then
  jq '{decision,summary,selectedScopeIds,closedLoopQualified}' "$output/plan.json"
  exit 0
fi
selected_repository=$(jq -er '.scopes[] | select(.selected) | .repositoryId' "$output/plan.json")
method=$(git rev-parse HEAD)
case "$lane" in
  semantic-refresh)
    workflow=maintainer-skill-agent-flywheel.yml
    inputs=$(jq -n --arg cut "$knowledge" --arg repository "$selected_repository" --arg method "$method" \
      '{knowledge_directory:$cut,repository:$repository,mode:"expand",iterations:"1",scope_batch_size:"1",expected_method:$method}')
    ;;
  operation-verification)
    jq -e '[.scopes[]|select(.selected)|.operationKind]==["source-only"]' "$output/plan.json" >/dev/null
    workflow=maintainer-source-recipe-author.yml
    rubric=examples/maintainer-knowledge-gate/source-quality-rubric.json
    rubric_sha=$(shasum -a 256 "$rubric" | cut -d ' ' -f1)
    inputs=$(jq -n --arg cut "$knowledge" --arg repository "$selected_repository" --arg method "$method" \
      --arg rubric "$rubric" --arg sha "$rubric_sha" \
      '{knowledge_directory:$cut,repository:$repository,expected_method:$method,reasoning_effort:"default",thinking_type:"disabled",response_format:"json-object",design_first:"true",design_revisions:"1",code_revisions:"1",independent_review:"true",review_rubric:$rubric,review_rubric_sha256:$sha,review_repair_limit:"1"}')
    ;;
  *) echo 'No implemented child for selected lane' >&2; exit 1 ;;
esac
request_id=$(printf '%s' "$(cd "$output" && pwd):$method" | shasum -a 256 | cut -d ' ' -f1)
jq -n --arg workflow "$workflow" --arg method "$method" --arg id "$request_id" --argjson inputs "$inputs" \
  '{schema:"agentlab.gap_dispatch_request.v1",requestId:$id,workflow:$workflow,methodRevision:$method,inputs:($inputs+{coordinator_request_id:$id}),closedLoopQualified:false}' > "$output/request.json"
if [[ $mode == plan ]]; then
  jq '.' "$output/request.json"
  exit 0
fi
test -n "${GITHUB_REPOSITORY:-}"
test -z "$(git status --porcelain)"
test "$(gh api "repos/$GITHUB_REPOSITORY/commits/main" --jq .sha)" == "$method"
# Intent exists before the only external dispatch. Uncertain outcome needs run
# discovery, never another call or reuse of this output directory.
jq --arg repository "$GITHUB_REPOSITORY" --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{requestId,workflow,methodRevision,inputs,repository:$repository,createdAt:$created,dispatchAttempted:true}' "$output/request.json" > "$output/dispatch-intent.json"
fields=()
while IFS= read -r field; do fields+=(-f "$field"); done < <(jq -r '.inputs|to_entries[]|.key+"="+.value' "$output/request.json")
gh workflow run "$workflow" --repo "$GITHUB_REPOSITORY" --ref main "${fields[@]}" \
  > "$output/dispatch.stdout" 2> "$output/dispatch.stderr"
jq -n '{dispatchRequestAccepted:true,childCompletionVerified:false,authorityWriteVerified:false,closedLoopQualified:false}' > "$output/dispatch-receipt.json"
