#!/usr/bin/env bash
# Read-only JSONL inventory. Candidate metadata is not deletion authority.
set -euo pipefail
if [[ $# -gt 0 ]]; then
  if [[ $# == 1 && "$1" == --help ]]; then
    printf '%s\n' 'Usage: bash agentlab-resource-inventory.sh' \
      'Read-only Docker identities and mounts; no environment/configuration secrets.' \
      'Output is private inventory, not an ownership or deletion verdict.'
    exit 0
  fi
  printf '%s\n' 'unsupported arguments' >&2
  exit 2
fi
command -v docker >/dev/null || { printf '%s\n' 'Docker CLI unavailable' >&2; exit 2; }
docker version >/dev/null
printf '%s\n' '{"schema":"agentlab.resource_inventory.v1","coverage":"current-docker-context-only","readOnly":true,"deletionAuthorized":false}'
ids=$(docker ps -aq --no-trunc)
while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  [[ "$id" =~ ^[a-f0-9]{64}$ ]] || { printf '%s\n' 'invalid Docker identity' >&2; exit 1; }
  docker container inspect --format '{"kind":"container","id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},"state":{{json .State.Status}},"restart":{{json .HostConfig.RestartPolicy.Name}},"composeProject":{{json (index .Config.Labels "com.docker.compose.project")}},"composeService":{{json (index .Config.Labels "com.docker.compose.service")}},"mounts":{{json .Mounts}}}' "$id"
done <<< "$ids"
docker volume ls --format '{"kind":"volume-candidate","name":{{json .Name}},"driver":{{json .Driver}},"ownershipVerified":false}'
