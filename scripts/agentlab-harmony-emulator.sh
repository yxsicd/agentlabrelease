#!/usr/bin/env bash
set -eu

TOOLS_BYTES=932070897
TOOLS_SHA256=ad1eb9a255b6fc6f022a646bd536ef230d66e47aea1f9177a793924b83ebb649
IMAGE_BYTES=1568108769
IMAGE_SHA256=75c537cb6dc62291f96f0f247c148de653c9c6633c4dc5b0c34cc254909ae671

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

file_bytes() {
  if stat -c %s "$1" >/dev/null 2>&1; then
    stat -c %s "$1"
  else
    stat -f %z "$1"
  fi
}

file_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    die "sha256sum, shasum, or openssl is required"
  fi
}

verify_one() {
  label=$1
  path=$2
  expected_bytes=$3
  expected_sha=$4
  [ -f "$path" ] || die "$label archive not found: $path"
  actual_bytes=$(file_bytes "$path")
  [ "$actual_bytes" = "$expected_bytes" ] ||
    die "$label byte count mismatch: expected $expected_bytes, got $actual_bytes"
  actual_sha=$(file_sha256 "$path")
  [ "$actual_sha" = "$expected_sha" ] ||
    die "$label SHA-256 mismatch: expected $expected_sha, got $actual_sha"
  zstd -t --long=31 "$path" >/dev/null
  printf '%s verified: bytes=%s sha256=%s\n' "$label" "$actual_bytes" "$actual_sha"
}

preflight() {
  need zstd
  need tar
  need awk
  arch=$(uname -m)
  [ "$arch" = x86_64 ] || die "unsupported architecture: $arch; linux x86_64 required"
  [ "$(uname -s)" = Linux ] || die "unsupported operating system; Linux required"
  [ -c /dev/kvm ] || die "/dev/kvm is not present"
  [ -r /dev/kvm ] && [ -w /dev/kvm ] ||
    die "/dev/kvm is not readable and writable by the current user"
  printf 'preflight passed: platform=linux-x64 acceleration=kvm\n'
}

verify_assets() {
  [ "$#" -eq 2 ] || die "verify-assets requires TOOLS_ARCHIVE IMAGE_ARCHIVE"
  need zstd
  need tar
  verify_one tools "$1" "$TOOLS_BYTES" "$TOOLS_SHA256"
  verify_one image "$2" "$IMAGE_BYTES" "$IMAGE_SHA256"
}

verify_install() {
  [ "$#" -eq 1 ] || die "verify-install requires INSTALL_ROOT"
  root=$1
  [ -x "$root/command-line-tools/bin/Emulator" ] ||
    die "emulator entrypoint missing or not executable"
  [ -x "$root/command-line-tools/sdk/default/openharmony/toolchains/hdc" ] ||
    die "hdc entrypoint missing or not executable"
  image="$root/images/system-image/HarmonyOS-7.0.0/phone_all_x86"
  for name in info.json sdk-pkg.json bzImage system.img vendor.img userdata.img; do
    [ -f "$image/$name" ] || die "system image member missing: $name"
  done
  printf 'install verified: root=%s imageAbi=x86\n' "$root"
}

install_bundle() {
  tools=
  image=
  root=
  acknowledged=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --tools) [ "$#" -ge 2 ] || die "--tools requires a path"; tools=$2; shift 2 ;;
      --image) [ "$#" -ge 2 ] || die "--image requires a path"; image=$2; shift 2 ;;
      --root) [ "$#" -ge 2 ] || die "--root requires a path"; root=$2; shift 2 ;;
      --acknowledge-vendor-agreements) acknowledged=true; shift ;;
      *) die "unknown install argument: $1" ;;
    esac
  done
  [ -n "$tools" ] && [ -n "$image" ] && [ -n "$root" ] ||
    die "install requires --tools, --image, and --root"
  [ "$acknowledged" = true ] ||
    die "operator must read and acknowledge the vendor agreements"
  preflight
  verify_assets "$tools" "$image"
  [ ! -e "$root" ] || die "refusing to overwrite existing install root: $root"
  parent=$(dirname "$root")
  mkdir -p "$parent"
  stage=$(mktemp -d "$parent/.harmony-emulator-stage.XXXXXX")
  cleanup_stage=true
  cleanup() {
    if [ "$cleanup_stage" = true ] && [ -n "${stage:-}" ] && [ -d "$stage" ]; then
      rm -rf -- "$stage"
    fi
  }
  trap cleanup EXIT INT TERM
  zstd -dc --long=31 "$tools" | tar -xf - -C "$stage"
  mkdir -p "$stage/images"
  zstd -dc --long=31 "$image" | tar -xf - -C "$stage/images"
  verify_install "$stage"
  mv -- "$stage" "$root"
  cleanup_stage=false
  trap - EXIT INT TERM
  printf 'installed: root=%s\n' "$root"
}

validate_token() {
  label=$1
  value=$2
  case "$value" in
    ''|*[!A-Za-z0-9_.:-]*) die "$label contains unsupported characters: $value" ;;
  esac
}

validate_integer() {
  label=$1
  value=$2
  minimum=$3
  maximum=$4
  case "$value" in ''|*[!0-9]*) die "$label must be numeric" ;; esac
  [ "$value" -ge "$minimum" ] && [ "$value" -le "$maximum" ] ||
    die "$label must be in $minimum..$maximum"
}

run_case() {
  root=
  tools_root=
  image_root=
  instance_path=
  instance=
  hdc_port=
  hap=
  bundle=
  ability=
  output=
  ui_scenario=
  task_id=
  source_id=
  boot_mode=coldboot
  profile_samples=3
  keep_running=false
  reset_app_data=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --root) [ "$#" -ge 2 ] || die "--root requires a path"; root=$2; shift 2 ;;
      --tools-root) [ "$#" -ge 2 ] || die "--tools-root requires a path"; tools_root=$2; shift 2 ;;
      --image-root) [ "$#" -ge 2 ] || die "--image-root requires a path"; image_root=$2; shift 2 ;;
      --instance-path) [ "$#" -ge 2 ] || die "--instance-path requires a path"; instance_path=$2; shift 2 ;;
      --instance) [ "$#" -ge 2 ] || die "--instance requires a name"; instance=$2; shift 2 ;;
      --hdc-port) [ "$#" -ge 2 ] || die "--hdc-port requires a port"; hdc_port=$2; shift 2 ;;
      --hap) [ "$#" -ge 2 ] || die "--hap requires a path"; hap=$2; shift 2 ;;
      --bundle) [ "$#" -ge 2 ] || die "--bundle requires an id"; bundle=$2; shift 2 ;;
      --ability) [ "$#" -ge 2 ] || die "--ability requires a name"; ability=$2; shift 2 ;;
      --output) [ "$#" -ge 2 ] || die "--output requires a path"; output=$2; shift 2 ;;
      --ui-scenario) [ "$#" -ge 2 ] || die "--ui-scenario requires a path"; ui_scenario=$2; shift 2 ;;
      --task-id) [ "$#" -ge 2 ] || die "--task-id requires an id"; task_id=$2; shift 2 ;;
      --source-id) [ "$#" -ge 2 ] || die "--source-id requires an id"; source_id=$2; shift 2 ;;
      --boot-mode) [ "$#" -ge 2 ] || die "--boot-mode requires a value"; boot_mode=$2; shift 2 ;;
      --profile-samples) [ "$#" -ge 2 ] || die "--profile-samples requires a count"; profile_samples=$2; shift 2 ;;
      --keep-running) keep_running=true; shift ;;
      --reset-app-data) reset_app_data=true; shift ;;
      *) die "unknown run-case argument: $1" ;;
    esac
  done
  [ -n "$instance" ] && [ -n "$hdc_port" ] && [ -n "$hap" ] &&
    [ -n "$bundle" ] && [ -n "$ability" ] && [ -n "$output" ] ||
    die "run-case requires --instance, --hdc-port, --hap, --bundle, --ability, and --output"
  if [ -n "$root" ]; then
    [ -z "$tools_root" ] || die "--root and --tools-root are mutually exclusive"
    tools_root="$root/command-line-tools"
    [ -n "$image_root" ] || image_root="$root/images"
  fi
  [ -n "$tools_root" ] && [ -n "$image_root" ] && [ -n "$instance_path" ] ||
    die "run-case requires --root or --tools-root, plus --image-root and --instance-path"
  validate_token instance "$instance"
  validate_token bundle "$bundle"
  validate_token ability "$ability"
  validate_integer "hdc port" "$hdc_port" 10000 16555
  validate_integer "profile samples" "$profile_samples" 1 60
  case "$boot_mode" in coldboot|reset|snapshot) ;; *) die "unsupported boot mode: $boot_mode" ;; esac
  emulator="$tools_root/bin/Emulator"
  hdc="$tools_root/sdk/default/openharmony/toolchains/hdc"
  [ -x "$emulator" ] || die "emulator entrypoint missing or not executable: $emulator"
  [ -x "$hdc" ] || die "hdc entrypoint missing or not executable: $hdc"
  [ -f "$hap" ] || die "HAP not found: $hap"
  [ -f "$instance_path/$instance.ini" ] || die "emulator instance is not prepared: $instance"
  scenario_id=
  scenario_sha=
  if [ -n "$ui_scenario" ]; then
    [ -f "$ui_scenario" ] || die "UI scenario not found: $ui_scenario"
    grep -q $'^schema\tagentlab.harmony_ui_scenario.v1$' "$ui_scenario" ||
      die "UI scenario schema is missing or unsupported"
    [ "$(grep -c $'^case\t' "$ui_scenario")" -eq 1 ] ||
      die "UI scenario must declare exactly one case"
    scenario_id=$(awk -F '\t' '$1 == "case" { print $2 }' "$ui_scenario")
    validate_token "scenario case" "$scenario_id"
    [ -n "$task_id" ] && [ -n "$source_id" ] ||
      die "--ui-scenario requires --task-id and --source-id"
    validate_token "task id" "$task_id"
    validate_token "source id" "$source_id"
    scenario_sha=$(file_sha256 "$ui_scenario")
  else
    [ -z "$task_id" ] && [ -z "$source_id" ] ||
      die "--task-id and --source-id require --ui-scenario"
  fi
  [ ! -e "$output" ] || die "refusing to overwrite existing output: $output"
  preflight
  mkdir -p "$output"
  hap_sha=$(file_sha256 "$hap")
  printf '%s\n' "$hap_sha" >"$output/hap.sha256"
  if [ -n "$ui_scenario" ]; then
    printf '%s\n' "$scenario_sha" >"$output/ui-scenario.sha256"
  fi
  target="127.0.0.1:$hdc_port"
  started=false
  terminal_status=failed
  oracle_status=not-run
  assessment_status=infrastructure-unavailable
  infrastructure_available=false
  subject_task_succeeded=null
  failure_class=infrastructure
  layout_ordinal=0
  action_ordinal=0
  last_layout=
  record_ui_action() {
    action_ordinal=$((action_ordinal + 1))
    printf '%s\t%s\t%s\n' "$action_ordinal" "$1" "$2" >>"$output/ui-actions.tsv"
  }
  record_ui_check() {
    printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >>"$output/ui-checks.tsv"
  }
  dump_ui_layout() {
    layout_ordinal=$((layout_ordinal + 1))
    layout_name=$(printf 'ui-layout-%03d.json' "$layout_ordinal")
    remote_layout="/data/local/tmp/agentlab-$scenario_id-$layout_ordinal.json"
    "$hdc" -t "$target" shell uitest dumpLayout -p "$remote_layout" \
      >"$output/$layout_name.dump.log" 2>&1 ||
      infrastructure_failure "UI layout dump failed"
    "$hdc" -t "$target" file recv "$remote_layout" "$output/$layout_name" \
      >"$output/$layout_name.recv.log" 2>&1 ||
      infrastructure_failure "UI layout receive failed"
    last_layout="$output/$layout_name"
  }
  infrastructure_failure() {
    assessment_status=infrastructure-unavailable
    infrastructure_available=false
    subject_task_succeeded=null
    failure_class=infrastructure
    die "$*"
  }
  oracle_failure() {
    assessment_status=assessed
    infrastructure_available=true
    subject_task_succeeded=false
    failure_class=oracle
    die "$*"
  }
  ui_validate_token() {
    label=$1
    value=$2
    case "$value" in
      ''|*[!A-Za-z0-9_.:-]*) infrastructure_failure "$label contains unsupported characters: $value" ;;
    esac
  }
  ui_validate_integer() {
    label=$1
    value=$2
    minimum=$3
    maximum=$4
    case "$value" in
      ''|*[!0-9]*) infrastructure_failure "$label must be numeric" ;;
    esac
    [ "$value" -ge "$minimum" ] && [ "$value" -le "$maximum" ] ||
      infrastructure_failure "$label must be in $minimum..$maximum"
  }
  run_ui_scenario() {
    oracle_status=failed
    assessment_status=assessed
    infrastructure_available=true
    subject_task_succeeded=false
    failure_class=oracle
    while IFS=$'\t' read -r operation a b c d e || [ -n "$operation$a$b$c$d$e" ]; do
      case "$operation" in
        ''|'#'*) continue ;;
        schema)
          [ "$a" = "agentlab.harmony_ui_scenario.v1" ] && [ -z "$b$c$d$e" ] ||
            infrastructure_failure "invalid UI scenario schema line"
          ;;
        case)
          [ "$a" = "$scenario_id" ] && [ -z "$b$c$d$e" ] ||
            infrastructure_failure "invalid UI scenario case line"
          ;;
        wait-text)
          ui_validate_token "UI check label" "$a"
          ui_validate_integer "wait-text timeout" "$b" 1 120
          [ -n "$c" ] && [ -z "$d$e" ] ||
            infrastructure_failure "wait-text requires LABEL TIMEOUT TEXT"
          wait_attempt=1
          wait_passed=false
          while [ "$wait_attempt" -le "$b" ]; do
            dump_ui_layout
            if LC_ALL=C grep -F -- "$c" "$last_layout" >/dev/null; then
              wait_passed=true
              break
            fi
            sleep 1
            wait_attempt=$((wait_attempt + 1))
          done
          record_ui_check "$a" "$wait_passed" wait-text "$c" ||
            infrastructure_failure "UI check evidence write failed"
          [ "$wait_passed" = true ] || oracle_failure "UI wait-text check failed: $a"
          ;;
        tap)
          ui_validate_integer "tap x" "$a" 0 10000
          ui_validate_integer "tap y" "$b" 0 10000
          [ -z "$c$d$e" ] || infrastructure_failure "tap requires X Y"
          "$hdc" -t "$target" shell uitest uiInput click "$a" "$b" \
            >>"$output/ui-input.log" 2>&1 || infrastructure_failure "UI tap failed"
          record_ui_action tap "$a,$b" || infrastructure_failure "UI action evidence write failed"
          ;;
        swipe)
          ui_validate_integer "swipe x1" "$a" 0 10000
          ui_validate_integer "swipe y1" "$b" 0 10000
          ui_validate_integer "swipe x2" "$c" 0 10000
          ui_validate_integer "swipe y2" "$d" 0 10000
          ui_validate_integer "swipe duration" "$e" 1 60000
          "$hdc" -t "$target" shell uitest uiInput swipe "$a" "$b" "$c" "$d" "$e" \
            >>"$output/ui-input.log" 2>&1 || infrastructure_failure "UI swipe failed"
          record_ui_action swipe "$a,$b,$c,$d,$e" ||
            infrastructure_failure "UI action evidence write failed"
          ;;
        key)
          ui_validate_integer "key code" "$a" 0 1000
          [ -z "$b$c$d$e" ] || infrastructure_failure "key requires KEYCODE"
          "$hdc" -t "$target" shell uitest uiInput keyEvent "$a" \
            >>"$output/ui-input.log" 2>&1 || infrastructure_failure "UI key event failed"
          record_ui_action key "$a" || infrastructure_failure "UI action evidence write failed"
          ;;
        sleep)
          ui_validate_integer "sleep milliseconds" "$a" 0 60000
          [ -z "$b$c$d$e" ] ||
            infrastructure_failure "sleep requires MILLISECONDS"
          sleep "$(awk -v ms="$a" 'BEGIN { printf "%.3f", ms / 1000 }')"
          record_ui_action sleep "$a" || infrastructure_failure "UI action evidence write failed"
          ;;
        assert-text|assert-no-text)
          ui_validate_token "UI check label" "$a"
          [ -n "$b" ] && [ -z "$c$d$e" ] ||
            infrastructure_failure "$operation requires LABEL TEXT"
          dump_ui_layout
          check_passed=false
          if LC_ALL=C grep -F -- "$b" "$last_layout" >/dev/null; then
            [ "$operation" = assert-text ] && check_passed=true
          else
            [ "$operation" = assert-no-text ] && check_passed=true
          fi
          record_ui_check "$a" "$check_passed" "$operation" "$b" ||
            infrastructure_failure "UI check evidence write failed"
          [ "$check_passed" = true ] || oracle_failure "UI oracle check failed: $a"
          ;;
        *) infrastructure_failure "unsupported UI scenario operation: $operation" ;;
      esac
    done <"$ui_scenario"
    oracle_status=passed
    subject_task_succeeded=true
    failure_class=none
  }
  cleanup_case() {
    rc=$?
    if [ "$started" = true ] && [ "$keep_running" != true ]; then
      "$emulator" -stop "$instance" -instancePath "$instance_path" \
        >>"$output/emulator-stop.log" 2>&1 || true
    fi
    if [ "$terminal_status" != passed ]; then
      if [ -n "$ui_scenario" ]; then
        printf '{"schema":"agentlab.harmony_emulator_case_result.v2","status":"failed","taskId":"%s","sourceIdentity":"%s","instance":"%s","target":"%s","bundle":"%s","ability":"%s","hapSha256":"%s","scenarioId":"%s","scenarioSha256":"%s","oracleStatus":"%s","assessmentStatus":"%s","infrastructureAvailable":%s,"subjectTaskSucceeded":%s,"failureClass":"%s","powerThermalAuthority":"unavailable_on_emulator"}\n' \
          "$task_id" "$source_id" "$instance" "$target" "$bundle" "$ability" "$hap_sha" \
          "$scenario_id" "$scenario_sha" "$oracle_status" "$assessment_status" \
          "$infrastructure_available" "$subject_task_succeeded" "$failure_class" >"$output/result.json"
      else
        printf '{"schema":"agentlab.harmony_emulator_case_result.v1","status":"failed","instance":"%s","target":"%s","bundle":"%s","ability":"%s"}\n' \
          "$instance" "$target" "$bundle" "$ability" >"$output/result.json"
      fi
    fi
    exit "$rc"
  }
  trap cleanup_case EXIT INT TERM
  "$emulator" -start "$instance" -instancePath "$instance_path" \
    -imageRoot "$image_root" -bootMode "$boot_mode" -noWindow -hdcPort "$hdc_port" \
    >"$output/emulator-start.log" 2>&1 &
  started=true
  connected=false
  attempt=1
  while [ "$attempt" -le 180 ]; do
    "$hdc" tconn "$target" >>"$output/hdc-connect.log" 2>&1 || true
    if "$hdc" list targets 2>/dev/null | awk -v target="$target" \
        '$1 == target { found = 1 } END { exit(found ? 0 : 1) }' \
        >"$output/hdc-target.txt"; then
      "$hdc" list targets >"$output/hdc-target.txt"
      connected=true
      break
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  [ "$connected" = true ] || die "emulator did not expose a connected HDC target within 180 seconds"
  "$hdc" -t "$target" shell param get const.product.name >"$output/device-product.txt"
  "$hdc" -t "$target" shell param get const.ohos.fullname >"$output/device-version.txt"
  ui_ready=false
  attempt=1
  while [ "$attempt" -le 60 ]; do
    if "$hdc" -t "$target" shell uitest dumpLayout \
        -p /data/local/tmp/agentlab-ready.json >"$output/ui-ready.log" 2>&1 &&
        ! grep -iF "failed" "$output/ui-ready.log" >/dev/null; then
      ui_ready=true
      break
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  [ "$ui_ready" = true ] || die "emulator UI did not become ready within 60 seconds"
  if [ "$reset_app_data" = true ]; then
    "$hdc" -t "$target" uninstall "$bundle" >"$output/uninstall.log" 2>&1 || true
  else
    printf 'reset-app-data not requested\n' >"$output/uninstall.log"
  fi
  "$hdc" -t "$target" install -r "$hap" >"$output/install.log" 2>&1
  "$hdc" -t "$target" shell bm dump -n "$bundle" >"$output/bundle-dump.txt" 2>&1
  "$hdc" -t "$target" shell uitest uiInput swipe 630 2400 630 600 1000 \
    >"$output/unlock.log" 2>&1
  sleep 3
  "$hdc" -t "$target" shell aa start -a "$ability" -b "$bundle" >"$output/launch.log" 2>&1
  grep -F "start ability successfully" "$output/launch.log" >/dev/null ||
    die "ability launch did not report success; inspect launch.log"
  process_hint=${bundle#com.}
  printf '%s\n' "$process_hint" >"$output/process-hint.txt"
  process_attempt=1
  process_found=false
  while [ "$process_attempt" -le 15 ]; do
    "$hdc" -t "$target" shell ps -A >"$output/process-all.txt" 2>&1
    if LC_ALL=C grep -F -- "$process_hint" "$output/process-all.txt" >"$output/process.txt"; then
      process_found=true
      break
    fi
    sleep 1
    process_attempt=$((process_attempt + 1))
  done
  [ "$process_found" = true ] || die "launched bundle has no process: $bundle"
  if [ -n "$ui_scenario" ]; then
    run_ui_scenario
  fi
  "$emulator" -instance "$instance" -instancePath "$instance_path" \
    -screenshot -screenshotPath "$output" >"$output/screenshot.log" 2>&1
  screenshot=
  screenshot_attempt=1
  while [ "$screenshot_attempt" -le 10 ]; do
    screenshot=$(find "$output" -maxdepth 1 -type f -name '*.png' -size +0c -print -quit)
    [ -n "$screenshot" ] && break
    sleep 1
    screenshot_attempt=$((screenshot_attempt + 1))
  done
  [ -n "$screenshot" ] || die "emulator screenshot was not produced"
  file_sha256 "$screenshot" >"$output/screenshot.sha256"
  if "$hdc" -t "$target" shell SP_daemon -N "$profile_samples" -PKG "$bundle" \
      -c -g -t -p -f -r -net -snapshot -d >"$output/smartperf.txt" 2>&1; then
    profile_status=collected
  else
    profile_status=unavailable
  fi
  terminal_status=passed
  if [ -n "$ui_scenario" ]; then
    printf '{"schema":"agentlab.harmony_emulator_case_result.v2","status":"passed","taskId":"%s","sourceIdentity":"%s","instance":"%s","target":"%s","bundle":"%s","ability":"%s","hapSha256":"%s","screenshotSha256":"%s","scenarioId":"%s","scenarioSha256":"%s","oracleStatus":"%s","assessmentStatus":"%s","infrastructureAvailable":%s,"subjectTaskSucceeded":%s,"failureClass":"%s","profileStatus":"%s","resetAppData":%s,"powerThermalAuthority":"unavailable_on_emulator","artifacts":{"uninstall":"uninstall.log","install":"install.log","bundle":"bundle-dump.txt","launch":"launch.log","process":"process.txt","uiActions":"ui-actions.tsv","uiChecks":"ui-checks.tsv","screenshot":"%s","smartperf":"smartperf.txt"}}\n' \
      "$task_id" "$source_id" "$instance" "$target" "$bundle" "$ability" "$hap_sha" \
      "$(cat "$output/screenshot.sha256")" "$scenario_id" "$scenario_sha" "$oracle_status" \
      "$assessment_status" "$infrastructure_available" "$subject_task_succeeded" "$failure_class" \
      "$profile_status" "$reset_app_data" "$(basename "$screenshot")" >"$output/result.json"
  else
    printf '{"schema":"agentlab.harmony_emulator_case_result.v1","status":"passed","instance":"%s","target":"%s","bundle":"%s","ability":"%s","hapSha256":"%s","screenshotSha256":"%s","profileStatus":"%s","powerThermalAuthority":"unavailable_on_emulator","artifacts":{"install":"install.log","bundle":"bundle-dump.txt","launch":"launch.log","process":"process.txt","screenshot":"%s","smartperf":"smartperf.txt"}}\n' \
      "$instance" "$target" "$bundle" "$ability" "$hap_sha" \
      "$(cat "$output/screenshot.sha256")" "$profile_status" \
      "$(basename "$screenshot")" >"$output/result.json"
  fi
  printf 'case passed: result=%s/result.json\n' "$output"
  trap - EXIT INT TERM
  if [ "$keep_running" != true ]; then
    "$emulator" -stop "$instance" -instancePath "$instance_path" \
      >"$output/emulator-stop.log" 2>&1
  fi
}

usage() {
  printf '%s\n' \
    'usage:' \
    '  agentlab-harmony-emulator.sh preflight' \
    '  agentlab-harmony-emulator.sh verify-assets TOOLS_ARCHIVE IMAGE_ARCHIVE' \
    '  agentlab-harmony-emulator.sh verify-install INSTALL_ROOT' \
    '  agentlab-harmony-emulator.sh install --tools PATH --image PATH --root PATH --acknowledge-vendor-agreements' \
    '  agentlab-harmony-emulator.sh run-case --root INSTALL_ROOT --image-root PATH --instance-path PATH --instance NAME --hdc-port PORT --hap PATH --bundle ID --ability NAME --output PATH [--ui-scenario PATH --task-id ID --source-id ID] [--reset-app-data] [--boot-mode coldboot|reset|snapshot] [--profile-samples N] [--keep-running]' \
    '  For an existing vendor layout, replace --root with --tools-root PATH.'
}

command_name=${1:-}
[ -n "$command_name" ] || { usage; exit 2; }
shift
case "$command_name" in
  preflight) [ "$#" -eq 0 ] || die "preflight takes no arguments"; preflight ;;
  verify-assets) verify_assets "$@" ;;
  verify-install) verify_install "$@" ;;
  install) install_bundle "$@" ;;
  run-case) run_case "$@" ;;
  -h|--help|help) usage ;;
  *) usage >&2; die "unknown command: $command_name" ;;
esac
