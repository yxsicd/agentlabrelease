#!/usr/bin/env bash
set -euo pipefail

root="${AGENTLAB_CI_ROOT:?AGENTLAB_CI_ROOT is required}"
composition="${AGENTLAB_COMPOSITION_DIR:?AGENTLAB_COMPOSITION_DIR is required}"
fast="${AGENTLAB_FAST_SUBJECT_ROOT:?AGENTLAB_FAST_SUBJECT_ROOT is required}"
downloads="$root/downloads"
assets="$fast/assets"
cli_root="$fast/harmony-cli"
kit_root="$fast/harmony-build-kit"
lock="$composition/environment-lock.json"

mkdir -p "$downloads" "$assets" "$cli_root" "$kit_root"
cp "$lock" "$downloads/environment-lock.json"
cp "$composition/publication.json" "$downloads/publication.json"

readarray -t values < <(python3 - "$lock" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
image=next(x for x in d['images'] if x['slot']=='runtime')
cli=next(x for x in d['components'] if x['slot']=='harmony-cli')
kit=next(x for x in d['components'] if x['slot']=='harmony-build-kit')
for value in (
 image['artifact'],image['archiveSha256'],image['imageId'],image['reference'],
 cli['artifact'],cli['archiveSha256'],
 kit['artifact'],kit['archiveSha256']): print(value)
PY
)

fetch() {
  local url=$1 sha=$2 out=$3
  if [[ -s "$out" ]] && printf '%s  %s\n' "$sha" "$out" | sha256sum -c - >/dev/null 2>&1; then return 0; fi
  rm -f "$out" "$out.partial"
  curl -fL --retry 3 --retry-all-errors --retry-delay 2 --connect-timeout 20 -o "$out.partial" "$url"
  printf '%s  %s\n' "$sha" "$out.partial" | sha256sum -c -
  mv "$out.partial" "$out"
}

runtime_archive="$assets/runtime.docker.tar.zst"
fetch "${values[0]}" "${values[1]}" "$runtime_archive"

cli_marker="$cli_root/.agentlab-fast-sha256"
if [[ ! -f "$cli_marker" || "$(cat "$cli_marker")" != "${values[5]}" ]]; then
  cli_archive="$assets/harmony-cli.tar.zst"
  fetch "${values[4]}" "${values[5]}" "$cli_archive"
  rm -rf "$cli_root"; mkdir -p "$cli_root"
  zstd -dc "$cli_archive" | tar -xf - -C "$cli_root"
  test -x "$cli_root/tool/node/bin/node"
  test -f "$cli_root/sdk/default/openharmony/ets/oh-uni-package.json"
  test -f "$cli_root/hvigor/hvigor/bin/hvigor-simple.js"
  printf '%s\n' "${values[5]}" > "$cli_marker"
fi

kit_marker="$kit_root/.agentlab-fast-sha256"
if [[ ! -f "$kit_marker" || "$(cat "$kit_marker")" != "${values[7]}" ]]; then
  kit_archive="$assets/harmony-build-kit.tar.zst"
  fetch "${values[6]}" "${values[7]}" "$kit_archive"
  rm -rf "$kit_root"; mkdir -p "$kit_root"
  zstd -dc "$kit_archive" | tar -xf - -C "$kit_root" --strip-components=1 payload
  test -x "$kit_root/bin/harmony"
  printf '%s\n' "${values[7]}" > "$kit_marker"
fi

zstd -dc "$runtime_archive" | docker load >/dev/null
actual=$(docker image inspect "${values[3]}" --format '{{.Id}}')
test "$actual" = "${values[2]}"

python3 - "$root/fast-subject-install.json" "${values[1]}" "${values[5]}" "${values[7]}" "$actual" <<'PY'
import json,sys
path,runtime,cli,kit,image=sys.argv[1:]
open(path,'w').write(json.dumps(dict(schema='agentlab.fast_subject_install.v1',runtimeArchiveSha256=runtime,harmonyCliSha256=cli,buildKitSha256=kit,imageId=image),indent=2)+'\n')
PY
