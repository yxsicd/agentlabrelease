#!/usr/bin/env bash
# Read-only observation of one original dispatch, including uncertain outcomes.
set -euo pipefail
[[ $# == 2 ]] || { echo 'usage: DISPATCH_DIRECTORY FRESH_OBSERVATION_DIRECTORY' >&2; exit 2; }
dispatch=$1
output=$2
test ! -e "$output" && test ! -L "$output"
mkdir "$output"
intent="$dispatch/dispatch-intent.json"
repository=$(jq -er .repository "$intent")
workflow=$(jq -er .workflow "$intent")
method=$(jq -er .methodRevision "$intent")
[[ $method =~ ^[0-9a-f]{40}$ ]]
created=$(jq -er .createdAt "$intent")
if [[ $workflow == maintainer-source-suite-review.yml ]]; then
  # An already resolved standalone review is observed by exact ID, never latest.
  observed="$dispatch/run-observation.json"
  run=$(jq -er --arg method "$method" 'select(.uniqueMatch==true and .methodRevision==$method and
    .workflow==".github/workflows/maintainer-source-suite-review.yml" and .event=="workflow_dispatch") | .runId' "$observed")
  [[ $run =~ ^[1-9][0-9]{0,19}$ ]]
  body_sha=$(shasum -a 256 "$dispatch/dispatch-body.json" | cut -d ' ' -f1)
  jq -e --arg sha "$body_sha" '.schema=="agentlab.retained_completion_review_dispatch_intent.v1" and
    .bodySha256==$sha and .dispatchAgainAllowed==false and .maximumNewAuthorCalls==0' "$intent" >/dev/null
  jq -e '.ref=="main"' "$dispatch/dispatch-body.json" >/dev/null
  gh api "repos/$repository/actions/runs/$run" > "$output/original-run.json"
  jq -e --arg run "$run" --arg method "$method" --arg repository "$repository" --arg created "$created" '
    (.id|tostring)==$run and .head_sha==$method and .head_branch=="main" and
    .event=="workflow_dispatch" and .repository.full_name==$repository and .run_attempt==1 and
    .name=="Maintainer independent source suite review" and
    .path==".github/workflows/maintainer-source-suite-review.yml" and
    .created_at>=($created|sub("\\.[0-9]+Z$";"Z"))' "$output/original-run.json" >/dev/null
  jq '[.]' "$output/original-run.json" > "$output/matches.json"
else
[[ $workflow == maintainer-skill-agent-flywheel.yml || $workflow == maintainer-source-recipe-author.yml ]]
id=$(jq -er .requestId "$intent")
[[ $id =~ ^[0-9a-f]{64}$ ]]
# A bounded first page. If visibility/history is inconclusive, retain it and
# wait or explicitly inspect additional history; never dispatch a replacement.
gh api --method GET "repos/$repository/actions/workflows/$workflow/runs" \
  -f event=workflow_dispatch -f head_sha="$method" -f per_page=100 \
  -f "created=>=$created" > "$output/original-runs.json"
jq --arg title "AgentLab gap $id" \
  '[.workflow_runs[]|select(.display_title==$title)]' "$output/original-runs.json" > "$output/matches.json"
fi
count=$(jq length "$output/matches.json")
if [[ $count == 0 ]]; then
  jq -n '{runVisible:false,dispatchAgainAllowed:false,childCompletionVerified:false}' > "$output/observation.json"
elif [[ $count == 1 ]]; then
  jq -e --arg method "$method" --arg repository "$repository" \
    '.[0] | .head_sha==$method and .head_branch=="main" and .event=="workflow_dispatch" and .repository.full_name==$repository and (.id|type=="number")' \
    "$output/matches.json" >/dev/null
  jq '.[0]|{runVisible:true,runId:.id,url:.html_url,status,conclusion,dispatchAgainAllowed:false,childCompletionVerified:(.status=="completed"),closedLoopQualified:false}' \
    "$output/matches.json" > "$output/observation.json"
else
  echo 'Ambiguous dispatch identity; retain all matches and stop without another dispatch' >&2
  exit 1
fi
jq '.' "$output/observation.json"
