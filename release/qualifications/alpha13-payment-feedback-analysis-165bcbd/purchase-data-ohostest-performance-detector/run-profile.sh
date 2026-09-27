#!/usr/bin/env bash
set -euo pipefail

root=/home/huawei/.agentlab/evidence/purchase-data-ohostest-profile-ee2bc87-v7
tools=/home/huawei/commandline-tools-26.0.0.821
emulator="$tools/bin/Emulator"
hdc="$tools/sdk/default/openharmony/toolchains/hdc"
image_root=/home/huawei/HarmonyOS-Emulator/images
instance_path=/home/huawei/HarmonyOS-Emulator/instances
instance=codex_phone_7
port=10100
target=127.0.0.1:10100
project=/home/huawei/agentlab-source-builds/payment-feedback-165bcbd-ohostest-ref-v1
app_hap="$project/entry/build/default/outputs/default/entry-default-unsigned.hap"
test_hap="$project/entry/build/default/outputs/ohosTest/entry-ohosTest-unsigned.hap"
runner="$root/run-harmony-instrument-test.py"
normalizer="$root/summarize-smartperf.py"
comparator="$root/compare-smartperf.py"
policy="$root/performance-policy.json"
workload="$root/profile-workload.tsv"
source_set=cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2
app_sha=dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073
test_sha=5a2015114fd435daba3e25331df6a7ac48445827230079870cc2571c710934fe
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
[ "$(git -C "$project" rev-parse HEAD)" = ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8 ]
[ -z "$(git -C "$project" status --short)" ]
if [ -e "$root/run-1" ] || [ -e "$root/run-2" ] || [ -e "$root/smartperf-comparison.json" ]; then
  echo "refusing to overwrite retained profile evidence" >&2
  exit 1
fi

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
    python3 "$runner"       --project-root "$project"       --case-id purchase-data-finalization-candidate-clean-v1       --source-set-sha256 "$source_set"       --hdc "$hdc"       --target "$target"       --app-hap "$app_hap"       --test-hap "$test_hap"       --bundle xxx.xxx.xxx       --module entry_test       --runner OpenHarmonyTestRunner       --skip-install       --timeout-seconds 300       --case-timeout-ms 60000       --output-dir "$out/tests/$ordinal" >"$out/tests/$ordinal.stdout.log" 2>"$out/tests/$ordinal.stderr.log"
    printf '%s\trepeat-ohostest\t7,OpenHarmonyTestRunner\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
    start_verified_app "$out" "$ordinal"
    printf '%s\tstart-app\tEntryAbility,xxx.xxx.xxx\n' "$ordinal" >>"$out/profile-workload-actions.tsv"
  done
  wait "$smartperf_pid"

  python3 "$normalizer"     --input "$out/smartperf.txt"     --task-id purchase-data-finalization-ee2bc87594f1     --source-identity "artifact-sha256:$app_sha"     --run-id "$label"     --environment-identity "$environment"     --minimum-samples 48     --performance-policy "$policy"     --profile-workload "$workload"     --output "$out/smartperf-summary.json"

  python3 - "$out" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
window_started = (root / "profile-window-started-at.txt").read_text().strip()
window_finished = (root / "profile-window-finished-at.txt").read_text().strip()
receipts = []
for path in sorted((root / "tests").glob("*/receipt.json")):
    value = json.loads(path.read_text())
    report_path = path.parent / value["report"]["path"]
    report = json.loads(report_path.read_text())
    if value.get("passed") is not True or value.get("packagesInstalled") is not False or report.get("passed") is not True or report.get("counts") != {"error": 0, "failure": 0, "ignore": 0, "pass": 7, "total": 7}:
        raise SystemExit(f"functional repeat failed: {path}")
    if not (window_started <= value["startedAt"] <= value["finishedAt"] <= window_finished):
        raise SystemExit(f"functional repeat escaped SmartPerf window: {path}")
    receipts.append({
        "ordinal": int(path.parent.name),
        "receiptSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "nativeReportSha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "counts": report["counts"],
    })
summary_path = root / "smartperf-summary.json"
summary = json.loads(summary_path.read_text())
if summary.get("profileValid") is not True or summary.get("sampleCount") != 48:
    raise SystemExit("SmartPerf profile is invalid")
manifest = {
    "schema": "agentlab.purchase_data_ohostest_profile_run.v1",
    "status": "passed",
    "runId": root.name,
    "candidateRevision": "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8",
    "candidateSourceSha256": "cd53dcfe1c5e364d67b57e59e27f4336c32d6058ef5abf45bd75385817d24bb0",
    "sourceSetSha256": "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2",
    "appHapSha256": "dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073",
    "testHapSha256": "5a2015114fd435daba3e25331df6a7ac48445827230079870cc2571c710934fe",
    "environmentIdentity": "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7",
    "functionalRepeatCount": len(receipts),
    "functionalRepeats": receipts,
    "functionalRepeatsWithinProfileWindow": True,
    "profileSampleCount": 48,
    "profileWindowStartedAt": window_started,
    "profileWindowFinishedAt": window_finished,
    "smartPerfSummarySha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    "performancePolicySha256": hashlib.sha256((root.parent / "performance-policy.json").read_bytes()).hexdigest(),
    "profileWorkloadSha256": hashlib.sha256((root.parent / "profile-workload.tsv").read_bytes()).hexdigest(),
    "profileWorkloadActionsSha256": hashlib.sha256((root / "profile-workload-actions.tsv").read_bytes()).hexdigest(),
    "profileWorkloadActionCount": len((root / "profile-workload-actions.tsv").read_text().splitlines()),
    "runnerSha256": hashlib.sha256((root.parent / "run-harmony-instrument-test.py").read_bytes()).hexdigest(),
    "standardTestContractSha256": hashlib.sha256((root.parent / "harmony-standard-test-contract.py").read_bytes()).hexdigest(),
    "normalizerSha256": hashlib.sha256((root.parent / "summarize-smartperf.py").read_bytes()).hexdigest(),
    "comparatorSha256": hashlib.sha256((root.parent / "compare-smartperf.py").read_bytes()).hexdigest(),
    "runProfileScriptSha256": hashlib.sha256((root.parent / "run-profile.sh").read_bytes()).hexdigest(),
    "oneTimeInstallAppLogSha256": hashlib.sha256((root / "install-app.log").read_bytes()).hexdigest(),
    "oneTimeInstallTestLogSha256": hashlib.sha256((root / "install-test.log").read_bytes()).hexdigest(),
    "performanceRepeatabilityOnly": True,
    "liveVendorIapExecuted": False,
    "realDeviceExecuted": False,
    "absolutePowerThermalAuthority": False,
    "automaticPromotion": False,
}
(root / "run-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY

  stop_emulator "$out/emulator-stop.log"
  [ ! -e "/proc/$(cat "$out/emulator-launcher.pid")" ] || wait "$(cat "$out/emulator-launcher.pid")" || true
}

run_one run-1
run_one run-2

python3 "$comparator"   --baseline "$root/run-1/smartperf-summary.json"   --candidate "$root/run-2/smartperf-summary.json"   --output "$root/smartperf-comparison.json"

"$hdc" list targets >"$root/final-hdc-targets.txt"
ps -eo pid,args | grep -E '[e]mulator|[q]emu-system' >"$root/final-emulator-processes.txt" || true
[ ! -s "$root/final-emulator-processes.txt" ]
if target_connected; then
  echo "unexpected HDC target remains" >&2
  exit 1
fi
sha256sum "$policy" "$workload" "$root/run-1/run-manifest.json" "$root/run-2/run-manifest.json" "$root/smartperf-comparison.json" >"$root/SHA256SUMS"
trap - EXIT INT TERM
printf '%s\n' "$root"
