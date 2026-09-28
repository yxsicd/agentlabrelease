#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 REPOSITORY REVISION SCOPE_PATH DESTINATION" >&2
  exit 2
fi

repository=$1
revision=$2
scope_path=${3%/}
destination=$4

if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
  echo "revision must be an exact 40-hex commit" >&2
  exit 2
fi
if [[ -z $scope_path || $scope_path == . || $scope_path == /* || $scope_path == *\\* ||
      /$scope_path/ == */../* || /$scope_path/ == */./* || $scope_path == *//* ]]; then
  echo "scope path must be a safe repository-relative directory" >&2
  exit 2
fi

mkdir -p "$destination"
if [[ ! -d "$destination/.git" ]]; then
  git -C "$destination" init
  git -C "$destination" remote add origin "$repository"
fi
if [[ $(git -C "$destination" remote get-url origin) != "$repository" ]]; then
  echo "existing checkout remote differs" >&2
  exit 1
fi

# Keep the exact commit and all of its trees available, but materialize only the
# selected Maintainer Skill boundary. This prevents one small scope in a large
# corpus from causing a whole-repository lazy Blob download during checkout.
git -C "$destination" sparse-checkout init --cone
git -C "$destination" sparse-checkout set "$scope_path"

attempts=3
for ((attempt = 1; attempt <= attempts; attempt++)); do
  if git -C "$destination" \
      -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=60 \
      fetch --no-tags --depth=1 --filter=blob:none origin "$revision" &&
     git -C "$destination" checkout --force --detach FETCH_HEAD &&
     [[ $(git -C "$destination" rev-parse HEAD) == "$revision" ]] &&
     [[ -d "$destination/$scope_path" ]]; then
    exit 0
  fi
  if ((attempt < attempts)); then
    echo "scope checkout attempt $attempt failed; retrying" >&2
    sleep $((attempt * 5))
  fi
done

echo "failed to materialize exact scope after $attempts attempts" >&2
exit 1
