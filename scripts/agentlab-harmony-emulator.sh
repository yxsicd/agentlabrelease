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
  boot_mode=coldboot
  profile_samples=3
  keep_running=false
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
      --boot-mode) [ "$#" -ge 2 ] || die "--boot-mode requires a value"; boot_mode=$2; shift 2 ;;
      --profile-samples) [ "$#" -ge 2 ] || die "--profile-samples requires a count"; profile_samples=$2; shift 2 ;;
      --keep-running) keep_running=true; shift ;;
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
  case "$hdc_port" in ''|*[!0-9]*) die "hdc port must be numeric" ;; esac
  [ "$hdc_port" -ge 10000 ] && [ "$hdc_port" -le 16555 ] ||
    die "hdc port must be in 10000..16555"
  case "$profile_samples" in ''|*[!0-9]*) die "profile samples must be numeric" ;; esac
  [ "$profile_samples" -ge 1 ] && [ "$profile_samples" -le 60 ] ||
    die "profile samples must be in 1..60"
  case "$boot_mode" in coldboot|reset|snapshot) ;; *) die "unsupported boot mode: $boot_mode" ;; esac
  emulator="$tools_root/bin/Emulator"
  hdc="$tools_root/sdk/default/openharmony/toolchains/hdc"
  [ -x "$emulator" ] || die "emulator entrypoint missing or not executable: $emulator"
  [ -x "$hdc" ] || die "hdc entrypoint missing or not executable: $hdc"
  [ -f "$hap" ] || die "HAP not found: $hap"
  [ -f "$instance_path/$instance.ini" ] || die "emulator instance is not prepared: $instance"
  [ ! -e "$output" ] || die "refusing to overwrite existing output: $output"
  preflight
  mkdir -p "$output"
  target="127.0.0.1:$hdc_port"
  started=false
  terminal_status=failed
  cleanup_case() {
    rc=$?
    if [ "$started" = true ] && [ "$keep_running" != true ]; then
      "$emulator" -stop "$instance" -instancePath "$instance_path" \
        >>"$output/emulator-stop.log" 2>&1 || true
    fi
    if [ "$terminal_status" != passed ]; then
      printf '{"schema":"agentlab.harmony_emulator_case_result.v1","status":"failed","instance":"%s","target":"%s","bundle":"%s","ability":"%s"}\n' \
        "$instance" "$target" "$bundle" "$ability" >"$output/result.json"
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
  file_sha256 "$hap" >"$output/hap.sha256"
  file_sha256 "$screenshot" >"$output/screenshot.sha256"
  if "$hdc" -t "$target" shell SP_daemon -N "$profile_samples" -PKG "$bundle" \
      -c -g -t -p -f -r -net -snapshot -d >"$output/smartperf.txt" 2>&1; then
    profile_status=collected
  else
    profile_status=unavailable
  fi
  terminal_status=passed
  printf '{"schema":"agentlab.harmony_emulator_case_result.v1","status":"passed","instance":"%s","target":"%s","bundle":"%s","ability":"%s","hapSha256":"%s","screenshotSha256":"%s","profileStatus":"%s","powerThermalAuthority":"unavailable_on_emulator","artifacts":{"install":"install.log","bundle":"bundle-dump.txt","launch":"launch.log","process":"process.txt","screenshot":"%s","smartperf":"smartperf.txt"}}\n' \
    "$instance" "$target" "$bundle" "$ability" \
    "$(cat "$output/hap.sha256")" "$(cat "$output/screenshot.sha256")" \
    "$profile_status" "$(basename "$screenshot")" >"$output/result.json"
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
    '  agentlab-harmony-emulator.sh run-case --root INSTALL_ROOT --image-root PATH --instance-path PATH --instance NAME --hdc-port PORT --hap PATH --bundle ID --ability NAME --output PATH [--boot-mode coldboot|reset|snapshot] [--profile-samples N] [--keep-running]' \
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
