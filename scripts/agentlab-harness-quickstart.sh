#!/usr/bin/env bash
set -euo pipefail

version="v0.1.0-alpha.9"
release_repo="yxsicd/agentlabrelease"
kit_name="agentlab-environment-kit-v0.1.0-alpha.9.tar.zst"
probe_name="agentlab-ts-probe-v0.1.0-alpha.9.tar.zst"
kit_sha="fcca40e0858bbbde7620ddec83db0dc525c62d597926dc27ef66b6dd54c27a73"
probe_sha="029074b412bdaaccd069250949eec459861e685a5ef398fbbc30d4c7cbf4d2d3"
harmony_version="6.1.1.300"
harmony_name="harmony-linux-x64-6.1.1.300.tar.zst"
harmony_sha="8fc2199afaea5055c6a3ff762b7b58a9475c5ff7b6c30285336014dc647927c2"
harmony_bytes="989968633"
harmony_url="https://github.com/yxsicd/agentlabrelease/releases/download/harmony-linux-x64-6.1.1.300/${harmony_name}"
harmony_volume="vol-harmony"

usage() {
  cat <<'EOF'
Usage: agentlab-harness-quickstart.sh ACTION [--root DIR] [--instance ald00]

Actions:
  online-install   Download missing immutable assets, install ald00, and check health.
  offline-install  Use only previously downloaded assets, install ald00, and check health.
  install-plan     Read-only preflight report for paths, cached assets, Docker state, and prepared artifacts.
  reinstall-instance
                   Recreate only ald00 main runtime using the retained verified
                   release, volumes, SessionFS companion, and external control plane.
  reset-instance    Destructively purge ALD data and SessionFS, then reinstall.
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
  online-install|offline-install|install-plan|reinstall-instance|reset-instance|health|probe-self-test) ;;
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
  [[ -f "${path}" ]] || return 1
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
harmony_archive="${downloads}/${harmony_name}"
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
  local config deploy_dir compose_args started ended hs ss
  require_prepared_install || return 1
  config="${kit_dir}/release/agentweb/aiwsl-agentlab.json"
  [[ -s "${config}" ]] || { echo "prepared config is missing" >&2; return 1; }
  validate_retained_control_plane || return 1

  deploy_dir="${HOME}/.agentlab/deployments/agentlab/${instance}/releases/alpha9-quickstart-v1"
  [[ -s "${deploy_dir}/bundle.env" && -s "${deploy_dir}/docker-compose.yaml" ]] || {
    echo "prepared direct deployment is missing; run offline-install once" >&2
    return 1
  }
  docker volume inspect "vol-data-${instance}" >/dev/null 2>&1 || {
    echo "instance data volume is absent; use reset-instance or offline-install" >&2
    return 1
  }
  for volume in "${instance}-sessionfs-image" "${instance}-sessionfs-export" "${instance}-sessionfs-control"; do
    docker volume inspect "${volume}" >/dev/null 2>&1 || {
      echo "retained SessionFS volume is absent (${volume}); use reset-instance" >&2
      return 1
    }
  done
  [[ "$(docker inspect "${instance}-sessionfs" --format '{{.State.Status}}' 2>/dev/null || true)" == running ]] || {
    echo "retained SessionFS companion is not running; use reset-instance" >&2
    return 1
  }
  [[ "$(docker inspect "${instance}-sessionfs" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)" == healthy ]] || {
    echo "retained SessionFS companion is not healthy; use reset-instance" >&2
    return 1
  }

  compose_args=(-f docker-compose.yaml -f docker-compose.sessionfs.yaml -f docker-compose.main-loopbacks.yaml)
  started="$(now_ns)"
  (cd "${deploy_dir}" && docker compose --env-file bundle.env "${compose_args[@]}" -p "${instance}" up -d --force-recreate --no-deps "${instance}") || return 1
  ended="$(now_ns)"
  emit_timing recreate-main "${started}" "${ended}" 0

  started="$(now_ns)"
  hs= ss=
  for _ in $(seq 1 60); do
    hs="$(docker inspect "${instance}" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)"
    ss="$(docker exec "${instance}" supervisorctl status sandboxrs 2>/dev/null | awk '{print $2}' || true)"
    [[ "${hs}" == healthy && "${ss}" == RUNNING ]] && break
    sleep 0.25
  done
  [[ "${hs}" == healthy && "${ss}" == RUNNING ]] || {
    echo "instance-only readiness timed out (health=${hs:-missing}, sandbox=${ss:-missing})" >&2
    return 1
  }
  ended="$(now_ns)"
  emit_timing instance-ready "${started}" "${ended}" 0
}

reset_instance() {
  local uninstall config
  require_prepared_install || return 1
  validate_retained_control_plane || return 1
  uninstall="${kit_dir}/scripts/agentlab-ald-uninstall.py"
  config="${kit_dir}/release/agentweb/aiwsl-agentlab.json"
  "${uninstall}" "${instance}" --config "${config}" \
    --execute --confirm-instance "${instance}" \
    --purge-data --purge-sessionfs --purge-control \
    --confirm-purge "PURGE ${instance}" \
    --confirm-data-volume "vol-data-${instance}" \
    --confirm-sessionfs-image "${instance}-sessionfs-image" || return 1
  env AGENTLAB_TIMING="${AGENTLAB_TIMING:-1}" \
    "${kit_dir}/agentlab-env" install \
    --instance "${instance}" --composition-receipt "${receipt}" \
    --release-id alpha9-quickstart-v1 || return 1
}

harmony_volume_exists() {
  docker volume inspect "${harmony_volume}" >/dev/null 2>&1
}

install_harmony_volume() {
  local runtime_image created=0 marker
  harmony_volume_exists && return 0
  [[ -f "${harmony_archive}" ]] || {
    echo "Harmony archive is unavailable: ${harmony_archive}" >&2
    return 1
  }
  [[ "$(sha256_file "${harmony_archive}")" == "${harmony_sha}" ]] || {
    echo "Harmony archive digest mismatch" >&2
    return 1
  }
  [[ "$(wc -c < "${harmony_archive}" | tr -d ' ')" == "${harmony_bytes}" ]] || {
    echo "Harmony archive byte count mismatch" >&2
    return 1
  }
  runtime_image="$(python3 - "${receipt}" <<'PY2'
import json,pathlib,sys
r=json.loads(pathlib.Path(sys.argv[1]).read_text())
row=next((x for x in r.get('images',[]) if x.get('slot')=='runtime'),None)
if not row or not row.get('reference'): raise SystemExit(1)
print(row['reference'])
PY2
)" || return 1
  docker image inspect "${runtime_image}" >/dev/null 2>&1 || {
    echo "runtime image must be installed before Harmony volume initialization" >&2
    return 1
  }
  docker volume create "${harmony_volume}" >/dev/null || return 1
  created=1
  if ! zstd --long=30 -dc -- "${harmony_archive}" | \
      docker run --rm -i --network=none -v "${harmony_volume}:/target" \
        --entrypoint tar "${runtime_image}" -xf - -C /target; then
    [[ "${created}" == 1 ]] && docker volume rm "${harmony_volume}" >/dev/null 2>&1 || true
    echo "Harmony volume extraction failed" >&2
    return 1
  fi
  marker="harmony-${harmony_version}-${harmony_sha}"
  if ! docker run --rm --network=none -v "${harmony_volume}:/target" \
      --entrypoint sh "${runtime_image}" -ceu \
      'test -x /target/bin/ohpm; test -x /target/ohpm/bin/ohpm; mkdir -p /target/.agentlab-harmony; printf "%s\n" "$1" > /target/.agentlab-harmony/READY' \
      sh "${marker}"; then
    [[ "${created}" == 1 ]] && docker volume rm "${harmony_volume}" >/dev/null 2>&1 || true
    echo "Harmony volume postcondition failed" >&2
    return 1
  fi
}

acquire_harmony_online() {
  harmony_volume_exists && return 0
  download_verified "${harmony_url}" "${harmony_archive}" "${harmony_sha}"
  [[ "$(wc -c < "${harmony_archive}" | tr -d ' ')" == "${harmony_bytes}" ]] || {
    echo "Harmony asset byte count mismatch" >&2
    return 1
  }
}

require_harmony_offline() {
  harmony_volume_exists && return 0
  require_cached "${harmony_archive}" "${harmony_sha}" || return 1
  [[ "$(wc -c < "${harmony_archive}" | tr -d ' ')" == "${harmony_bytes}" ]] || {
    echo "offline Harmony asset byte count mismatch" >&2
    return 1
  }
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

install_plan() {
  python3 - "${root}" "${instance}" "${downloads}" "${work}" "${kit}" "${kit_sha}" "${probe}" "${probe_sha}" "${harmony_archive}" "${harmony_sha}" "${harmony_bytes}" "${lock}" "${receipt}" "${kit_dir}" "${harmony_volume}" <<'PYPLAN'
import hashlib, json, os, pathlib, shutil, subprocess, sys
root, instance, downloads, work, kit, kit_sha, probe, probe_sha, harmony, harmony_sha, harmony_bytes, lock, receipt, kit_dir, harmony_volume = sys.argv[1:]

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(8<<20), b''):
            h.update(chunk)
    return h.hexdigest()

def asset(label, path, expected_sha=None, expected_bytes=None):
    p=pathlib.Path(path)
    row={"name":label,"path":str(p),"exists":p.exists(),"isSymlink":p.is_symlink()}
    if p.exists():
        row["resolvedPath"]=str(p.resolve()) if p.is_symlink() else str(p)
        row["bytes"]=p.stat().st_size
        if expected_bytes is not None:
            row["expectedBytes"]=int(expected_bytes)
            row["bytesOk"]=(p.stat().st_size==int(expected_bytes))
        if expected_sha:
            got=sha256(p)
            row["sha256"]=got
            row["expectedSha256"]=expected_sha
            row["sha256Ok"]=(got==expected_sha)
            row["ok"]=row.get("bytesOk", True) and row["sha256Ok"]
        else:
            row["ok"]=True
    else:
        row["ok"]=False
    return row

def docker_available():
    return shutil.which('docker') is not None

def docker_inspect(kind, name):
    if not docker_available():
        return {"name":name,"exists":False,"error":"docker_unavailable"}
    try:
        if kind == 'volume':
            r=subprocess.run(['docker','volume','inspect',name],capture_output=True,text=True,timeout=3)
        else:
            r=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=3)
    except Exception as e:
        return {"name":name,"exists":False,"error":type(e).__name__}
    if r.returncode != 0:
        return {"name":name,"exists":False}
    data=json.loads(r.stdout)[0]
    row={"name":name,"exists":True}
    if kind == 'container':
        state=data.get('State') or {}
        row.update({"status":state.get('Status'),"health":(state.get('Health') or {}).get('Status'),"image":(data.get('Config') or {}).get('Image')})
    return row

assets=[
    asset('environment-kit', kit, kit_sha),
    asset('typescript-probe', probe, probe_sha),
    asset('harmony', harmony, harmony_sha, harmony_bytes),
    asset('environment-lock', lock),
]
commands={name: bool(shutil.which(name)) for name in ['tar','zstd','docker','curl','agentlabctl','python3']}
prepared={
    'receipt': pathlib.Path(receipt).is_file(),
    'kitDir': pathlib.Path(kit_dir).is_dir(),
    'agentlabEnv': pathlib.Path(kit_dir,'agentlab-env').is_file(),
    'acquiredAlDev': pathlib.Path(root,'acquired-aldev').is_dir(),
}
docker={
    'volumes':[docker_inspect('volume', n) for n in [harmony_volume, f'vol-data-{instance}', f'{instance}-sessionfs-image', f'{instance}-sessionfs-export', f'{instance}-sessionfs-control']],
    'containers':[docker_inspect('container', n) for n in [instance, f'{instance}-sessionfs', 'ala00-mcpgit', 'ala00-mcpgit-gateway']],
}
plan={
    'schema':'agentlab.quickstart_install_plan.v1',
    'action':'install-plan',
    'readOnly':True,
    'root':root,
    'instance':instance,
    'downloads':downloads,
    'work':work,
    'commands':commands,
    'assets':assets,
    'prepared':prepared,
    'docker':docker,
    'okForOfflineInstall': bool(commands.get('tar') and commands.get('zstd') and commands.get('docker') and all(a.get('ok') for a in assets)),
    'credentialsIncluded':False,
}
print(json.dumps(plan,indent=2,sort_keys=True))
PYPLAN
}

if [[ "${action}" == "install-plan" ]]; then
  install_plan
  exit 0
fi

if [[ "${action}" == "online-install" || "${action}" == "offline-install" ]]; then
  require_command tar
  require_command zstd
  require_command docker
  mkdir -p -- "${downloads}" "${work}"

  if [[ "${action}" == "online-install" ]]; then
    require_command curl
    run_timed acquire-control-assets acquire_online_assets
    run_timed acquire-harmony acquire_harmony_online
  else
    run_timed verify-cached-assets verify_offline_assets
    run_timed verify-harmony require_harmony_offline
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
  run_timed install-harmony install_harmony_volume
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
elif [[ "${action}" == "reset-instance" ]]; then
  require_command docker
  run_timed reset-instance reset_instance
fi

[[ -s "${receipt}" ]] || {
  echo "composition receipt is missing; run online-install or offline-install first" >&2
  exit 1
}
[[ -x "${kit_dir}/agentlab-env" ]] || {
  echo "environment kit is missing; run online-install or offline-install first" >&2
  exit 1
}

if [[ "${action}" == "reinstall-instance" ]]; then
  # The fast path already proves retained SessionFS health before mutation and
  # main-container health plus sandbox readiness after recreation. Avoid the
  # generic full health pass here; reset/offline installs still use it.
  exit 0
fi

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
