#!/usr/bin/env bash
set -euo pipefail

role=$1
case "$role" in
  reference) project=/home/huawei/agentlab-source-builds/payment-feedback-165bcbd-caseperf-reference-v1 ;;
  baseline-task-start) project=/home/huawei/agentlab-source-builds/payment-feedback-165bcbd-caseperf-baseline-v1 ;;
  meaningful-wrong) project=/home/huawei/agentlab-source-builds/payment-feedback-165bcbd-caseperf-wrong-v1 ;;
  *) echo invalid-role >&2; exit 2 ;;
esac

root=/home/huawei/.agentlab/evidence/purchase-data-case-performance-matrix-v2
role_root="$root/$role"
tools=/home/huawei/commandline-tools-26.0.0.821
emulator="$tools/bin/Emulator"
hdc="$tools/sdk/default/openharmony/toolchains/hdc"
image_root=/home/huawei/HarmonyOS-Emulator/images
instance_path=/home/huawei/HarmonyOS-Emulator/instances
instance=codex_phone_7
port=10100
target=127.0.0.1:10100
runner="$root/run-harmony-instrument-test.py"
normalizer="$root/summarize-smartperf.py"
policy="$root/performance-policy.json"
workload="$root/profile-workload.tsv"
app_hap="$project/entry/build/default/outputs/default/entry-default-unsigned.hap"
test_hap="$project/entry/build/default/outputs/ohosTest/entry-ohosTest-unsigned.hap"
source_path="$project/entry/src/main/ets/common/PurchaseFinalizationPolicy.ets"
test_path="$project/entry/src/ohosTest/ets/test/PurchaseFinalizationPolicy.test.ets"
source_set=cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2
environment=hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7

test ! -e "$role_root"
mkdir -p "$role_root"
id >"$role_root/runtime-identity.txt"
app_sha=$(sha256sum "$app_hap" | awk '{print $1}')
test_sha=$(sha256sum "$test_hap" | awk '{print $1}')
source_sha=$(sha256sum "$source_path" | awk '{print $1}')
test_source_sha=$(sha256sum "$test_path" | awk '{print $1}')
started=false

bounded_hdc() {
  timeout --signal=TERM --kill-after=2s 30s "$hdc" "$@"
}

target_connected() {
  bounded_hdc list targets 2>/dev/null | awk -v target="$target" '$1 == target { found=1 } END { exit(found ? 0 : 1) }'
}

start_verified_app() {
  local out=$1
  local ordinal=$2
  bounded_hdc -t "$target" shell uitest uiInput swipe 630 2400 630 600 1000 >"$out/unlock-$ordinal.log" 2>&1
  sleep 2
  bounded_hdc -t "$target" shell aa start -a EntryAbility -b xxx.xxx.xxx >"$out/app-start-$ordinal.log" 2>&1
  grep -F "start ability successfully" "$out/app-start-$ordinal.log" >/dev/null
  local attempt
  for attempt in {1..15}; do
    bounded_hdc -t "$target" shell ps -A -o PID,NAME >"$out/process-$ordinal-all.txt" 2>&1
    if awk '$2 == "xxx.xxx.xxx" { found=1; print } END { exit(found ? 0 : 1) }' "$out/process-$ordinal-all.txt" >"$out/process-$ordinal.txt"; then
      return 0
    fi
    sleep 1
  done
  echo launched-bundle-has-no-verified-process >&2
  return 1
}

port_listening() {
  (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
}

stop_emulator() {
  local log=$1
  "$emulator" -stop "$instance" -instancePath "$instance_path" >>"$log" 2>&1
  local deadline=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! port_listening; then
      started=false
      return 0
    fi
    sleep 1
  done
  echo emulator-stop-timeout >>"$log"
  return 1
}

cleanup() {
  local rc=$?
  if [ "$started" = true ]; then
    stop_emulator "$role_root/emergency-stop.log" || true
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

python3 - "$role_root" "$role" "$project" "$source_sha" "$test_source_sha" "$app_sha" "$test_sha" <<'PY'
import hashlib, json, pathlib, subprocess, sys
out, role, project, source_sha, test_source_sha, app_sha, test_sha = sys.argv[1:]
project_path = pathlib.Path(project)
value = {
    "schema": "agentlab.purchase_data_case_performance_role.v1",
    "role": role,
    "project": project,
    "candidateRevision": subprocess.check_output(["git", "-C", project, "rev-parse", "HEAD"], text=True).strip(),
    "sourceSha256": source_sha,
    "testSourceSha256": test_source_sha,
    "appHapSha256": app_sha,
    "testHapSha256": test_sha,
    "performancePolicySha256": hashlib.sha256((pathlib.Path(out).parent / "performance-policy.json").read_bytes()).hexdigest(),
    "profileWorkloadSha256": hashlib.sha256((pathlib.Path(out).parent / "profile-workload.tsv").read_bytes()).hexdigest(),
    "automaticPromotion": False,
}
(pathlib.Path(out) / "role-metadata.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY

run_one() {
  local label=$1
  local out="$role_root/$label"
  mkdir -p "$out/tests"
  "$emulator" -start "$instance" -instancePath "$instance_path" -imageRoot "$image_root" -bootMode coldboot -noWindow -hdcPort "$port" >"$out/emulator-start.log" 2>&1 &
  echo $! >"$out/emulator-launcher.pid"
  started=true
  local deadline=$((SECONDS + 240))
  until target_connected; do
    [ "$SECONDS" -lt "$deadline" ] || { echo emulator-target-timeout >&2; return 1; }
    sleep 2
  done

  bounded_hdc -t "$target" install -r "$app_hap" >"$out/install-app.log" 2>&1
  bounded_hdc -t "$target" install -r "$test_hap" >"$out/install-test.log" 2>&1
  : >"$out/profile-workload-actions.tsv"
  start_verified_app "$out" 0
  printf '%s\tstart-app\tEntryAbility,xxx.xxx.xxx\n' 0 >>"$out/profile-workload-actions.tsv"
  python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())' >"$out/profile-window-started-at.txt"
  (
    set +e
    timeout --signal=TERM --kill-after=5s 90s "$hdc" -t "$target" shell SP_daemon -N 48 -PKG xxx.xxx.xxx -c -g -t -p -f -r -net -snapshot -d >"$out/smartperf.txt" 2>&1
    rc=$?
    python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())' >"$out/profile-window-finished-at.txt"
    exit "$rc"
  ) &
  local smartperf_pid=$!
  local ordinal
  for ordinal in {1..6}; do
    python3 "$runner" \
      --project-root "$project" \
      --case-id "purchase-data-caseperf-$role-v2" \
      --source-set-sha256 "$source_set" \
      --hdc "$hdc" \
      --target "$target" \
      --app-hap "$app_hap" \
      --test-hap "$test_hap" \
      --bundle xxx.xxx.xxx \
      --module entry_test \
      --runner OpenHarmonyTestRunner \
      --skip-install \
      --timeout-seconds 300 \
      --case-timeout-ms 120000 \
      --output-dir "$out/tests/$ordinal" \
      >"$out/tests/$ordinal.stdout.log" 2>"$out/tests/$ordinal.stderr.log"
    printf '%s\trepeat-ohostest\t8,OpenHarmonyTestRunner\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
    start_verified_app "$out" "$ordinal"
    printf '%s\tstart-app\tEntryAbility,xxx.xxx.xxx\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
  done
  wait "$smartperf_pid"

  python3 "$normalizer" \
    --input "$out/smartperf.txt" \
    --task-id purchase-data-finalization-ee2bc87594f1 \
    --source-identity "artifact-sha256:$app_sha" \
    --run-id "$role-$label" \
    --environment-identity "$environment" \
    --minimum-samples 48 \
    --performance-policy "$policy" \
    --profile-workload "$workload" \
    --output "$out/smartperf-summary.json"

  python3 - "$out" "$role" "$source_sha" "$test_source_sha" "$app_sha" "$test_sha" <<'PY'
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[1])
role, source_sha, test_source_sha, app_sha, test_sha = sys.argv[2:]
started = (out / "profile-window-started-at.txt").read_text().strip()
finished = (out / "profile-window-finished-at.txt").read_text().strip()
repeats = []
for receipt_path in sorted((out / "tests").glob("*/receipt.json")):
    receipt = json.loads(receipt_path.read_text())
    report_path = receipt_path.parent / receipt["report"]["path"]
    report = json.loads(report_path.read_text())
    expected = {"error": 0, "failure": 0, "ignore": 0, "pass": 8, "total": 8}
    if receipt.get("passed") is not True or receipt.get("packagesInstalled") is not False:
        raise SystemExit(f"functional receipt failed: {receipt_path}")
    if report.get("passed") is not True or report.get("counts") != expected:
        raise SystemExit(f"functional report failed: {report_path}")
    if not (started <= receipt["startedAt"] <= receipt["finishedAt"] <= finished):
        raise SystemExit(f"functional repeat escaped profile window: {receipt_path}")
    repeats.append({
        "ordinal": int(receipt_path.parent.name),
        "receiptSha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "nativeReportSha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "counts": report["counts"],
    })
summary_path = out / "smartperf-summary.json"
summary = json.loads(summary_path.read_text())
if len(repeats) != 6 or summary.get("profileValid") is not True or summary.get("sampleCount") != 48:
    raise SystemExit("profile coverage differs")
manifest = {
    "schema": "agentlab.purchase_data_case_performance_run.v1",
    "status": "functionally-passed-profile-captured",
    "role": role,
    "runId": out.name,
    "candidateRevision": "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8",
    "sourceSha256": source_sha,
    "testSourceSha256": test_source_sha,
    "sourceSetSha256": "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2",
    "appHapSha256": app_sha,
    "testHapSha256": test_sha,
    "environmentIdentity": "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7",
    "functionalRepeatCount": len(repeats),
    "functionalTestCountPerRepeat": 8,
    "functionalVerdictCount": 48,
    "functionalRepeats": repeats,
    "functionalRepeatsWithinProfileWindow": True,
    "profileSampleCount": 48,
    "profileWindowStartedAt": started,
    "profileWindowFinishedAt": finished,
    "smartPerfSummarySha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    "performancePolicySha256": hashlib.sha256((out.parent.parent / "performance-policy.json").read_bytes()).hexdigest(),
    "profileWorkloadSha256": hashlib.sha256((out.parent.parent / "profile-workload.tsv").read_bytes()).hexdigest(),
    "profileWorkloadActionsSha256": hashlib.sha256((out / "profile-workload-actions.tsv").read_bytes()).hexdigest(),
    "packagesInstalledInsideProfileWindow": False,
    "caseBoundFunction": "planPurchaseFinalization",
    "caseBoundTest": "purchaseFinalizationPerformanceWorkload",
    "caseBoundIterationCountPerRepeat": 5000,
    "controlledVariantNotAgentRun": role != "reference",
    "automaticPromotion": False,
}
(out / "run-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY

  stop_emulator "$out/emulator-stop.log"
  wait "$(cat "$out/emulator-launcher.pid")" || true
  timeout 5s "$hdc" list targets >"$out/final-hdc-targets.txt"
  ps -eo pid,args | grep -E '[E]mulator|[q]emu-system' >"$out/final-emulator-processes.txt" || true
  test ! -s "$out/final-emulator-processes.txt"
}

run_one run-1
run_one run-2
trap - EXIT INT TERM
printf '%s\n' "$role_root"
