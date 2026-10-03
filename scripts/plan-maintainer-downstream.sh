#!/usr/bin/env bash
# Read-only bridge from independently assessed candidate plans to the Rust router.
set -euo pipefail
if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo 'usage: KNOWLEDGE EVIDENCE_ROOT FRESH_OUTPUT [PREVIOUS_OUTPUT]' >&2
  exit 2
fi
knowledge=$1
evidence_root=$2
output=$3
previous=${4:-}
router=${AGENTLAB_FLYWHEEL_BIN:-target/debug/agentlab-maintainer-skill-flywheel}
test ! -e "$output"
test ! -L "$output"
mkdir -p "$output"
count=0
partial_plans=()
while IFS= read -r plan; do
  id=$(jq -er '.candidateId' "$plan")
  # Never let a business identifier become a directory traversal.
  [[ "$id" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo 'Unsafe candidate id' >&2; exit 1; }
  test ! -e "$output/$id"
  mkdir "$output/$id"
  readiness_command=(python3 examples/maintainer-knowledge-gate/shadow_construction_readiness.py
    --knowledge "$knowledge" --candidate-id "$id" --plan "$plan"
    --evidence-root "$evidence_root" --output "$output/$id/readiness.json")
  # Explicit construction selection, independently reconstructed by the native gate.
  if [[ -n "${AGENTLAB_CONSTRUCTION_BINDING_ROOT:-}" ]]; then
    binding_profile="$AGENTLAB_CONSTRUCTION_BINDING_ROOT/profiles/$id.json"
    if [[ -e "$binding_profile" || -L "$binding_profile" ]]; then
      test -f "$binding_profile" && test ! -L "$binding_profile"
      jq -e --arg id "$id" '
        keys == ["candidateId","editBoundary","reviewed","schema","sourceWorktree"] and
        .schema == "agentlab.construction_path_binding_profile.v1" and
        .reviewed == true and .candidateId == $id and
        (.sourceWorktree | type == "string" and startswith("/")) and
        (.editBoundary | type == "string" and startswith("/"))' "$binding_profile" >/dev/null
      readiness_command+=(--source-worktree "$(jq -er .sourceWorktree "$binding_profile")"
        --edit-boundary "$(jq -er .editBoundary "$binding_profile")" --flywheel-tool "$router")
    fi
  fi
  "${readiness_command[@]}"
  command=("$router" --plan-downstream --readiness "$output/$id/readiness.json" --output "$output/$id/next-actions.json")
  if [[ -n "$previous" && -f "$previous/$id/next-actions.json" ]]; then
    command+=(--previous-plan "$previous/$id/next-actions.json")
  fi
  "${command[@]}"
  # Opt-in retained-observation lane. Its actions never replace formal gates.
  if [[ -n "${AGENTLAB_PARTIAL_CALIBRATION_ROOT:-}" ]]; then
    partial_profile="$AGENTLAB_PARTIAL_CALIBRATION_ROOT/profiles/$id.json"
    if [[ -f "$partial_profile" ]]; then
      partial_command=("$router" --feedback-partial-calibration --readiness "$output/$id/readiness.json"
        --partial-profile "$partial_profile" --capture-root "$AGENTLAB_PARTIAL_CALIBRATION_ROOT"
        --output "$output/$id/scoped-next-actions.json")
      if [[ -n "$previous" && -f "$previous/$id/scoped-next-actions.json" ]]; then
        partial_command+=(--previous-feedback-plan "$previous/$id/scoped-next-actions.json")
      fi
      "${partial_command[@]}"
      partial_plans+=("$output/$id/scoped-next-actions.json")
    fi
  fi
  count=$((count + 1))
done < <(find "$knowledge/construction-plans" -type f -name '*.json' | LC_ALL=C sort)
test "$count" -gt 0
# Candidates without construction plans remain visible; do not silently drop
# them or invent plans/qualification from the absence of downstream artifacts.
jq -s '.' "$output"/*/next-actions.json > "$output/plans.json"
"$router" --summarize-downstream --candidates "$knowledge/case_generation_candidates.jsonl" \
  --plans "$output/plans.json" --output "$output/summary.json"
if [[ ${#partial_plans[@]} -gt 0 ]]; then
  jq -s --slurpfile formal "$output/summary.json" '
    {schema:"agentlab.partial_calibration_batch.v1",planCount:length,
     activeCandidateIds:[.[] | select(.schedulingAllowed == true) | .candidateId as $id |
       select(($formal[0].retainedHistoricalCandidateIds | index($id)) == null) | $id],
     qualified:false,automaticPromotion:false,agentExecutionPerformed:false,authorityWritePerformed:false}' \
    "${partial_plans[@]}" > "$output/partial-summary.json"
fi
