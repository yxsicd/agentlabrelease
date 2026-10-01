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
while IFS= read -r plan; do
  id=$(jq -er '.candidateId' "$plan")
  # Never let a business identifier become a directory traversal.
  [[ "$id" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo 'Unsafe candidate id' >&2; exit 1; }
  test ! -e "$output/$id"
  mkdir "$output/$id"
  python3 examples/maintainer-knowledge-gate/shadow_construction_readiness.py \
    --knowledge "$knowledge" --candidate-id "$id" --plan "$plan" \
    --evidence-root "$evidence_root" --output "$output/$id/readiness.json"
  command=("$router" --plan-downstream --readiness "$output/$id/readiness.json" --output "$output/$id/next-actions.json")
  if [[ -n "$previous" && -f "$previous/$id/next-actions.json" ]]; then
    command+=(--previous-plan "$previous/$id/next-actions.json")
  fi
  "${command[@]}"
  count=$((count + 1))
done < <(find "$knowledge/construction-plans" -type f -name '*.json' | LC_ALL=C sort)
test "$count" -gt 0
# Candidates without construction plans remain visible; do not silently drop
# them or invent plans/qualification from the absence of downstream artifacts.
jq -s '.' "$output"/*/next-actions.json > "$output/plans.json"
"$router" --summarize-downstream --candidates "$knowledge/case_generation_candidates.jsonl" \
  --plans "$output/plans.json" --output "$output/summary.json"
