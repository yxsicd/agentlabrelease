#!/usr/bin/env bash
set -euo pipefail

version="v0.1.0-alpha.10"
control_url="https://github.com/yxsicd/agentlabrelease/releases/download/control-24fb4ec0-linux-x64/agentlabctl-linux-x64"
control_sha256="51cec430e1c0a3741bab77f387ee90ed7349746a2d87ff39a275b4f975eab886"
control_bytes="4532144"
lock_url="https://github.com/yxsicd/agentlabrelease/releases/download/candidate-agentlab-alpha10-24fb4ec0-linux-x64/environment-lock.json"
lock_sha256="dcb27623ef9f3f5a92c0eb759120989cafcf25ace8873945a043242cb41fd1eb"
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

[[ "${root}" == /* && "${root}" != "/" ]] || {
  echo "--root must be a dedicated absolute directory" >&2
  exit 2
}
cache_dir="${cache_dir:-${root}/cache}"
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
    curl -fL --retry 3 --connect-timeout 20 -o "${out}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "${out}" "${url}"
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

printf '{"schema":"agentlab.portable_install_result.v1","version":"%s","root":"%s","controlSha256":"%s","lockSha256":"%s","receipt":"%s"}\n' \
  "${version}" "${root}" "${control_sha256}" "${lock_sha256}" "${root}/receipts/install.json"
