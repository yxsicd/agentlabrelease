#!/usr/bin/env bash
set -euo pipefail

version="v0.1.0-alpha.9"
release_repo="yxsicd/agentlabrelease"
kit_name="agentlab-environment-kit-v0.1.0-alpha.9.tar.zst"
probe_name="agentlab-ts-probe-v0.1.0-alpha.9.tar.zst"
kit_sha="fcca40e0858bbbde7620ddec83db0dc525c62d597926dc27ef66b6dd54c27a73"
probe_sha="029074b412bdaaccd069250949eec459861e685a5ef398fbbc30d4c7cbf4d2d3"

usage() {
  cat <<'EOF'
Usage: agentlab-harness-quickstart.sh ACTION [--root DIR] [--instance ald00]

Actions:
  online-install   Download missing immutable assets, install ald00, and check health.
  offline-install  Use only previously downloaded assets, install ald00, and check health.
  reinstall-instance
                   Recreate only ald00 instance state using the retained verified
                   kit, composition receipt, CAS, and external control plane.
  health           Read-only health check for the installed composition.
  probe-self-test  Run the downloaded deterministic TypeScript probe tests with Bun.

The AIWSL developer preview supports only instance ald00. The default root is
$HOME/.local/share/agentlab/ald00-alpha9; downloaded assets are retained there
for later offline installation.
EOF
}

now_ns() {
  date +%s%N
}

emit_timing() {
  local phase="$1" started_ns="$2" ended_ns="$3" exit_code="$4"
  [[ "${AGENTLAB_TIMING:-1}" == "1" ]] || return 0
  printf '{"schema":"agentlab.quickstart_timing.v1","action":"%s","phase":"%s","elapsedMs":%s,"exitCode":%s}\n' \
    "${action}" "${phase}" "$(( (ended_ns - started_ns) / 1000000 ))" "${exit_code}" >&2
}

run_timed() {
  local phase="$1" started_ns ended_ns exit_code
  shift
  started_ns="$(now_ns)"
  if "$@"; then
    exit_code=0
  else
    exit_code=$?
  fi
  ended_ns="$(now_ns)"
  emit_timing "${phase}" "${started_ns}" "${ended_ns}" "${exit_code}"
  return "${exit_code}"
}

action="${1:-}"
if [[ -z "${action}" || "${action}" == "-h" || "${action}" == "--help" ]]; then
  usage
  exit 0
fi
shift

root="${AGENTLAB_QUICKSTART_ROOT:-${HOME}/.local/share/agentlab/ald00-alpha9}"
instance="ald00"
while (( $# )); do
  case "$1" in
    --root)
      root="${2:?--root requires a directory}"
      shift 2
      ;;
    --instance)
      instance="${2:?--instance requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "${action}" in
  online-install|offline-install|reinstall-instance|health|probe-self-test) ;;
  *)
    echo "unknown action: ${action}" >&2
    usage >&2
    exit 2
    ;;
esac
if [[ "${instance}" != "ald00" ]]; then
  echo "this developer preview supports only --instance ald00" >&2
  exit 2
fi
if [[ "${root}" != /* || "${root}" == "/" || "${root}" == "${HOME}" || "${root}/" != "${HOME}/"* ]]; then
  echo "--root must be a dedicated absolute directory below the user home" >&2
  exit 2
fi
if [[ -x "${root}/bin/agentlabctl" ]]; then
  export PATH="${root}/bin:${PATH}"
fi

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command is unavailable: $1" >&2
    exit 2
  }
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "sha256sum or shasum is required" >&2
    exit 2
  fi
}

verify_file() {
  local path="$1" expected="$2" actual
  [[ -f "${path}" && ! -L "${path}" ]] || return 1
  actual="$(sha256_file "${path}")"
  [[ "${actual}" == "${expected}" ]]
}

download_verified() {
  local url="$1" path="$2" expected="$3" temporary
  if verify_file "${path}" "${expected}"; then
    printf 'reused %s\n' "${path}"
    return
  fi
  rm -f -- "${path}"
  temporary="${path}.partial.$$"
  rm -f -- "${temporary}"
  curl -fL --retry 3 --connect-timeout 20 -o "${temporary}" "${url}"
  if ! verify_file "${temporary}" "${expected}"; then
    rm -f -- "${temporary}"
    echo "downloaded asset digest mismatch: ${url}" >&2
    exit 1
  fi
  mv -f -- "${temporary}" "${path}"
  printf 'downloaded %s\n' "${path}"
}

require_cached() {
  local path="$1" expected="$2"
  if ! verify_file "${path}" "${expected}"; then
    echo "offline asset is missing or invalid: ${path}" >&2
    exit 1
  fi
  printf 'verified %s\n' "${path}"
}

downloads="${root}/downloads"
work="${root}/work"
lock="${downloads}/agentlab-aldev-environment-lock.json"
kit="${downloads}/${kit_name}"
probe="${downloads}/${probe_name}"
receipt="${work}/composition-install-receipt.json"
kit_dir="${work}/agentlab-environment-kit"
probe_dir="${work}/external-brain-ts"
action_started_ns="$(now_ns)"
on_exit() {
  local exit_code=$?
  emit_timing total "${action_started_ns}" "$(now_ns)" "${exit_code}"
}
trap on_exit EXIT

unpack_assets() {
  rm -rf -- "${kit_dir}" "${probe_dir}"
  zstd -dc -- "${kit}" | tar -xf - -C "${work}"
  zstd -dc -- "${probe}" | tar -xf - -C "${work}"
}

require_prepared_install() {
  [[ -s "${receipt}" ]] || {
    echo "composition receipt is missing; run online-install or offline-install first" >&2
    return 1
  }
  [[ -x "${kit_dir}/agentlab-env" ]] || {
    echo "prepared environment kit is missing; run online-install or offline-install first" >&2
    return 1
  }
  [[ -d "${root}/acquired-aldev" ]] || {
    echo "prepared composition is missing; run online-install or offline-install first" >&2
    return 1
  }
}

validate_retained_control_plane() {
  local config expected_host expected_url secret_root image_ref target_host target_port docker_network
  config="${kit_dir}/release/agentweb/aiwsl-agentlab.json"
  IFS=$'\t' read -r expected_host expected_url secret_root image_ref target_host target_port docker_network < <(
    python3 - "${config}" "${receipt}" "${instance}" <<'PY'
import json, pathlib, sys
config = json.loads(pathlib.Path(sys.argv[1]).read_text())
receipt = json.loads(pathlib.Path(sys.argv[2]).read_text())
dep = config["deployments"][sys.argv[3]]
controller = dep.get("controllerEnvironment") or {}
loopback = dep.get("mcpgitLoopback") or {}
images = receipt.get("images") or []
runtime = next((row for row in images if row.get("slot") == "runtime"), None)
values = (
    controller.get("MCPGIT_GLOBAL_ORGANIZATION_HOST"),
    controller.get("MCPGIT_GLOBAL_SERVICE_URL"),
    loopback.get("secretHostDir"),
    runtime.get("reference") if runtime else None,
    loopback.get("targetHost"),
    str(loopback.get("targetPort")) if loopback.get("targetPort") is not None else None,
    config.get("target", {}).get("dockerNetwork") or "armnet",
)
if any(not isinstance(value, str) or not value for value in values):
    raise SystemExit("retained control-plane metadata is incomplete")
print("\t".join(values))
PY
  )

  docker run --rm --pull=never --network=none --entrypoint python3 \
    -v "${secret_root}:/probe:ro" "${image_ref}" -c \
    'import json,pathlib,sys; q=json.loads(pathlib.Path("/probe/template-qualification.json").read_text()); orgs=q.get("organizations") or []; scope=orgs[0].get("scope") if orgs else None; assert isinstance(scope,dict); assert scope.get("organizationHost")==sys.argv[1], "retained MCPGit qualification Organization Host differs from descriptor"; assert scope.get("gatewayUrl")==sys.argv[2], "retained MCPGit qualification Gateway URL differs from descriptor"' \
    "${expected_host}" "${expected_url}" || return 1

  docker run --rm --pull=never --network="${docker_network}" --entrypoint python3 \
    -v "${secret_root}:/probe:ro" "${image_ref}" -c \
    'import pathlib,socket,sys
host=sys.argv[1]
port=int(sys.argv[2])
org=sys.argv[3]
auth=pathlib.Path("/probe/global-service-authorization").read_text().strip()
addrs={row[4][0] for row in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
assert len(addrs)==1, f"retained MCPGit target must resolve uniquely: {sorted(addrs)}"
def probe(extra):
    s=socket.create_connection((host,port),3)
    s.settimeout(3)
    req=("GET /__mcpgit/service-ws HTTP/1.1\r\n"+f"Host: {org}\r\n"+"Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==\r\nSec-WebSocket-Protocol: mcpgit.service.ws.v1\r\n"+extra+"\r\n")
    s.sendall(req.encode("ascii"))
    f=s.makefile("rb")
    status=f.readline().strip()
    f.close()
    s.close()
    return status
u=probe("")
assert u==b"HTTP/1.1 401 Unauthorized", f"retained MCPGit route is not qualified: {u!r}"
a=probe("Authorization: "+auth+"\r\n")
assert a==b"HTTP/1.1 101 Switching Protocols", f"retained MCPGit authorization is not admitted: {a!r}"' \
    "${target_host}" "${target_port}" "${expected_host}" || return 1
}

reinstall_instance() {
  local uninstall config
  require_prepared_install || return 1
  uninstall="${kit_dir}/scripts/agentlab-ald-uninstall.py"
  config="${kit_dir}/release/agentweb/aiwsl-agentlab.json"
  [[ -x "${uninstall}" && -s "${config}" ]] || {
    echo "prepared uninstall/config surface is incomplete" >&2
    return 1
  }

  # Fail before destructive work when the retained external control plane is
  # not qualified for this exact descriptor. This converts a late readiness
  # timeout into a bounded precondition failure.
  validate_retained_control_plane || return 1

  "${uninstall}" "${instance}" --config "${config}" \
    --execute --confirm-instance "${instance}" \
    --purge-data --purge-sessionfs --purge-control \
    --confirm-purge "PURGE ${instance}" \
    --confirm-data-volume "vol-data-${instance}" \
    --confirm-sessionfs-image "${instance}-sessionfs-image" || return 1

  env AGENTLAB_TIMING="${AGENTLAB_TIMING:-1}" \
    "${kit_dir}/agentlab-env" install \
    --instance "${instance}" \
    --composition-receipt "${receipt}" \
    --release-id alpha9-quickstart-v1
}

acquire_online_assets() {
  download_verified \
    "https://github.com/${release_repo}/releases/download/${version}/${kit_name}" \
    "${kit}" "${kit_sha}"
  download_verified \
    "https://github.com/${release_repo}/releases/download/${version}/${probe_name}" \
    "${probe}" "${probe_sha}"
  if [[ ! -s "${lock}" ]]; then
    temporary_lock="${lock}.partial.$$"
    curl -fL --retry 3 --connect-timeout 20 -o "${temporary_lock}" \
      "https://github.com/${release_repo}/releases/download/aldev/agentlab-aldev-environment-lock.json"
    mv -f -- "${temporary_lock}" "${lock}"
  fi
  if ! command -v agentlabctl >/dev/null 2>&1; then
    bootstrap="${downloads}/agentlab-bootstrap.sh"
    curl -fL --retry 3 --connect-timeout 20 -o "${bootstrap}.partial.$$" \
      "https://github.com/${release_repo}/releases/download/alcontrol/agentlab-bootstrap.sh"
    mv -f -- "${bootstrap}.partial.$$" "${bootstrap}"
    sh "${bootstrap}" --current --install-dir "${root}/bin"
    export PATH="${root}/bin:${PATH}"
  fi
}

verify_offline_assets() {
  require_cached "${kit}" "${kit_sha}"
  require_cached "${probe}" "${probe_sha}"
  [[ -s "${lock}" ]] || { echo "offline lock is missing: ${lock}" >&2; return 1; }
}

if [[ "${action}" == "online-install" || "${action}" == "offline-install" ]]; then
  require_command tar
  require_command zstd
  require_command docker
  mkdir -p -- "${downloads}" "${work}"

  if [[ "${action}" == "online-install" ]]; then
    require_command curl
    run_timed acquire-control-assets acquire_online_assets
  else
    run_timed verify-cached-assets verify_offline_assets
  fi
  require_command agentlabctl

  run_timed unpack-assets unpack_assets

  if [[ "${action}" == "online-install" ]]; then
    run_timed fetch-composition agentlabctl fetch composition \
      --lock "${lock}" \
      --platform linux-x64 \
      --out-dir "${root}/acquired-aldev" \
      --cache-dir "${root}/public-cas"
  elif [[ ! -d "${root}/acquired-aldev" ]]; then
    echo "offline acquired composition is missing: ${root}/acquired-aldev" >&2
    exit 1
  fi
  run_timed install-composition agentlabctl composition install-docker \
    --dir "${root}/acquired-aldev" \
    --platform linux-x64 \
    --receipt "${receipt}"
  # install performs the same fail-closed aggregate preflight immediately
  # before mutation. Running qualify here duplicated that full check and added
  # about 13 seconds to every cached installation.
  run_timed install-environment env AGENTLAB_TIMING="${AGENTLAB_TIMING:-1}" \
    "${kit_dir}/agentlab-env" install \
    --instance "${instance}" \
    --composition-receipt "${receipt}" \
    --release-id alpha9-quickstart-v1
elif [[ "${action}" == "reinstall-instance" ]]; then
  require_command docker
  run_timed reinstall-instance reinstall_instance
fi

[[ -s "${receipt}" ]] || {
  echo "composition receipt is missing; run online-install or offline-install first" >&2
  exit 1
}
[[ -x "${kit_dir}/agentlab-env" ]] || {
  echo "environment kit is missing; run online-install or offline-install first" >&2
  exit 1
}

if [[ "${action}" == "probe-self-test" ]]; then
  bun_bin="$(command -v bun || true)"
  if [[ -z "${bun_bin}" ]]; then
    for candidate in "${HOME}/.bun/bin/bun" "${HOME}/bin/bun"; do
      if [[ -x "${candidate}" ]]; then
        bun_bin="${candidate}"
        break
      fi
    done
  fi
  if [[ -z "${bun_bin}" ]]; then
    echo "Bun is required for probe-self-test; install it or add it to PATH" >&2
    exit 2
  fi
  [[ -f "${probe_dir}/package.json" ]] || {
    echo "TypeScript probe is missing; run online-install or offline-install first" >&2
    exit 1
  }
  (cd -- "${probe_dir}" && "${bun_bin}" test)
else
  run_timed health env AGENTLAB_TIMING="${AGENTLAB_TIMING:-1}" \
    "${kit_dir}/agentlab-env" health --instance "${instance}" --composition-receipt "${receipt}"
fi
