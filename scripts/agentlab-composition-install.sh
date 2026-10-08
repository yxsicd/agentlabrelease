#!/usr/bin/env bash
set -euo pipefail

version="40ecdf4b"
control_url="https://github.com/yxsicd/agentlabrelease/releases/download/control-90496dc0-linux-x64/agentlabctl-90496dc0-linux-x64"
control_sha256="764b74d71b1c21f01cb68758d00da58d0f6b564d92a28fb4f8bc0e202a9fd880"
control_bytes="4260960"
lock_url="https://github.com/yxsicd/agentlabrelease/releases/download/candidate-20260913-40ecdf4b-sdk-c075105a-linux-x64/environment-lock.json"
lock_sha256="ac9192c09ee9e3488f2e874ddeb7b5d5dc0ec422aa09e728a49cb037f1ef333e"
lock_bytes="6515"

usage() {
  cat <<'EOF'
Usage:
  agentlab-composition-install.sh online [--plan] [--root DIR] [--cache-dir DIR]
  agentlab-composition-install.sh offline [--plan] --control FILE --lock FILE [--root DIR] [--cache-dir DIR]
  agentlab-composition-install.sh inspect --root DIR

--plan acquires verified assets into the private root/cache, then produces a
no-Docker-write plan instead of installing. inspect uses already acquired bytes
and creates no files or Docker resources. A plan does not verify installed bytes.

Online bootstrap verifies the static agentlabctl with a host checksum command.
The trusted control binary then performs all remaining downloads, verification,
zstd decoding, and Docker installation. Offline media must supply a trusted
control binary and the exact lock. Neither path requires Python, zstd, tar,
Git, Node/Bun, or Rust/Cargo on the host.
This prepares components only. It does not start or qualify a full Harness.
EOF
}

action="${1:-}"
case "${action}" in
  online|offline|inspect) shift ;;
  -h|--help|"") usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

root="${AGENTLAB_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/agentlab/${version}}"
cache_dir=""
control=""
lock=""
plan=false
while (( $# )); do
  case "$1" in
    --plan) plan=true; shift ;;
    --root) root="${2:?--root requires a directory}"; shift 2 ;;
    --cache-dir) cache_dir="${2:?--cache-dir requires a directory}"; shift 2 ;;
    --control) control="${2:?--control requires a file}"; shift 2 ;;
    --lock) lock="${2:?--lock requires a file}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

private_directory() {
  local directory="$1" ancestor="$1"
  [[ "${directory}" == /* && "${directory}" != */ && "${directory}" != "${HOME}" &&
     "${directory}" != *'"'* && "${directory}" != *$'\\'* && "${directory}" != *[[:cntrl:]]* &&
     "${directory}" != *//* && "${directory}" != */./* && "${directory}" != */../* &&
     "${directory}" != */. && "${directory}" != */.. ]] || return 2
  case "${directory}" in
    /bin|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/sys|/tmp|/usr|/var) return 2 ;;
  esac
  while [[ "${ancestor}" != / ]]; do
    [[ ! -L "${ancestor}" ]] || return 2
    ancestor="${ancestor%/*}"
    ancestor="${ancestor:-/}"
  done
}
cache_dir="${cache_dir:-${root}/cache}"
private_directory "${root}" && private_directory "${cache_dir}" || {
  echo "--root and --cache-dir must be dedicated absolute directories without symlink ancestors" >&2
  exit 2
}
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "this component cut requires Linux x86_64 (including WSL2)" >&2
  exit 2
}
command -v docker >/dev/null 2>&1 || { echo "Docker CLI is required" >&2; exit 2; }
docker version >/dev/null
umask 077

digest_with_host() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${path}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${path}" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 -r "${path}" | awk '{print $1}'
  else
    echo "online bootstrap requires sha256sum, shasum, or openssl" >&2
    return 2
  fi
}

download() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --connect-timeout 20 --max-time 180 -o "${out}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget --timeout=180 --tries=3 -O "${out}" "${url}"
  else
    echo "online bootstrap requires curl or wget" >&2
    return 2
  fi
}

prepare_public_executable() {
  # These are checksum-verified public code bytes, not credentials. Docker's
  # root/other UID with cap-drop=ALL must execute the read-only binary bind.
  # Private acquisition directories retain umask 077; no writable code bits.
  chmod 0555 "${1}"
}

if [[ "${action}" == "inspect" ]]; then
  [[ "${plan}" == false && -z "${control}" && -z "${lock}" ]] || {
    echo "inspect accepts an existing root, not --plan/--control/--lock" >&2; exit 2;
  }
  control="${root}/bin/agentlabctl"
  [[ -f "${control}" && -x "${control}" && ! -L "${control}" ]] || {
    echo "inspect requires the exact installed controller; first acquire with online --plan" >&2; exit 2;
  }
  [[ "$(digest_with_host "${control}")" == "${control_sha256}" ]] || {
    echo "unexpected agentlabctl identity" >&2; exit 1;
  }
  [[ -f "${root}/acquired/agentlab-environment-lock.json" &&
     ! -L "${root}/acquired/agentlab-environment-lock.json" &&
     "$("${control}" digest "${root}/acquired/agentlab-environment-lock.json")" == "${lock_sha256}" ]] || {
    echo "inspect requires the selected exact acquired environment lock" >&2; exit 1;
  }
  exec "${control}" composition plan-docker --dir "${root}/acquired" --platform linux-x64
fi

mkdir -p "${root}/bin" "${root}/metadata" "${root}/acquired" "${root}/receipts" "${cache_dir}"
if [[ "${action}" == "online" ]]; then
  control="${root}/bin/agentlabctl"
  temporary="${control}.partial.$$"
  trap 'rm -f -- "${temporary:-}"' EXIT
  download "${control_url}" "${temporary}"
  [[ "$(digest_with_host "${temporary}")" == "${control_sha256}" ]] || {
    echo "agentlabctl digest mismatch" >&2
    exit 1
  }
  [[ "$(wc -c < "${temporary}" | tr -d ' ')" == "${control_bytes}" ]] || {
    echo "agentlabctl size mismatch" >&2
    exit 1
  }
  prepare_public_executable "${temporary}"
  mv -f -- "${temporary}" "${control}"
  trap - EXIT
  lock="${root}/metadata/environment-lock.json"
  "${control}" fetch asset --url "${lock_url}" --sha256 "${lock_sha256}" --bytes "${lock_bytes}" --out "${lock}" --cache-dir "${cache_dir}"
else
  [[ -n "${control}" && -n "${lock}" ]] || {
    echo "offline requires --control and --lock" >&2
    exit 2
  }
  [[ -x "${control}" && -f "${lock}" ]] || {
    echo "offline control or lock is unavailable" >&2
    exit 2
  }
fi

[[ "$(digest_with_host "${control}")" == "${control_sha256}" ]] || {
  echo "unexpected agentlabctl identity" >&2
  exit 1
}
if [[ "${action}" == "offline" ]]; then
  temporary="${root}/bin/agentlabctl.offline.partial.$$"
  trap 'rm -f -- "${temporary:-}"' EXIT
  cp -- "${control}" "${temporary}"
  [[ "$(digest_with_host "${temporary}")" == "${control_sha256}" ]] || {
    echo "offline control changed while copying" >&2; exit 1;
  }
  prepare_public_executable "${temporary}"
  mv -f -- "${temporary}" "${root}/bin/agentlabctl"
  control="${root}/bin/agentlabctl"
  trap - EXIT
fi
[[ "$("${control}" digest "${lock}")" == "${lock_sha256}" ]] || {
  echo "unexpected environment lock identity" >&2
  exit 1
}
command -v docker >/dev/null 2>&1 || { echo "Docker CLI is required" >&2; exit 2; }
docker version >/dev/null

"${control}" fetch composition \
  --lock "${lock}" --platform linux-x64 \
  --out-dir "${root}/acquired" --cache-dir "${cache_dir}" \
  > "${root}/receipts/fetch.json"

if [[ "${plan}" == true ]]; then
  exec "${control}" composition plan-docker --dir "${root}/acquired" --platform linux-x64
fi

"${control}" composition install-docker \
  --dir "${root}/acquired" --platform linux-x64 \
  --receipt "${root}/receipts/install.json" \
  > "${root}/receipts/install.stdout.json"

printf '{"schema":"agentlab.portable_install_result.v1","coverage":"component-install-only","fullHarnessReady":false,"version":"%s","root":"%s","controlSha256":"%s","lockSha256":"%s","receipt":"%s"}\n' \
  "${version}" "${root}" "${control_sha256}" "${lock_sha256}" "${root}/receipts/install.json"
