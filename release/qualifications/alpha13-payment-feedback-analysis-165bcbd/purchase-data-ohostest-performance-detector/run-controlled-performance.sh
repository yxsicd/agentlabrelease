#!/usr/bin/env bash
set -euo pipefail

root=/home/huawei/.agentlab/evidence/purchase-data-ohostest-performance-calibration-ee2bc87-v2
tools=/home/huawei/commandline-tools-26.0.0.821
emulator="$tools/bin/Emulator"
hdc="$tools/sdk/default/openharmony/toolchains/hdc"
image_root=/home/huawei/HarmonyOS-Emulator/images
instance_path=/home/huawei/HarmonyOS-Emulator/instances
instance=codex_phone_7
port=10100
target=127.0.0.1:10100
project=/home/huawei/agentlab-source-builds/payment-feedback-165bcbd-ohostest-perfwrong-v1
app_hap="$project/entry/build/default/outputs/default/entry-default-unsigned.hap"
test_hap="$project/entry/build/default/outputs/ohosTest/entry-ohosTest-unsigned.hap"
runner="$root/run-harmony-instrument-test.py"
normalizer="$root/summarize-smartperf.py"
comparator="$root/compare-smartperf.py"
policy="$root/performance-policy.json"
workload="$root/profile-workload.tsv"
source_set=cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2
base_app_sha=dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073
app_sha=7bf92151da1a85ba3291c4997d5f4e291cc38833f5e5dbef72a4b2e42ec2a7b3
test_sha=2a9ee43900d7f4813b896909bc40b192319f7db79df117f4e4243b56278d53b5
base_source_file_sha=daf0f32975c9c9d05174995b165669d3b19388df03f2d6b8284131cab9c1aea0
candidate_source_file_sha=99c0dd5acdf45973401cd8fefd7bc9daa055af4a12342ae8d0c3656c34f3924f
environment=hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7
started=false

bounded_hdc() {
  timeout --signal=TERM --kill-after=2s 30s "$hdc" "$@"
}

target_connected() {
  bounded_hdc list targets 2>/dev/null | awk -v target="$target" '$1 == target { found = 1 } END { exit(found ? 0 : 1) }'
}

start_verified_app() {
  local out=$1
  local ordinal=$2
  bounded_hdc -t "$target" shell uitest uiInput swipe 630 2400 630 600 1000 >"$out/unlock-$ordinal.log" 2>&1
  sleep 2
  bounded_hdc -t "$target" shell aa start -a EntryAbility -b xxx.xxx.xxx >"$out/app-start-$ordinal.log" 2>&1
  grep -F "start ability successfully" "$out/app-start-$ordinal.log" >/dev/null
  local attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    bounded_hdc -t "$target" shell ps -A -o PID,NAME >"$out/process-$ordinal-all.txt" 2>&1
    if awk '$2 == "xxx.xxx.xxx" { found = 1; print } END { exit(found ? 0 : 1) }' "$out/process-$ordinal-all.txt" >"$out/process-$ordinal.txt"; then
      return 0
    fi
    sleep 1
  done
  echo "launched bundle has no verified process" >&2
  return 1
}

port_listening() {
  (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
}

stop_emulator() {
  local log=$1
  if "$emulator" -stop "$instance" -instancePath "$instance_path" >>"$log" 2>&1; then
    local deadline=$((SECONDS + 45))
    while [ "$SECONDS" -lt "$deadline" ]; do
      if ! port_listening; then
        started=false
        return 0
      fi
      sleep 1
    done
  fi
  echo "emulator stop failed or HDC port stayed bound" >>"$log"
  return 1
}

cleanup() {
  local rc=$?
  if [ "$started" = true ]; then
    stop_emulator "$root/emergency-stop.log" || true
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

[ "$(sha256sum "$app_hap" | awk '{print $1}')" = "$app_sha" ]
[ "$(sha256sum "$test_hap" | awk '{print $1}')" = "$test_sha" ]
[ "$(sha256sum "$project/entry/src/main/ets/pages/EntryPage.ets" | awk '{print $1}')" = "$candidate_source_file_sha" ]
[ "$(git -C "$project" rev-parse HEAD)" = ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8 ]
[ "$(git -C "$project" status --short)" = " M entry/src/main/ets/pages/EntryPage.ets" ]
for path in "$root/wrong-run-1" "$root/wrong-run-2" "$root/wrong-comparison-1.json" "$root/wrong-comparison-2.json" "$root/controlled-performance-calibration.json"; do
  [ ! -e "$path" ] || { echo "refusing to overwrite retained calibration evidence: $path" >&2; exit 1; }
done

run_one() {
  local label=$1
  local out="$root/$label"
  mkdir -p "$out/tests"
  "$emulator" -start "$instance" -instancePath "$instance_path" -imageRoot "$image_root" -bootMode coldboot -noWindow -hdcPort "$port" >"$out/emulator-start.log" 2>&1 &
  echo $! >"$out/emulator-launcher.pid"
  started=true
  local deadline=$((SECONDS + 240))
  until target_connected; do
    [ "$SECONDS" -lt "$deadline" ] || { echo "emulator target timeout" >&2; return 1; }
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
    smartperf_rc=$?
    python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())' >"$out/profile-window-finished-at.txt"
    exit "$smartperf_rc"
  ) &
  local smartperf_pid=$!
  for ordinal in 1 2 3 4 5 6; do
    python3 "$runner" \
      --project-root "$project" \
      --case-id purchase-data-finalization-candidate-clean-v1 \
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
      --case-timeout-ms 60000 \
      --output-dir "$out/tests/$ordinal" >"$out/tests/$ordinal.stdout.log" 2>"$out/tests/$ordinal.stderr.log"
    printf '%s\trepeat-ohostest\t7,OpenHarmonyTestRunner\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
    start_verified_app "$out" "$ordinal"
    printf '%s\tstart-app\tEntryAbility,xxx.xxx.xxx\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
  done
  wait "$smartperf_pid"

  python3 "$normalizer" \
    --input "$out/smartperf.txt" \
    --task-id purchase-data-finalization-ee2bc87594f1 \
    --source-identity "artifact-sha256:$app_sha" \
    --run-id "$label" \
    --environment-identity "$environment" \
    --minimum-samples 48 \
    --performance-policy "$policy" \
    --profile-workload "$workload" \
    --output "$out/smartperf-summary.json"

  python3 - "$out" <<'PY'
import hashlib, json, pathlib, sys
run = pathlib.Path(sys.argv[1])
root = run.parent
started = (run / "profile-window-started-at.txt").read_text().strip()
finished = (run / "profile-window-finished-at.txt").read_text().strip()
receipts = []
for path in sorted((run / "tests").glob("*/receipt.json")):
    receipt = json.loads(path.read_text())
    report_path = path.parent / receipt["report"]["path"]
    report = json.loads(report_path.read_text())
    if receipt.get("passed") is not True or receipt.get("packagesInstalled") is not False:
        raise SystemExit(f"functional repeat failed: {path}")
    if report.get("passed") is not True or report.get("counts") != {"error": 0, "failure": 0, "ignore": 0, "pass": 7, "total": 7}:
        raise SystemExit(f"native report failed: {report_path}")
    if not (started <= receipt["startedAt"] <= receipt["finishedAt"] <= finished):
        raise SystemExit(f"functional repeat escaped profile window: {path}")
    receipts.append({
        "ordinal": int(path.parent.name),
        "receiptSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "nativeReportSha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "counts": report["counts"],
    })
summary_path = run / "smartperf-summary.json"
summary = json.loads(summary_path.read_text())
if summary.get("profileValid") is not True or summary.get("sampleCount") != 48 or len(receipts) != 6:
    raise SystemExit("candidate profile is incomplete")
manifest = {
    "schema": "agentlab.purchase_data_ohostest_performance_variant_run.v1",
    "status": "passed",
    "runId": run.name,
    "role": "controlled-meaningful-wrong-not-agent-not-gold",
    "baseRevision": "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8",
    "sourceSetSha256": "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2",
    "baselineAppHapSha256": "dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073",
    "appHapSha256": "7bf92151da1a85ba3291c4997d5f4e291cc38833f5e5dbef72a4b2e42ec2a7b3",
    "testHapSha256": "2a9ee43900d7f4813b896909bc40b192319f7db79df117f4e4243b56278d53b5",
    "controlledMutation": {
        "id": "retain-64m-and-bounded-cpu-entry-page-v2",
        "kind": "combined-cpu-memory",
        "bytes": 67108864,
        "intervalMs": 500,
        "busyWindowMs": 400,
        "sourcePath": "entry/src/main/ets/pages/EntryPage.ets",
        "baseSourceFileSha256": "daf0f32975c9c9d05174995b165669d3b19388df03f2d6b8284131cab9c1aea0",
        "candidateSourceFileSha256": "99c0dd5acdf45973401cd8fefd7bc9daa055af4a12342ae8d0c3656c34f3924f",
    },
    "environmentIdentity": "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7",
    "functionalRepeats": receipts,
    "functionalRepeatCount": len(receipts),
    "functionalRepeatsWithinProfileWindow": True,
    "profileSampleCount": 48,
    "profileWindowStartedAt": started,
    "profileWindowFinishedAt": finished,
    "smartPerfSummarySha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    "performancePolicySha256": hashlib.sha256((root / "performance-policy.json").read_bytes()).hexdigest(),
    "profileWorkloadSha256": hashlib.sha256((root / "profile-workload.tsv").read_bytes()).hexdigest(),
    "profileWorkloadActionsSha256": hashlib.sha256((run / "profile-workload-actions.tsv").read_bytes()).hexdigest(),
    "performanceDetectorCalibrationOnly": True,
    "liveVendorIapExecuted": False,
    "realDeviceExecuted": False,
    "absolutePowerThermalAuthority": False,
    "automaticPromotion": False,
}
(run / "run-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY

  stop_emulator "$out/emulator-stop.log"
  [ ! -e "/proc/$(cat "$out/emulator-launcher.pid")" ] || wait "$(cat "$out/emulator-launcher.pid")" || true
}

run_one wrong-run-1
run_one wrong-run-2

python3 "$comparator" --baseline "$root/run-1/smartperf-summary.json" --candidate "$root/wrong-run-1/smartperf-summary.json" --output "$root/wrong-comparison-1.json"
python3 "$comparator" --baseline "$root/run-1/smartperf-summary.json" --candidate "$root/wrong-run-2/smartperf-summary.json" --output "$root/wrong-comparison-2.json"

python3 - "$root" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
comparisons = [json.loads((root / f"wrong-comparison-{ordinal}.json").read_text()) for ordinal in (1, 2)]
if any(value.get("decision") != "performance-regression-candidate" for value in comparisons):
    raise SystemExit("both controlled wrong runs must be rejected")
regressed = [
    {metric["metric"] for metric in value.get("metrics", []) if metric.get("status") == "regressed"}
    for value in comparisons
]
common = sorted(regressed[0] & regressed[1])
if not common:
    raise SystemExit("controlled wrong runs lack a common regressed metric")
evidence = {
    "schema": "agentlab.purchase_data_ohostest_performance_detector_calibration.v1",
    "status": "qualified-review-required",
    "caseId": "purchase-data-finalization-candidate-clean-v1",
    "baseRevision": "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8",
    "sourceSetSha256": "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2",
    "baseline": {
        "runId": "run-1",
        "appHapSha256": "dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073",
        "summarySha256": hashlib.sha256((root / "run-1/smartperf-summary.json").read_bytes()).hexdigest(),
        "manifestSha256": hashlib.sha256((root / "run-1/run-manifest.json").read_bytes()).hexdigest(),
    },
    "controlledWrong": {
        "appHapSha256": "7bf92151da1a85ba3291c4997d5f4e291cc38833f5e5dbef72a4b2e42ec2a7b3",
        "testHapSha256": "2a9ee43900d7f4813b896909bc40b192319f7db79df117f4e4243b56278d53b5",
        "runIds": ["wrong-run-1", "wrong-run-2"],
        "mutation": {
            "id": "retain-64m-and-bounded-cpu-entry-page-v2",
            "kind": "combined-cpu-memory",
            "bytes": 67108864,
            "intervalMs": 500,
            "busyWindowMs": 400,
            "sourcePath": "entry/src/main/ets/pages/EntryPage.ets",
            "baseSourceFileSha256": "daf0f32975c9c9d05174995b165669d3b19388df03f2d6b8284131cab9c1aea0",
            "candidateSourceFileSha256": "99c0dd5acdf45973401cd8fefd7bc9daa055af4a12342ae8d0c3656c34f3924f",
        },
        "manifestSha256s": [
            hashlib.sha256((root / f"wrong-run-{ordinal}/run-manifest.json").read_bytes()).hexdigest()
            for ordinal in (1, 2)
        ],
        "summarySha256s": [
            hashlib.sha256((root / f"wrong-run-{ordinal}/smartperf-summary.json").read_bytes()).hexdigest()
            for ordinal in (1, 2)
        ],
    },
    "comparisonSha256s": [
        hashlib.sha256((root / f"wrong-comparison-{ordinal}.json").read_bytes()).hexdigest()
        for ordinal in (1, 2)
    ],
    "consistentRegressedMetrics": common,
    "functionalAssertionCount": 84,
    "profileSampleCount": 96,
    "relativePerformanceDetectorCalibrated": True,
    "distinctBaselineReferenceWrongCaseCalibrationComplete": False,
    "performanceCalibrated": False,
    "authority": {
        "functional": "ohosTest-hypium-source-bound",
        "relativePerformance": "smartperf-emulator-proxy",
        "absolutePowerThermal": "unavailable-on-emulator",
    },
    "boundary": "The exact clean candidate remains functionally passing while a controlled combined 64 MiB retained-memory and 400/500 ms bounded-CPU variant is rejected twice by the predeclared emulator guardrails. This calibrates the relative performance detector only; it is not an Agent run, unseen case, gold repair, distinct baseline/reference/wrong case calibration, live vendor-IAP, real-device or absolute power/thermal evidence.",
    "automaticPromotion": False,
    "nextGate": "rust-qualification-then-independent-review-and-distinct-case-variant-calibration",
}
(root / "controlled-performance-calibration.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
PY

"$hdc" list targets >"$root/final-calibration-hdc-targets.txt"
ps -eo pid,args | grep -E '[e]mulator|[q]emu-system' >"$root/final-calibration-emulator-processes.txt" || true
[ ! -s "$root/final-calibration-emulator-processes.txt" ]
if target_connected; then
  echo "unexpected HDC target remains" >&2
  exit 1
fi
trap - EXIT INT TERM
printf '%s\n' "$root"
