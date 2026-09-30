#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 KNOWLEDGE RUN_ROOT REPOSITORY ITERATIONS PI" >&2
  exit 2
fi

knowledge=$1
run_root=$2
repository_selector=$3
iterations=$4
pi=$5

max_iterations=${AGENTLAB_MAX_ITERATIONS:-3}
scope_batch_size=${AGENTLAB_SCOPE_BATCH_SIZE:-1}
if [[ ! $max_iterations =~ ^[1-9][0-9]*$ || $max_iterations -gt 64 ]]; then
  echo "AGENTLAB_MAX_ITERATIONS must be an integer from 1 through 64" >&2
  exit 2
fi
if [[ ! $iterations =~ ^[1-9][0-9]*$ || $iterations -gt $max_iterations ]]; then
  echo "iterations must be an integer from 1 through $max_iterations" >&2
  exit 2
fi
if [[ ! $scope_batch_size =~ ^[1-4]$ ]]; then
  echo "AGENTLAB_SCOPE_BATCH_SIZE must be an integer from 1 through 4" >&2
  exit 2
fi

loop_root="$run_root/loop"
source_root="$run_root/../sources"
mkdir -p "$loop_root" "$source_root"
working_knowledge=$knowledge
producer_args=(--producer-kind "${AGENTLAB_PRODUCER_KIND:-github-action}")
if [[ -n ${AGENTLAB_PRODUCER_URL:-} ]]; then
  producer_args+=(--producer-url "$AGENTLAB_PRODUCER_URL")
fi
if [[ -n ${AGENTLAB_PRODUCER_HOST:-} ]]; then
  producer_args+=(--producer-host "$AGENTLAB_PRODUCER_HOST")
fi

for ((iteration = 1; iteration <= iterations; iteration++)); do
  iteration_root="$loop_root/iteration-$iteration"
  mkdir -p "$iteration_root"
  target/debug/agentlab-maintainer-skill-flywheel --resolve-latest-assessment \
    --base "$working_knowledge" --output "$iteration_root/durable-assessment-reference.json"
  assessment=$(jq -r '.assessmentPath' "$iteration_root/durable-assessment-reference.json")
  test -n "$assessment"

  if [[ $(jq -r '.standard.operationEvidencePolicy' "$assessment") == verified-receipt-content ]]; then
    test -d "$working_knowledge/operation-evidence"
    plan_parent=()
    if [[ $(jq -r '.roundIndex' "$assessment") -gt 1 ]]; then
      plan_parent=(--parent-assessment-sha256 "$(jq -r '.parentAssessmentSha256' "$assessment")")
    fi
    target/debug/agentlab-maintainer-skill-flywheel --plan-next-round \
      --scope-skills "$working_knowledge/maintainer_scope_skills.jsonl" \
      --program-facts "$working_knowledge/program_facts.jsonl" \
      --operation-receipts-root "$working_knowledge/operation-evidence" \
      --round-index "$(jq -r '.roundIndex' "$assessment")" ${plan_parent[@]+"${plan_parent[@]}"} \
      --available-lane semantic-refresh --batch-size "$scope_batch_size" \
      --repository "$repository_selector" --output "$iteration_root/strict-next-round-plan.json"
    target/debug/agentlab-maintainer-skill-flywheel --prepare-semantic-batch \
      --scope-skills "$working_knowledge/maintainer_scope_skills.jsonl" \
      --program-facts "$working_knowledge/program_facts.jsonl" \
      --operation-receipts-root "$working_knowledge/operation-evidence" \
      --next-round-plan "$iteration_root/strict-next-round-plan.json" --before "$assessment" \
      --knowledge-cut "$working_knowledge/maintainer-knowledge-cut.json" \
      --repository "$repository_selector" --output "$iteration_root/flywheel-batch-request.json"
  else
    # Historical policy remains explicit; never silently migrate it to strict.
    python3 examples/maintainer-knowledge-gate/agent_flywheel.py prepare-batch \
      --knowledge "$working_knowledge" --assessment "$assessment" \
      --repository "$repository_selector" --batch-size "$scope_batch_size" \
      --output "$iteration_root/flywheel-batch-request.json"
  fi

  mapfile -t source < <(jq -r '.repository.repository,.repository.revision' \
    "$iteration_root/flywheel-batch-request.json")
  repository_id=$(jq -r '.repository.id' "$iteration_root/flywheel-batch-request.json")
  scope_count=$(jq -r '.selectedScopeCount' "$iteration_root/flywheel-batch-request.json")
  scope_path=$(jq -r '.requests[0].scope.pathBoundary' "$iteration_root/flywheel-batch-request.json")
  [[ $scope_count =~ ^[1-4]$ && $scope_count -le $scope_batch_size ]]
  [[ ${#source[@]} -eq 2 && "${source[1]}" =~ ^[0-9a-f]{40}$ ]]
  python3 examples/maintainer-knowledge-gate/agent_flywheel.py plan \
    --knowledge "$working_knowledge" --assessment "$assessment" \
    --repository "$repository_id" --output "$iteration_root/convergence-plan.json"

  # Source checkouts are execution inputs, not evidence artifacts. Keep them
  # beside run_root so the workflow's run/ upload cannot retain whole repos.
  source_dir="$source_root/$repository_id-${source[1]}"
  scripts/checkout-maintainer-scope.sh \
    "${source[0]}" "${source[1]}" "$scope_path" "$source_dir" \
    "$iteration_root/flywheel-batch-request.json"

  mkdir -p "$iteration_root/requests" "$iteration_root/agents" \
    "$iteration_root/receipts" "$iteration_root/facts"
  pids=()
  agent_outputs=()
  for ((scope_index = 0; scope_index < scope_count; scope_index++)); do
    request="$iteration_root/requests/scope-$scope_index.json"
    jq ".requests[$scope_index]" "$iteration_root/flywheel-batch-request.json" > "$request"
    agent_outputs[$scope_index]="$iteration_root/agents/scope-$scope_index"
    python3 examples/maintainer-knowledge-gate/agent_flywheel.py run-agent \
      --request "$request" --source "$source_dir" \
      --output "${agent_outputs[$scope_index]}" --pi "$pi" \
      --gateway "$AGENTLAB_LM_GATEWAY_URL" --model "$AGENTLAB_MODEL" \
      --provider-route "$AGENTLAB_PROVIDER_ROUTE" &
    pids+=("$!")
  done
  failed_scopes=()
  for ((scope_index = 0; scope_index < scope_count; scope_index++)); do
    if ! wait "${pids[$scope_index]}"; then
      failed_scopes+=("$scope_index")
    fi
  done

  # Preserve every successful proposal. Retry only failed independent scopes,
  # once and in parallel, before the aggregate hard gate or TableGit mutation.
  retried_scopes=("${failed_scopes[@]}")
  if (( ${#failed_scopes[@]} )); then
    mkdir -p "$iteration_root/agent-retries"
    retry_pids=()
    for scope_index in "${failed_scopes[@]}"; do
      agent_outputs[$scope_index]="$iteration_root/agent-retries/scope-$scope_index"
      python3 examples/maintainer-knowledge-gate/agent_flywheel.py run-agent \
        --request "$iteration_root/requests/scope-$scope_index.json" --source "$source_dir" \
        --output "${agent_outputs[$scope_index]}" --pi "$pi" \
        --gateway "$AGENTLAB_LM_GATEWAY_URL" --model "$AGENTLAB_MODEL" \
        --provider-route "$AGENTLAB_PROVIDER_ROUTE" &
      retry_pids+=("$!")
    done
    agent_failed=false
    for retry_index in "${!failed_scopes[@]}"; do
      if ! wait "${retry_pids[$retry_index]}"; then
        agent_failed=true
      fi
    done
  else
    agent_failed=false
  fi
  [[ $agent_failed == false ]] || {
    echo "one or more bounded Maintainer Skill Agents failed after one isolated retry" >&2
    exit 1
  }

  candidate_facts="$working_knowledge/program_facts.jsonl"
  receipt_args=()
  lifecycle_args=()
  for ((scope_index = 0; scope_index < scope_count; scope_index++)); do
    next_facts="$iteration_root/facts/scope-$scope_index.jsonl"
    receipt="$iteration_root/receipts/scope-$scope_index.json"
    python3 examples/maintainer-knowledge-gate/agent_flywheel.py validate \
      --request "$iteration_root/requests/scope-$scope_index.json" \
      --proposal "${agent_outputs[$scope_index]}/program-fact-proposal.json" \
      --source "$source_dir" --program-facts "$candidate_facts" \
      --output "$next_facts" --receipt "$receipt"
    candidate_facts=$next_facts
    receipt_args+=(--receipt "$receipt")
    lifecycle_args+=("${agent_outputs[$scope_index]}/evidence/maintainer-skill-author-attempt-lifecycle.json")
  done
  cp "$candidate_facts" "$iteration_root/candidate-program-facts.jsonl"
  jq -s '.' "$iteration_root"/receipts/scope-*.json \
    > "$iteration_root/proposal-receipts.json"
  jq -s '.' "${lifecycle_args[@]}" > "$iteration_root/agent-lifecycles.json"
  printf '%s\n' "${retried_scopes[@]}" | jq -s 'map(tonumber)' \
    > "$iteration_root/retried-scope-indices.json"

  parent=$(sha256sum "$assessment" | cut -d' ' -f1)
  round=$(jq -r '.roundIndex + 1' "$assessment")
  operation_receipt_args=()
  if [[ $(jq -r '.standard.operationEvidencePolicy' "$assessment") == verified-receipt-content ]]; then
    test -d "$working_knowledge/operation-evidence"
    operation_receipt_args=(--operation-receipts-root "$working_knowledge/operation-evidence")
  fi
  target/debug/agentlab-maintainer-skill-flywheel \
    --scope-skills "$working_knowledge/maintainer_scope_skills.jsonl" \
    --program-facts "$iteration_root/candidate-program-facts.jsonl" \
    --round-index "$round" --parent-assessment-sha256 "$parent" "${operation_receipt_args[@]}" \
    --output "$iteration_root/candidate-assessment.json"
  selected_args=()
  while IFS= read -r selected_scope; do
    selected_args+=(--selected-scope "$selected_scope")
  done < <(jq -r '.requests[].scope.id' "$iteration_root/flywheel-batch-request.json")
  target/debug/agentlab-maintainer-skill-flywheel --compare-semantic-round \
    --before "$assessment" --after "$iteration_root/candidate-assessment.json" \
    "${selected_args[@]}" --output "$iteration_root/result.json"
  jq -e '.decision == "review-proposed-knowledge"' "$iteration_root/result.json"

  next_knowledge="$loop_root/knowledge-$iteration"
  python3 scripts/maintainer-skill-tablegit.py stage \
    --base "$working_knowledge" \
    --candidate-program-facts "$iteration_root/candidate-program-facts.jsonl" \
    --candidate-assessment "$iteration_root/candidate-assessment.json" \
    --result "$iteration_root/result.json" \
    "${receipt_args[@]}" \
    --run-id "$GITHUB_RUN_ID" --github-repository "$GITHUB_REPOSITORY" \
    "${producer_args[@]}" \
    --output "$next_knowledge"
  working_knowledge=$next_knowledge

  execution_plan="$iteration_root/convergence-plan.json"
  if [[ -f "$iteration_root/strict-next-round-plan.json" ]]; then
    execution_plan="$iteration_root/strict-next-round-plan.json"
  fi
  jq -n --argjson iteration "$iteration" --arg repository "$repository_id" \
    --slurpfile batch "$iteration_root/flywheel-batch-request.json" \
    --slurpfile result "$iteration_root/result.json" \
    --slurpfile receipts "$iteration_root/proposal-receipts.json" \
    --slurpfile lifecycle "$iteration_root/agent-lifecycles.json" \
    --slurpfile retried "$iteration_root/retried-scope-indices.json" \
    --slurpfile plan "$execution_plan" \
    '{iteration:$iteration,repository:$repository,
      scopeIds:[$batch[0].requests[].scope.id],
      acceptedFactIds:[$receipts[0][].acceptedFactId],
      batchSize:$batch[0].selectedScopeCount,before:$result[0].before,
      after:$result[0].after,
      selectionPlan:{decision:$plan[0].decision,summary:$plan[0].summary,
        policy:($batch[0].selectionPolicy // "legacy-semantic-selector"),
        planSha256:$batch[0].selectionPlanSha256,
        sourceAssessmentSha256:$batch[0].sourceAssessment.sha256},
      execution:{parallel:true,agentCount:($lifecycle[0]|length),
        retriedScopeIndices:$retried[0],retryCount:($retried[0]|length),
        maxToolCalls:([$lifecycle[0][].maxToolCalls]|add),
        startedToolCalls:([$lifecycle[0][].startedToolCalls]|add),
        completedToolCalls:([$lifecycle[0][].completedToolCalls]|add),
        toolCallBudgetExceeded:any($lifecycle[0][];.toolCallBudgetExceeded),
        wallDurationMs:([$lifecycle[0][].durationMs]|max),
        aggregateAgentDurationMs:([$lifecycle[0][].durationMs]|add),
        timedOut:any($lifecycle[0][];.timedOut)},
      automaticPromotion:false}' \
    > "$iteration_root/loop-result.json"
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    jq '{iteration,repository,scopeIds,acceptedFactIds,batchSize,before,after,automaticPromotion}' \
      "$iteration_root/loop-result.json" >> "$GITHUB_STEP_SUMMARY"
  fi
done

jq -s --argjson requested "$iterations" \
  '{schema:"agentlab.maintainer_skill_bounded_loop_receipt.v1",
    requestedIterations:$requested,completedIterations:length,
    automaticPromotion:false,iterations:.}' \
  "$loop_root"/iteration-*/loop-result.json > "$loop_root/loop-receipt.json"

if [[ -n ${GITHUB_OUTPUT:-} ]]; then
  echo "snapshot=$working_knowledge" >> "$GITHUB_OUTPUT"
fi
