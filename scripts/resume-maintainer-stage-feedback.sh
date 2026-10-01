#!/usr/bin/env bash
# Read-only bounded Action history recovery. Never executes prior source or promotes a case.
set -euo pipefail
if [ "$#" -ne 7 ]; then
  echo 'usage: resume-maintainer-stage-feedback.sh BINARY KNOWLEDGE EVIDENCE CONTRACT CANDIDATE REPOSITORY CURRENT_RUN' >&2
  exit 2
fi
binary=$1 knowledge=$2 evidence=$3 contract=$4 candidate=$5 repository=$6 current_run=$7
[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && "$current_run" =~ ^[0-9]+$ ]] || exit 2
test -d "$evidence"
test ! -e "$evidence/stage-next.json"
calibration_sha=$(sha256sum "$evidence/stage-calibration.json" | cut -d' ' -f1)
common=(--feedback-stage-calibration --candidates "$knowledge/case_generation_candidates.jsonl"
  --candidate-id "$candidate" --downstream-plan "$evidence/queue/$candidate/next-actions.json"
  --stage-contract "$contract" --stage-calibration "$evidence/stage-calibration.json"
  --calibration-sha256 "$calibration_sha" --output "$evidence/stage-next.json")
# Transport failure is not a claim that no compatible predecessor exists.
gh api "repos/$repository/actions/workflows/maintainer-downstream-probe.yml/runs?branch=main&event=workflow_dispatch&status=success&per_page=10" > "$evidence/stage-history-runs.json"
jq -e '.workflow_runs | type == "array"' "$evidence/stage-history-runs.json" > /dev/null
while read -r previous_run; do
  scratch=$(mktemp -d "$(dirname "$evidence")/stage-history-XXXXXX")
  printf 'Inspect prior main run %s\n' "$previous_run"
  if ! gh run download "$previous_run" --repo "$repository" --name "maintainer-downstream-probe-$previous_run" --dir "$scratch"; then
    printf 'Prior artifact unavailable for run %s; not treated as accepted feedback\n' "$previous_run" >&2
    continue
  fi
  if [ ! -f "$scratch/stage-next.json" ] || [ ! -f "$scratch/stage-calibration.json" ] || [ ! -f "$scratch/stage-contract.json" ]; then
    printf 'Prior run %s has no complete stage feedback/capture/contract\n' "$previous_run"
    continue
  fi
  if ! cmp -s "$contract" "$scratch/stage-contract.json"; then
    printf 'Prior run %s owns another contract cut\n' "$previous_run"
    continue
  fi
  prior_sha=$(sha256sum "$scratch/stage-calibration.json" | cut -d' ' -f1)
  if "$binary" "${common[@]}" --previous-feedback-plan "$scratch/stage-next.json" \
      --previous-stage-calibration "$scratch/stage-calibration.json" --previous-calibration-sha256 "$prior_sha"; then
    # Copy only this predecessor's self-contained capture, not recursive history.
    cp "$scratch/stage-calibration.json" "$evidence/previous-stage-calibration.json"
    cp "$scratch/stage-contract.json" "$evidence/previous-stage-contract.json"
    cp "$scratch/stage-next.json" "$evidence/previous-stage-next.json"
    jq -n --arg run "$previous_run" --arg sha "$prior_sha" --arg repo "$repository" \
      '{schema:"agentlab.stage_history_selection.v1",previousRunId:$run,previousCalibrationSha256:$sha,repository:$repo,previousCaptureReconstructed:true}' > "$evidence/stage-history-selection.json"
    exit 0
  fi
  # The Rust verifier must fail before creating any output. A partial write is terminal.
  test ! -e "$evidence/stage-next.json"
  printf 'Prior run %s was rejected by independent reconstruction\n' "$previous_run"
done < <(jq -r --arg repo "$repository" --arg run "$current_run" '
  .workflow_runs[] | select((.id|tostring)!=$run and .head_branch=="main" and .event=="workflow_dispatch"
    and .status=="completed" and .conclusion=="success" and .head_repository.full_name==$repo
    and .path==".github/workflows/maintainer-downstream-probe.yml") | .id' "$evidence/stage-history-runs.json")
"$binary" "${common[@]}"
jq -n '{schema:"agentlab.stage_history_selection.v1",previousRunId:null,previousCaptureReconstructed:false,reason:"no compatible retained main capture in bounded history"}' > "$evidence/stage-history-selection.json"
