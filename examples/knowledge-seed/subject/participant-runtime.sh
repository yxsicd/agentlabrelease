#!/usr/bin/env bash
set -euo pipefail
runtime_root=$1
participant_tag=$2
mkdir -p "$runtime_root"
cache_tar=${AGENTLAB_PARTICIPANT_CACHE_TAR:-}
if [[ -n "$cache_tar" && -s "$cache_tar" ]]; then
  loaded=$(docker load -i "$cache_tar")
  loaded_ref=$(printf '%s\n' "$loaded" | sed -n 's/^Loaded image: //p' | tail -n 1)
  if [[ -z "$loaded_ref" ]]; then
    echo "participant cache did not yield a tagged image" >&2
    exit 1
  fi
  docker tag "$loaded_ref" "$participant_tag"
else
  docker pull node:22-bookworm-slim
  participant_base=$(docker image inspect node:22-bookworm-slim --format '{{index .RepoDigests 0}}')
  docker build --build-arg "NODE_BASE=$participant_base" -f examples/knowledge-seed/subject/participant.Dockerfile -t "$participant_tag" examples/knowledge-seed/subject
  if [[ -n "$cache_tar" ]]; then
    mkdir -p "$(dirname "$cache_tar")"
    docker save "$participant_tag" -o "$cache_tar"
  fi
fi
participant_image=$(docker image inspect "$participant_tag" --format '{{.Id}}')
docker image inspect "$participant_image" > "$runtime_root/participant-image.json"
docker run --rm --network=none "$participant_image" sh -ec 'node --version; git --version; mkdir /tmp/project; cd /tmp/project; git init -q; git status --porcelain' > "$runtime_root/participant-runtime-preflight.txt"
printf '%s\n' "$participant_image" > "$runtime_root/image.txt"
