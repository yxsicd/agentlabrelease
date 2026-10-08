#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 5 ]]; then
  echo "usage: $0 KNOWLEDGE RUN_ROOT REPOSITORY ITERATIONS PI" >&2
  exit 2
fi

knowledge=$1
run_root=$2
repository=$3
iterations=$4
pi=$5
gate=${AGENTLAB_FLYWHEEL_GATE:-${CARGO_TARGET_DIR:-target}/debug/agentlab-maintainer-skill-flywheel}
scope_batch_size=${AGENTLAB_SCOPE_BATCH_SIZE:-1}
max_iterations=${AGENTLAB_MAX_ITERATIONS:-3}
shadow_sample=${AGENTLAB_SHADOW_SAMPLE:-0}

if [[ ! -x "$gate" || ! -x "$pi" ]]; then
  echo "verified Pi and Flywheel gate executables are required" >&2
  exit 2
fi
if [[ ! $scope_batch_size =~ ^[1-4]$ || ! $shadow_sample =~ ^[01]$ ||
      ! $max_iterations =~ ^[1-9][0-9]*$ || $max_iterations -gt 64 ]]; then
  echo "invalid scope, shadow or iteration budget" >&2
  exit 2
fi
if [[ $iterations == converge ]]; then
  : "${AGENTLAB_SKILLSGIT_ROOT:?converge requires an explicit SkillsGit root}"
  : "${AGENTLAB_SKILLSGIT_REVISION:?converge requires an exact SkillsGit revision}"
elif [[ ! $iterations =~ ^[1-9][0-9]*$ || $iterations -gt $max_iterations ]]; then
  echo "iterations must be an integer from 1 through $max_iterations" >&2
  exit 2
fi
if [[ -n ${AGENTLAB_SKILLSGIT_ROOT:-} ]]; then
  : "${AGENTLAB_SKILLSGIT_REVISION:?required when AGENTLAB_SKILLSGIT_ROOT is set}"
fi
if [[ ! -d "$knowledge" || -L "$knowledge" || $run_root != /* ||
      -e "$run_root" || -L "$run_root" ]]; then
  echo "an existing knowledge cut and a fresh absolute run root are required" >&2
  exit 2
fi
knowledge_real=$(cd "$knowledge" && pwd -P)
project_real=$(pwd -P)
run_parent=$(cd "$(dirname "$run_root")" && pwd -P)
run_name=$(basename "$run_root")
[[ $run_name =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$ ]] || exit 2
run_root="$run_parent/$run_name"
for output in "$run_root" "$run_parent/sources"; do
  case "$output/" in
    "$knowledge_real/"*|"$project_real/"*)
      echo "run and source outputs must be outside the input cut and public checkout" >&2
      exit 2;;
  esac
done
sources_root="$run_parent/sources"
if [[ -L "$sources_root" || ( -e "$sources_root" && ! -d "$sources_root" ) ]]; then
  echo "source cache must be a real directory, not a symlink" >&2
  exit 2
fi
# A cached checkout may not redirect Git's forced checkout into another cut.
for source_entry in "$sources_root"/* "$sources_root"/.[!.]*; do
  if [[ -L "$source_entry" || -L "$source_entry/.git" ||
        ( -e "$source_entry/.git" && ! -d "$source_entry/.git" ) ]]; then
    echo "source checkout or Git metadata redirects outside the owned cache" >&2
    exit 2
  fi
done
if [[ -n ${AGENTLAB_SKILLSGIT_ROOT:-} ]]; then
  python3 scripts/materialize-skillsgit-maintainer-tree.py \
    --knowledge "$knowledge" --repository "$repository" \
    --skillsgit-root "$AGENTLAB_SKILLSGIT_ROOT" \
    --skillsgit-revision "$AGENTLAB_SKILLSGIT_REVISION" --check-inputs-only
fi

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
export AGENTLAB_SCOPE_BATCH_SIZE=$scope_batch_size
export AGENTLAB_FLYWHEEL_GATE=$gate
export AGENTLAB_FLYWHEEL_BIN=$gate

mkdir "$run_root"
# Admission precedes every model call, exactly as in the public Action.
python3 scripts/maintainer-skill-tablegit.py preflight \
  --base "$knowledge" --receipt "$run_root/tablegit-preflight-receipt.json"
"$gate" --resolve-latest-assessment \
  --base "$knowledge" --output "$run_root/durable-initial-assessment.json"
assessment=$(jq -r '.assessmentPath' "$run_root/durable-initial-assessment.json")
test -n "$assessment"
python3 examples/maintainer-knowledge-gate/agent_flywheel.py plan \
  --knowledge "$knowledge" --assessment "$assessment" --repository "$repository" \
  --output "$run_root/convergence-plan.json"

converging=false
if [[ $iterations == converge ]]; then
  converging=true
  eligible=$(jq -r '.summary.eligible' "$run_root/convergence-plan.json")
  if [[ $eligible -eq 0 ]]; then
    echo "repository has no eligible L1 scope to advance" >&2
    exit 3
  fi
  iterations=$(((eligible + scope_batch_size - 1) / scope_batch_size))
  export AGENTLAB_MAX_ITERATIONS=64
fi

scripts/run-maintainer-skill-agent-loop.sh \
  "$knowledge" "$run_root" "$repository" "$iterations" "$pi"

snapshot="$run_root/loop/knowledge-$iterations"
test -f "$snapshot/stage-manifest.json"
"$gate" --resolve-latest-assessment \
  --base "$snapshot" --output "$run_root/durable-final-assessment.json"
final_assessment=$(jq -r '.assessmentPath' "$run_root/durable-final-assessment.json")
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

committed_knowledge="$run_root/committed-knowledge"
python3 scripts/maintainer-skill-tablegit.py sync \
  --base "$knowledge" --snapshot "$snapshot" --export "$committed_knowledge" \
  --receipt "$run_root/tablegit-sync-receipt.json" \
  --run-id "$GITHUB_RUN_ID" --github-repository "$GITHUB_REPOSITORY" \
  "${producer_args[@]}"

# Third-ring sampling has its own explicit model budget. It cannot undo an
# already committed first/two-ring gain or erase its failure diagnostics.
shadow_exit=0
shadow_decision=not-requested
if [[ $shadow_sample == 1 ]]; then
  if scripts/run-case-generation-shadow.sh "$committed_knowledge" "$run_root" "$pi" \
      > "$run_root/shadow-stdout.log" 2> "$run_root/shadow-stderr.log"; then
    shadow_decision=completed
  else
    shadow_exit=$?
    shadow_decision=failed
  fi
fi
jq -n --arg decision "$shadow_decision" --argjson exitCode "$shadow_exit" \
  --arg receipt "$run_root/shadow-case-generation/shadow-receipt.json" \
  '{decision:$decision,exitCode:$exitCode,qualified:false,
    verdictReceipt: (if $decision == "completed" then $receipt else null end)}' > "$run_root/shadow-status.json"
# Reconsume the real committed readback, not only the local proposal.
"$gate" --resolve-latest-assessment --base "$committed_knowledge" \
  --output "$run_root/durable-committed-assessment.json"
committed_assessment=$(jq -er '.assessmentPath' "$run_root/durable-committed-assessment.json")
python3 examples/maintainer-knowledge-gate/agent_flywheel.py plan \
  --knowledge "$committed_knowledge" --assessment "$committed_assessment" \
  --repository "$repository" --output "$run_root/committed-next-round-plan.json"
if [[ -d "$committed_knowledge/construction-plans" &&
      -f "$committed_knowledge/case_generation_candidates.jsonl" ]]; then
  bash scripts/plan-maintainer-downstream.sh \
    "$committed_knowledge" . "$run_root/downstream"
else
  mkdir "$run_root/downstream"
  jq -n '{decision:"blocked-case-inputs-not-in-committed-cut",closedLoopQualified:false}' \
    > "$run_root/downstream/summary.json"
fi

materialization_file="$run_root/materialization.json"
printf '{}\n' > "$materialization_file"
if [[ -n ${AGENTLAB_SKILLSGIT_ROOT:-} ]]; then
  : "${AGENTLAB_SKILLSGIT_REVISION:?required when AGENTLAB_SKILLSGIT_ROOT is set}"
  python3 scripts/materialize-skillsgit-maintainer-tree.py \
    --knowledge "$committed_knowledge" --repository "$repository" \
    --skillsgit-root "$AGENTLAB_SKILLSGIT_ROOT" \
    --skillsgit-revision "$AGENTLAB_SKILLSGIT_REVISION" \
    --output "$run_root/materialized-maintainer-tree" \
    > "$materialization_file"
fi

jq -n \
  --slurpfile loop "$run_root/loop/loop-receipt.json" \
  --slurpfile tablegit "$run_root/tablegit-sync-receipt.json" \
  --slurpfile admission "$run_root/tablegit-preflight-receipt.json" \
  --slurpfile shadow "$run_root/shadow-status.json" \
  --slurpfile downstream "$run_root/downstream/summary.json" \
  --arg committedKnowledge "$committed_knowledge" \
  --slurpfile materialization "$materialization_file" \
  --slurpfile convergencePlan "$run_root/convergence-plan.json" \
  --slurpfile convergenceReport "$run_root/convergence-report.json" \
  --slurpfile nextRound "$run_root/committed-next-round-plan.json" \
  '{schema:"agentlab.maintainer_skill_local_flywheel_receipt.v1",
    loop:$loop[0],tableGit:$tablegit[0],authorityAdmission:$admission[0],
    committedKnowledge:$committedKnowledge,inputCutPreserved:true,
    shadow:$shadow[0],downstream:$downstream[0],closedLoopQualified:false,
    materialization:$materialization[0],convergencePlan:$convergencePlan[0],
    convergenceReport:$convergenceReport[0],nextRound:$nextRound[0]}' \
  > "$run_root/local-flywheel-receipt.json"
