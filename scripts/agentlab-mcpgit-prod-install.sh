#!/bin/sh
# Pinned GitHub-only MCPGit integration. Not full Harness qualification.
set -eu
umask 077
usage() {
  echo 'Usage: agentlab-mcpgit-prod-install.sh install|download|check [--root DIR] [--instance NAME] [--port PORT]' >&2
}
[ $# -gt 0 ] || { usage; exit 2; }
action=$1; shift
case "$action" in install|download|check) ;; -h|--help) usage; exit 0 ;; *) usage; exit 2 ;; esac
root=${XDG_DATA_HOME:-$HOME/.local/share}/agentlab/mcpgit-prod-a75b9809
instance=agentlab-mcpgit-prod
port=18095
while [ $# -gt 0 ]; do
  [ $# -ge 2 ] || { usage; exit 2; }
  case "$1" in
    --root) root=$2 ;;
    --instance) instance=$2 ;;
    --port) port=$2 ;;
    *) usage; exit 2 ;;
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
python3 - "$instance" "$port" "$root" "$HOME" <<'PY'
import pathlib,re,sys
instance,port,root,home=sys.argv[1:]
def reject(message):
    print(message,file=sys.stderr)
    raise SystemExit(2)
if not re.fullmatch(r'agentlab-[A-Za-z0-9_.-]{1,119}',instance):
    reject('invalid AgentLab instance name')
if not port.isdigit() or not 1 <= int(port) <= 65535:
    reject('invalid port')
parts=root.split('/')
broad={'/bin','/dev','/etc','/home','/lib','/lib64','/mnt','/opt','/proc','/root','/run','/sbin','/sys','/tmp','/usr','/var'}
if (root==home or root in broad or root.endswith('/') or '//' in root
    or any(p in {'.','..'} for p in parts)
    or any(ord(c)<32 or ord(c)==127 or c in '\\"' for c in root)):
    reject('root must be a dedicated absolute private directory')
path=pathlib.Path(root)
if any(p.is_symlink() for p in (path,*path.parents)):
    reject('root must not have symlink ancestors')
if path.exists() and not path.is_dir():
    reject('root must be a directory')
for name in ('bootstrap','bundle','credentials','instances','install-state','bin'):
    if (path/name).is_symlink():
        reject('installation directories must not be symlinks')
PY
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || {
  echo 'this component cut requires Linux x86_64 (including WSL2)' >&2
  exit 2
}
if [ "$action" != download ]; then
  command -v docker >/dev/null 2>&1 || { echo 'missing required dependency: docker' >&2; exit 1; }
  docker version >/dev/null
fi
mkdir -p "$root/bootstrap"
snapshot=d32300f6953c57af1323ea71b606b363c4d99a3d
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
export MCPGIT_EXPECTED_MANIFEST_SHA256=c623bb1b87d7f168bb6874ef7bf0add32e75d7e6f53d2baf55b0f9a2dd836e84
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
