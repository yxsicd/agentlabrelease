#!/usr/bin/env bash
set -euo pipefail

repo="${AGENTLAB_RELEASE_REPO:-yxsicd/agentlabrelease}"
channel="${AGENTLAB_RELEASE_CHANNEL:-alprod}"
root="${AGENTLAB_CI_ROOT:-${RUNNER_TEMP:-/tmp}/agentlab-public-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}}"
downloads="${root}/downloads"
composition="${root}/composition"
cas="${root}/cas"
install_bin="${root}/bin"
standalone="${root}/standalone"
sessionfs="${root}/sessionfs"
tasks="${sessionfs}/tasks"
summary="${root}/summary.json"
ops_pid=""
sessionfs_pid=""

mkdir -p "${downloads}" "${composition}" "${cas}" "${install_bin}" \
  "${standalone}" "${tasks}" "${sessionfs}"

cleanup() {
  if [[ -n "${ops_pid}" ]]; then kill "${ops_pid}" 2>/dev/null || true; fi
  if [[ -n "${sessionfs_pid}" ]]; then kill "${sessionfs_pid}" 2>/dev/null || true; fi
}
trap cleanup EXIT

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command is unavailable: $1" >&2
    exit 2
  }
}
for command in curl docker python3 sha256sum tar zstd; do need "${command}"; done

download() {
  local url="$1" out="$2"
  curl -fL --retry 3 --retry-all-errors --retry-delay 2 \
    --connect-timeout 20 -o "${out}.partial" "${url}"
  mv -f "${out}.partial" "${out}"
}

release_url="https://github.com/${repo}/releases/download"
lock="${downloads}/environment-lock.json"
publication="${downloads}/publication.json"
if [[ -n "${AGENTLAB_COMPOSITION_DIR:-}" ]]; then
  cp "${AGENTLAB_COMPOSITION_DIR}/environment-lock.json" "${lock}"
  cp "${AGENTLAB_COMPOSITION_DIR}/publication.json" "${publication}"
else
  download "${release_url}/${channel}/agentlab-${channel}-environment-lock.json" "${lock}"
  download "${release_url}/${channel}/agentlab-${channel}-publication.json" "${publication}"
fi

python3 - "${repo}" "${channel}" "${lock}" "${publication}" <<'PY'
import hashlib, json, pathlib, sys, urllib.parse

repo, channel = sys.argv[1:3]
lock_path, publication_path = map(pathlib.Path, sys.argv[3:5])
lock_bytes = lock_path.read_bytes()
lock = json.loads(lock_bytes)
publication = json.loads(publication_path.read_bytes())

assert lock["schema"] == "agentlab.environment_lock.v3"
if publication["status"] == "candidate":
    assert publication["schema"] == "agentlab.reference_publication.v1"
    assert publication["tag"] == channel
else:
    assert lock["tier"] == "prod"
    assert publication["schema"] == "agentlab.reference_publication.v2"
    assert publication["status"] == "fixed"
    assert publication["tag"] == channel
    assert all(value == "passed" for value in publication["gates"].values())
assert publication["sourceRevision"] == lock["sourceRevision"]
assert publication["environmentLockSha256"] == hashlib.sha256(lock_bytes).hexdigest()
assert publication["componentPayloadsUploaded"] is False

expected_prefix = f"/{repo}/releases/download/"
for component in lock["images"] + lock["components"]:
    for field in ("artifact", "descriptor"):
        parsed = urllib.parse.urlsplit(component[field])
        assert parsed.scheme == "https" and parsed.netloc == "github.com"
        assert parsed.path.startswith(expected_prefix)
        assert not parsed.query and not parsed.fragment

print(json.dumps({
    "schema": "agentlab.public_composition_admission.v1",
    "ok": True,
    "channel": channel,
    "sourceRevision": lock["sourceRevision"],
    "environmentLockSha256": hashlib.sha256(lock_bytes).hexdigest(),
}, sort_keys=True))
PY

source_revision="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sourceRevision"])' "${lock}")"
source_short="${source_revision:0:8}"
# A component-only candidate can reuse the exact published controller declared
# by its publication. Controller version and runtime version are independent.
if [[ -n "${AGENTLAB_COMPOSITION_DIR:-}" ]]; then
  source_short="$(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(p["controllerSourceShort"])' "${publication}")"
fi
control_release="${downloads}/matching-control-release.json"
control_api="https://api.github.com/repos/${repo}/releases/tags/control-${source_short}-linux-x64"
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  curl -fsSL --retry 3 --retry-all-errors --retry-delay 2 \
    -H 'Accept: application/vnd.github+json' \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "${control_api}" -o "${control_release}"
else
  curl -fsSL --retry 3 --retry-all-errors --retry-delay 2 \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "${control_api}" -o "${control_release}"
fi
readarray -t control < <(python3 - "${control_release}" "${source_short}" <<'PY'
import json, sys
release = json.load(open(sys.argv[1]))
short = sys.argv[2]
name = f"agentlabctl-{short}-linux-x64"
asset = next(row for row in release["assets"] if row["name"] == name)
assert asset["digest"].startswith("sha256:")
print(asset["browser_download_url"])
print(asset["digest"].removeprefix("sha256:"))
print(asset["size"])
PY
)
agentlabctl="${install_bin}/agentlabctl"
download "${control[0]}" "${agentlabctl}"
[[ "$(wc -c < "${agentlabctl}")" == "${control[2]}" ]]
printf '%s  %s\n' "${control[1]}" "${agentlabctl}" | sha256sum -c -
chmod +x "${agentlabctl}"

"${agentlabctl}" fetch composition \
  --lock "${lock}" \
  --platform linux-x64 \
  --out-dir "${composition}" \
  --cache-dir "${cas}"
"${agentlabctl}" composition install-docker \
  --dir "${composition}" \
  --platform linux-x64 \
  --receipt "${root}/composition-install-receipt.json"

python3 - "${lock}" "${root}/docker-identities" <<'PY'
import json, pathlib, sys
lock = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
out.mkdir()
(out / "images").write_text("\n".join(row["reference"] for row in lock["images"] if row.get("enabled", True)) + "\n")
(out / "volumes").write_text("\n".join(row["volume"] for row in lock["components"] if row.get("enabled", True)) + "\n")
PY
while IFS= read -r image; do [[ -z "${image}" ]] || docker image inspect "${image}" >/dev/null; done < "${root}/docker-identities/images"
while IFS= read -r volume; do [[ -z "${volume}" ]] || docker volume inspect "${volume}" >/dev/null; done < "${root}/docker-identities/volumes"

harmony_manifest="${downloads}/harmony-combined.json"
harmony_archive="${downloads}/harmony-combined.tar.zst"
# The standalone portable tier is pinned separately from the main runtime.
readarray -t harmony < <(python3 - <<'PY'
import json, sys
print("alharmony-combined-linux-x64-218ce52.json")
print("alharmony-combined-linux-x64-218ce52.tar.zst")
print("0d854c293f76ea3f16c55c61091fc817523a2e574c38e0516e5dea0280010352")
print(389602)
PY
)
download "${release_url}/alharmony/${harmony[0]}" "${harmony_manifest}"
download "${release_url}/alharmony/${harmony[1]}" "${harmony_archive}"
[[ "$(wc -c < "${harmony_archive}")" == "${harmony[3]}" ]]
printf '%s  %s\n' "${harmony[2]}" "${harmony_archive}" | sha256sum -c -
python3 - "${harmony_manifest}" "${harmony_archive}" <<'PY'
import hashlib, json, pathlib, sys
manifest = json.load(open(sys.argv[1]))
archive = pathlib.Path(sys.argv[2]).read_bytes()
assert manifest["schema"] == "agentlab.alharmony_combined_release.v1"
assert manifest["platform"] == "linux-x64"
assert manifest["bytes"] == len(archive)
assert manifest["sha256"] == hashlib.sha256(archive).hexdigest()
PY
zstd -dc "${harmony_archive}" | tar -xf - -C "${standalone}"
# SessionFS advances independently: retain the unchanged Harmony binary from
# its existing package and acquire only the corrected standalone component.
readarray -t storage_component < <(python3 - <<'PY'
import json
d = json.load(open("release/ci/standalone-sessionfs.json"))
assert d["schema"] == "agentlab.standalone_component.v1"
assert d["platform"] == "linux-x64" and d["component"] == "alsessionfsd"
print(d["artifact"])
print(d["sha256"])
print(d["bytes"])
PY
)
download "${storage_component[0]}" "${standalone}/bin/alsessionfsd"
[[ "$(wc -c < "${standalone}/bin/alsessionfsd")" == "${storage_component[2]}" ]]
printf '%s  %s\n' "${storage_component[1]}" "${standalone}/bin/alsessionfsd" | sha256sum -c -
cp release/ci/standalone-sessionfs.json "${downloads}/standalone-sessionfs.json"
chmod +x "${standalone}/bin/alsessionfsd" "${standalone}/bin/alharmony-ops"

"${standalone}/bin/alsessionfsd" serve \
  --bind 127.0.0.1:19780 \
  --backend copy-tree \
  --storage-root "${sessionfs}" >"${root}/sessionfs.log" 2>&1 &
sessionfs_pid=$!
wait_json() {
  local url="$1" out="$2"
  for _ in $(seq 1 60); do
    if curl -fsS "${url}" -o "${out}"; then return 0; fi
    sleep 1
  done
  return 1
}
wait_json http://127.0.0.1:19780/health "${root}/sessionfs-health.json"

"${standalone}/bin/alharmony-ops" serve \
  --bind 127.0.0.1:19731 \
  --workers 2 \
  --queue-capacity 8 \
  --max-active-requests 4 \
  --task-root "${tasks}" \
  --fork-backend sessionfs \
  --sessionfs-endpoint http://127.0.0.1:19780 >"${root}/harmony.log" 2>&1 &
ops_pid=$!

wait_json http://127.0.0.1:19731/health "${root}/harmony-health.json"

op() {
  local name="$1" out="$2"; shift 2
  local args=(--fail --silent --show-error --get "http://127.0.0.1:19731/v1/ops/${name}")
  local pair
  for pair in "$@"; do args+=(--data-urlencode "${pair}"); done
  curl "${args[@]}" -o "${out}"
}

parent_project="${tasks}/parent/workspace/app"
child_project="${tasks}/child/workspace/app"
op harmony.task.prepare "${root}/01-prepare.json" "taskId=parent"
op harmony.project.create "${root}/02-create.json" \
  "taskId=parent" "projectRoot=${parent_project}" "bundleName=com.agentlab.ci" \
  "appLabel=AgentLab CI" "materialize=true"
op harmony.project.verify "${root}/03-verify-parent.json" \
  "taskId=parent" "projectRoot=${parent_project}"
op harmony.task.fork "${root}/04-fork.json" "taskId=child" "parentTaskId=parent"
op harmony.project.patch "${root}/05-patch-child.json" \
  "taskId=child" "projectRoot=${child_project}" \
  "path=entry/src/main/ets/pages/Index.ets" "find=AgentLab CI" \
  "replace=AgentLab CI Iterated"
op harmony.project.verify "${root}/06-verify-child.json" \
  "taskId=child" "projectRoot=${child_project}"

python3 - "${root}" "${summary}" <<'PY'
import json, pathlib, sys
root, summary_path = map(pathlib.Path, sys.argv[1:3])
files = [root / f"{index:02d}-{name}.json" for index, name in [
    (1, "prepare"), (2, "create"), (3, "verify-parent"),
    (4, "fork"), (5, "patch-child"), (6, "verify-child"),
]]
receipts = [json.loads(path.read_text()) for path in files]
assert all(row.get("ok") is True for row in receipts)
parent = root / "sessionfs/tasks/parent/workspace/app/entry/src/main/ets/pages/Index.ets"
child = root / "sessionfs/tasks/child/workspace/app/entry/src/main/ets/pages/Index.ets"
assert "AgentLab CI Iterated" not in parent.read_text()
assert "AgentLab CI Iterated" in child.read_text()
lock = json.loads((root / "downloads/environment-lock.json").read_text())
summary = {
    "schema": "agentlab.public_install_deploy_smoke.v1",
    "ok": True,
    "compositionTier": lock["tier"],
    "sourceRevision": lock["sourceRevision"],
    "checks": {
        "compositionAdmitted": True,
        "compositionDownloaded": True,
        "dockerCompositionInstalled": True,
        "sessionFsDeployed": True,
        "harmonyServiceDeployed": True,
        "projectCreated": True,
        "projectVerified": True,
        "forkCreated": True,
        "childPatched": True,
        "parentIsolated": True,
    },
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
PY

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo '### AgentLab public installation and deployment smoke'
    echo
    echo '```json'
    cat "${summary}"
    echo '```'
  } >> "${GITHUB_STEP_SUMMARY}"
fi
