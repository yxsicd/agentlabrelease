"""Empty disposable infrastructure repositories and their test operator identity.

AgentLab business tables and Session data are created by the released SDK tool,
never by this fixture. The configured Person belongs only to this test instance.
"""
import json
import pathlib
import subprocess

def docker(*args, timeout=180):
    return subprocess.check_output(["docker", *args], text=True, timeout=timeout).strip()

def write_agent_config(path: pathlib.Path) -> None:
    path.write_text(
        """
[[repositories]]
id = "session"
path = "/data/repos/session"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"

[[repositories]]
id = "owner-template"
path = "/data/repos/owner-template"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"

[[repositories]]
id = "session-template"
path = "/data/repos/session-template"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"

[[repositories]]
id = "systemconfig"
path = "/data/repos/systemconfig"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"

[[repositories]]
id = "global-control"
path = "/data/repos/global-control"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"

[[repositories]]
id = "safegit"
path = "/data/repos/safegit"
author_name = "AgentLab E2E"
author_email = "agentlab-e2e@example.invalid"
""".lstrip()
    )
    path.chmod(0o444)

def init_volume(image: str, volume: str) -> dict[str, str]:
    script = """
set -eu
init_repo() {
  repo="$1"
  file="$2"
  content="$3"
  message="$4"
  mkdir -p "/data/repos/$repo"
  git init -q -b main "/data/repos/$repo"
  git -C "/data/repos/$repo" config user.name 'AgentLab E2E'
  git -C "/data/repos/$repo" config user.email 'agentlab-e2e@example.invalid'
  printf '%s\\n' "$content" >"/data/repos/$repo/$file"
  git -C "/data/repos/$repo" add "$file"
  GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' GIT_COMMITTER_DATE='2026-01-01T00:00:00Z' \
    git -C "/data/repos/$repo" commit -q -m "$message"
}
init_repo session README.md base 'e2e base'
init_repo owner-template OWNER.md owner-template 'e2e owner template'
init_repo session-template TEMPLATE.md session-template 'e2e session template'
init_repo global-control README.md global-control 'e2e global control'
init_repo safegit README.md safegit 'e2e safegit'
person_digest=bd7662a5eeb41614e720d477abfcb2272e19a8a70a93b7e3bc8560d44ad326e9
mkdir -p /data/repos/systemconfig/data/tables/system_persons/rows/bd
git init -q -b main /data/repos/systemconfig
git -C /data/repos/systemconfig config user.name 'AgentLab E2E'
git -C /data/repos/systemconfig config user.email 'agentlab-e2e@example.invalid'
printf '%s\\n' '{"schema":"mcpgit.table.v1","key_field":"person_id","required_fields":["person_id","handle","display_name","status"],"indexes":[{"name":"handle","field":"handle"},{"name":"status","field":"status"}],"description":"AgentLab E2E organization Persons"}' \
  >/data/repos/systemconfig/data/tables/system_persons/_table.json
printf '%s\\n' '{"schema":"mcpgit.table-row.v1","key":"11111111-1111-4111-8111-111111111111","row_version":1,"deleted":false,"recorded_at_unix_ms":1,"transaction_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","row":{"person_id":"11111111-1111-4111-8111-111111111111","handle":"agentlab-e2e","display_name":"AgentLab E2E","status":"active"}}' \
  >"/data/repos/systemconfig/data/tables/system_persons/rows/bd/${person_digest}.json"
git -C /data/repos/systemconfig add data/tables
GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' GIT_COMMITTER_DATE='2026-01-01T00:00:00Z' \
  git -C /data/repos/systemconfig commit -q -m 'e2e system Person'
printf '{"session":"%s","ownerTemplate":"%s","sessionTemplate":"%s"}\\n' \
  "$(git -C /data/repos/session rev-parse HEAD)" \
  "$(git -C /data/repos/owner-template rev-parse HEAD)" \
  "$(git -C /data/repos/session-template rev-parse HEAD)"
"""
    return json.loads(
        docker(
            "run",
            "--rm",
            "--mount",
            f"type=volume,src={volume},dst=/data",
            "--entrypoint",
            "/bin/sh",
            image,
            "-lc",
            script,
        )
    )
