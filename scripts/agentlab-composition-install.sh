#!/usr/bin/env bash
set -euo pipefail

version="40ecdf4b"
control_url="https://github.com/yxsicd/agentlabrelease/releases/download/control-ea25616d-linux-x64/agentlabctl-ea25616d-linux-x64"
control_sha256="076ee1beee90023660cbda7f9ab90ae01863550783f16d4de4a4e39422343da8"
control_bytes="4425648"
lock_url="https://github.com/yxsicd/agentlabrelease/releases/download/candidate-20260913-40ecdf4b-sdk-c075105a-linux-x64/environment-lock.json"
lock_sha256="ac9192c09ee9e3488f2e874ddeb7b5d5dc0ec422aa09e728a49cb037f1ef333e"
lock_bytes="6515"

usage() {
  cat <<'EOF'
Usage:
  agentlab-composition-install.sh online [--root DIR] [--cache-dir DIR]
  agentlab-composition-install.sh offline --control FILE --lock FILE [--root DIR] [--cache-dir DIR]

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
  online|offline) shift ;;
  -h|--help|"") usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

root="${AGENTLAB_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/agentlab/${version}}"
cache_dir=""
control=""
lock=""
while (( $# )); do
  case "$1" in
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
mkdir -p "${root}/bin" "${root}/metadata" "${root}/acquired" "${root}/receipts" "${cache_dir}"

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
  chmod 700 "${temporary}"
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

[[ "$("${control}" digest "${control}")" == "${control_sha256}" ]] || {
  echo "unexpected agentlabctl identity" >&2
  exit 1
}
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

"${control}" composition install-docker \
  --dir "${root}/acquired" --platform linux-x64 \
  --receipt "${root}/receipts/install.json" \
  > "${root}/receipts/install.stdout.json"

printf '{"schema":"agentlab.portable_install_result.v1","coverage":"component-install-only","fullHarnessReady":false,"version":"%s","root":"%s","controlSha256":"%s","lockSha256":"%s","receipt":"%s"}\n' \
  "${version}" "${root}" "${control_sha256}" "${lock_sha256}" "${root}/receipts/install.json"
