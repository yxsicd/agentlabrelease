#!/usr/bin/env bash
# Read-only continuation of one original source-only child; never model/write.
set -euo pipefail
[[ $# == 3 ]] || { echo 'usage: DISPATCH_DIRECTORY FRESH_OUTPUT EXACT_SOURCE_CHECKOUT' >&2; exit 2; }
dispatch=$1
output=$2
checkout=$3
test ! -e "$output" && test ! -L "$output"
mkdir "$output"
bash scripts/recover-maintainer-flywheel-run.sh "$dispatch" "$output/run-observation"
observed="$output/run-observation/observation.json"
if ! jq -e '.runVisible==true and .childCompletionVerified==true' "$observed" >/dev/null; then
  jq -n '{decision:"wait-original-child",knowledgeAdmissionAllowed:false,authorityWritePerformed:false}' > "$output/result.json"
  exit 0
fi
intent="$dispatch/dispatch-intent.json"
test "$(jq -r .workflow "$intent")" == maintainer-source-recipe-author.yml
repository=$(jq -er .repository "$intent")
run=$(jq -er .runId "$observed")
method=$(jq -er .methodRevision "$intent")
gh api "repos/$repository/actions/runs/$run/artifacts?per_page=100" > "$output/original-artifacts.json"
jq -e '.total_count<=100 and (.artifacts|length)==.total_count' "$output/original-artifacts.json" >/dev/null
jq --arg name "independent-source-suite-review-$run" \
  '[.artifacts[]|select(.name==$name and .expired==false)]' "$output/original-artifacts.json" > "$output/selected-artifacts.json"
test "$(jq length "$output/selected-artifacts.json")" == 1
artifact=$(jq -er '.[0].id' "$output/selected-artifacts.json")
digest=$(jq -er '.[0].digest' "$output/selected-artifacts.json")
[[ $digest =~ ^sha256:[0-9a-f]{64}$ ]]
python3 scripts/acquire-source-suite-review-input.py --repository "$repository" --run "$run" \
  --artifact "$artifact" --artifact-sha256 "${digest#sha256:}" --source-revision "$method" \
  --coordinator-request-id "$(jq -er .requestId "$intent")" \
  --artifact-kind review-feedback --output "$output/acquisition" > "$output/acquisition.stdout"
review="$output/acquisition/review-inputs"
if ! jq -e '.completed==true' "$review/agent/attempt-coordinator.json" >/dev/null; then
  jq -n '{decision:"retain-incomplete-or-rejected-review",knowledgeAdmissionAllowed:false,authorityWritePerformed:false}' > "$output/result.json"
  exit 0
fi
case "$(jq -er .selectedAttempt "$review/agent/attempt-coordinator.json")" in
  .) agent="$review/agent" ;;
  repair-attempt) agent="$review/agent/repair-attempt" ;;
  *) echo 'Unknown original selected attempt' >&2; exit 1 ;;
esac
verdict=$(jq -er .verdict "$agent/validation.json")
case "$verdict" in
  reject|unverified)
    jq -n --arg verdict "$verdict" '{decision:"retain-nonaccepted-review",verdict:$verdict,knowledgeAdmissionAllowed:false,authorityWritePerformed:false}' > "$output/result.json"
    exit 0 ;;
  accept) ;;
  *) echo 'Unknown native review verdict' >&2; exit 1 ;;
esac
gate=${AGENTLAB_FLYWHEEL_GATE:-target/debug/agentlab-maintainer-skill-flywheel}
"$gate" --verify-source-suite-review-feedback --source "$review/source/observations" \
  --quality-rubric "$review/rubric.json" --participant-evidence "$agent/evidence" \
  --review-response "$agent/response.json" --source-git-checkout "$checkout" \
  --feedback "$review/feedback" --output "$output/native-reception.json" \
  > "$output/native-reception.stdout" 2> "$output/native-reception.stderr"
response_sha=$(shasum -a 256 "$agent/response.json" | cut -d ' ' -f1)
jq -e --arg sha "$response_sha" '.schema=="agentlab.independent_review_feedback_reception.v1" and
  .originalResponseSha256==$sha and .originalResponseBytesVerified==true and
  .responseContentVerified==true and .recordedCompletionVerified==true and
  .originalRawSourceBytesVerified==true and .nativeOperationalExportReconstructed==true and
  .sourceGitBindingVerified==true and .candidateReadyForObservationImport==true and
  .authorityWritePerformed==false' "$output/native-reception.json" >/dev/null
jq -s -e '.[0]==.[1]' "$output/native-reception.json" "$output/native-reception.stdout" >/dev/null
jq -n '{decision:"native-feedback-received-operational-return-required",nativeReceptionVerified:true,knowledgeAdmissionAllowed:false,authorityWritePerformed:false,closedLoopQualified:false}' > "$output/result.json"
jq '.' "$output/result.json"
