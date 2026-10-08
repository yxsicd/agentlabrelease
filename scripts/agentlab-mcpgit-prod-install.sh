#!/bin/sh
# Pinned GitHub-only MCPGit successor integration. Not full Harness qualification.
set -eu
umask 077
usage() {
  echo 'Usage: agentlab-mcpgit-prod-install.sh install|download|check [--root DIR] [--instance NAME] [--port PORT]' >&2
  exit 2
}
[ $# -gt 0 ] || usage
action=$1; shift
case "$action" in install|download|check) ;; *) usage ;; esac
root=${XDG_DATA_HOME:-$HOME/.local/share}/agentlab/mcpgit-prod-a75b9809
instance=agentlab-mcpgit-prod
port=18095
while [ $# -gt 0 ]; do
  [ $# -ge 2 ] || usage
  case "$1" in
    --root) root=$2 ;;
    --instance) instance=$2 ;;
    --port) port=$2 ;;
    *) usage ;;
  esac
  shift 2
done
case "$root" in /*) ;; *) echo 'root must be absolute' >&2; exit 2 ;; esac
case "$root" in /) echo 'root must not be /' >&2; exit 2 ;; esac
[ ! -L "$root" ] || { echo 'root must not be a symlink' >&2; exit 2; }
case "$instance" in agentlab-*) ;; *) echo 'instance must use the agentlab- namespace' >&2; exit 2 ;; esac
for dep in curl python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "missing required dependency: $dep" >&2; exit 1; }
done
python3 - "$instance" "$port" <<'PY'
import re,sys
assert re.fullmatch(r'agentlab-[A-Za-z0-9_.-]{1,119}',sys.argv[1]), 'invalid AgentLab instance name'
assert sys.argv[2].isdigit() and 1 <= int(sys.argv[2]) <= 65535, 'invalid port'
PY
if [ "$action" != download ]; then
  command -v docker >/dev/null 2>&1 || { echo 'missing required dependency: docker' >&2; exit 1; }
  docker version >/dev/null
fi
mkdir -p "$root/bootstrap"
snapshot=ce380809aaa5187f75adc9aed74053c0933661a0
tag=mcpgit-git-a75b9809857cea23047b61f3acea17bc09b9996c-linux-amd64
fetch_verified() {
  url=$1; path=$2; bytes=$3; sha=$4
  curl -fLSs --connect-timeout 10 --max-time 120 "$url" -o "$path"
  python3 - "$path" "$bytes" "$sha" <<'PY'
import hashlib,pathlib,sys
raw=pathlib.Path(sys.argv[1]).read_bytes()
assert len(raw)==int(sys.argv[2]), 'download size mismatch'
assert hashlib.sha256(raw).hexdigest()==sys.argv[3], 'download digest mismatch'
PY
}
fetch_verified "https://raw.githubusercontent.com/yxsicd/mcpgitrelease/$snapshot/install.sh" "$root/bootstrap/install.sh" 1732 de23d36fdf8fc444eb74a64ec0bb89ee00120b9accae6232e639168ec4a27c0f
fetch_verified "https://github.com/yxsicd/mcpgitrelease/releases/download/$tag/mcpgit-offline-release-v1.json" "$root/bootstrap/manifest.json" 1944 c623bb1b87d7f168bb6874ef7bf0add32e75d7e6f53d2baf55b0f9a2dd836e84
# Force the documented immutable snapshot path; no GitHub API discovery or LAN source.
export MCPGIT_INSTALL_REVISION="$snapshot"
export MCPGIT_INSTALL_BASE_URL="https://raw.githubusercontent.com/yxsicd/mcpgitrelease/$snapshot/deploy"
export MCPGIT_INSTALL_CONTENT_BASE="https://raw.githubusercontent.com/yxsicd/mcpgitrelease/$snapshot"
export MCPGIT_CHANNEL_URL="$MCPGIT_INSTALL_CONTENT_BASE/offline-latest.json"
export MCPGIT_RELEASE_TAG="$tag"
export MCPGIT_BUNDLE_DIR="$root/bundle"
export MCPGIT_CREDENTIAL_DIR="$root/credentials"
export MCPGIT_INSTANCE_CONFIG_DIR="$root/instances"
export MCPGIT_STATE_DIR="$root/install-state"
export MCPGIT_BIN_DIR="$root/bin"
export MCPGIT_BIND_ADDRESS=127.0.0.1
export MCPGIT_NETRC=
set -- --instance "$instance" --port "$port" --data-volume "${instance}-data"
case "$action" in
  download) set -- "$@" --download-only ;;
  check) set -- "$@" --check ;;
esac
sh "$root/bootstrap/install.sh" "$@"
# Acceptance cannot depend on a different manifest being downloaded by the backend.
python3 - "$root/bundle/mcpgit-offline-release-v1.json" <<'PY'
import hashlib,pathlib,sys
raw=pathlib.Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(raw).hexdigest()=='c623bb1b87d7f168bb6874ef7bf0add32e75d7e6f53d2baf55b0f9a2dd836e84', 'backend manifest differs from integration pin'
PY
echo "PASS: pinned MCPGit $action completed; credentials remain private under the selected root"
