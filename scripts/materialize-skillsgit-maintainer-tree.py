#!/usr/bin/env python3
"""Materialize evidence-backed target knowledge as a SkillsGit-native tree."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


CORE_SKILLS = (
    "mst-repo-onboarding",
    "mst-repo-transformation",
    "mst-agentsmd-authoring",
    "mst-skill-tree-design",
    "mst-transformation-verification",
    "mst-skill-governor",
    "mst-git-checkpoint-policy",
    "mst-maintainer-handoff",
    "mst-loop-engineering-framework",
    "mst-experience-ingestion",
    "mst-tool-adapter-boundary",
    "mst-runtime-skill-boundary",
    "mst-harmonyos-repo-maintenance",
)


def load(path: Path):
    return json.loads(path.read_text())


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def ownership_labels(scope: dict) -> list[str]:
    selectors = scope.get("ownershipSelectors")
    if not selectors:
        return [scope["pathBoundary"]]
    result = []
    for selector in selectors:
        if selector["type"] == "prefix":
            result.append(selector["path"] + "/**")
        else:
            result.extend(selector["paths"])
    return result


def latest_assessment(knowledge: Path):
    candidates = [load(path) for path in (knowledge / "assessments").glob("*.json")]
    if not candidates:
        raise ValueError("knowledge cut has no assessment")
    return max(candidates, key=lambda row: row["roundIndex"])


def semantic_scope_material(knowledge: Path, repository: str):
    assessment = latest_assessment(knowledge)
    states = {row["skillId"]: row for row in assessment["skills"]}
    facts_by_scope = {}
    for fact in rows(knowledge / "program_facts.jsonl"):
        if fact.get("repositoryId") != repository:
            continue
        if set(fact.get("dimensions", [])) != {
            "responsibility", "boundary", "relations", "behavior",
        }:
            continue
        for scope_id in fact.get("scopeSkillIds", []):
            facts_by_scope.setdefault(scope_id, []).append(fact)
    selected = []
    for scope in rows(knowledge / "maintainer_scope_skills.jsonl"):
        if scope.get("repositoryId") != repository:
            continue
        state = states.get(scope["id"], {})
        if state.get("maturity") not in ("L2-semantic-ready", "L3-maintenance-ready"):
            continue
        facts = sorted(facts_by_scope.get(scope["id"], []), key=lambda row: row["id"])
        if not facts:
            raise ValueError(f"semantic-ready scope lacks a complete fact: {scope['id']}")
        selected.append((scope, state, facts))
    return assessment, selected


def frontmatter_description(scope: dict):
    path = ", ".join(ownership_labels(scope)[:3])
    return (
        f"Use when maintaining {path} in the pinned target repository. "
        "Do not use as proof of build, device, or runtime behavior."
    )


def render_scope_skill(repository: str, scope: dict, state: dict, facts: list[dict]):
    evidence = [
        (item["path"], item["gitBlobOid"])
        for item in scope.get("evidence", [])
        if isinstance(item, dict) and item.get("path") and item.get("gitBlobOid")
    ]
    analysis_evidence = []
    limitations = []
    contracts = []
    for fact in facts:
        contracts.append(fact["interpretation"].strip())
        for item in fact.get("evidence", []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            if item.get("gitBlobOid"):
                evidence.append((item["path"], item["gitBlobOid"]))
            elif item.get("sha256"):
                analysis_evidence.append((item["path"], item["sha256"]))
        limitations.extend(fact.get("limitations", []))
    limitations.extend(
        gap["message"] for gap in state.get("gaps", [])
        if isinstance(gap, dict) and gap.get("message")
    )
    if not limitations:
        limitations.append("No executable build, test, runtime, or maintenance evidence is bound to this generated Skill.")
    evidence = sorted(set(evidence))
    analysis_evidence = sorted(set(analysis_evidence))
    limitations = list(dict.fromkeys(limitations))
    skill_id = (
        f"{slug(scope['id'].removeprefix('skill-scope-'))}-maintenance"
        if scope.get("ownershipSelectors")
        else f"{repository}-{slug(scope['pathBoundary'])}-maintenance"
    )
    labels = ownership_labels(scope)
    lines = [
        "---",
        f"name: {skill_id}",
        f"description: {frontmatter_description(scope)}",
        "---",
        "",
        f"# Maintain `{scope['pathBoundary']}`",
        "",
        "## Purpose",
        "",
        scope["responsibility"],
        "",
        "## Trigger",
        "",
        "Use this skill for changes owned by any selector below or to their declared consumers and dependencies.",
        *(f"- `{label}`" for label in labels),
        "",
        "## Evidence-backed contract",
        "",
        *contracts,
        "",
        "## Workflow",
        "",
        "1. Confirm the checkout matches the source revision below.",
        "2. Re-read the cited blobs and refresh this skill if any blob changed.",
        "3. Trace exported interfaces, local dependencies, state transitions, and consumers before editing.",
        "4. Run the narrowest repository-native build and test entrypoints declared below.",
        "5. Preserve unresolved claims as gaps; do not convert source inference into runtime proof.",
        "",
        "## Source authority",
        "",
        f"- Repository id: `{repository}`",
        f"- Revision: `{scope['sourceRevision']}`",
        f"- Boundary: `{scope['pathBoundary']}`",
        *(["- Ownership selectors:", *(f"  - `{label}`" for label in labels)] if scope.get("ownershipSelectors") else []),
        f"- Maturity: `{state['maturity']}`",
        "",
        "## Build and test entrypoints",
        "",
    ]
    entrypoints = [*(scope.get("buildEntrypoints") or []), *(scope.get("testEntrypoints") or [])]
    lines.extend(f"- `{path}`" for path in entrypoints[:20])
    if not entrypoints:
        lines.append("- No repository-native entrypoint is proven for this scope yet.")
    lines.extend(["", "## Exact evidence", ""])
    lines.extend(f"- `{path}` at `{oid}`" for path, oid in evidence[:20])
    if analysis_evidence:
        lines.extend(["", "## Analysis evidence", ""])
        lines.extend(f"- `{path}` with SHA-256 `{digest}`" for path, digest in analysis_evidence[:12])
    lines.extend(["", "## Residual gaps", ""])
    lines.extend(f"- {item}" for item in limitations[:8])
    lines.extend([
        "",
        "## Verification",
        "",
        "- Verify every cited blob against the pinned revision.",
        "- Run the applicable repository-native build/test lane; record missing SDK, emulator, or hardware as infrastructure evidence.",
        "- Re-run the AgentLab Maintainer Skill hard gate before publishing a refreshed tree.",
        "",
        "## Governance",
        "",
        "This is a generated target-repository Maintainer Skill candidate. Promotion requires repository review; runtime/product skills remain outside `.agents/skills`.",
    ])
    if len(lines) > 120:
        raise ValueError(f"materialized skill exceeds 120 lines: {skill_id}")
    return skill_id, "\n".join(lines) + "\n"


def read_description(skill_file: Path):
    for line in skill_file.read_text().splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"skill lacks description: {skill_file}")


def write_registry(output: Path, standard_revision: str, generated: list[tuple[str, dict]]):
    entries = []
    for skill_id in CORE_SKILLS:
        skill_file = output / ".agents/skills" / skill_id / "SKILL.md"
        entries.append((skill_id, "stable", "maintainer", "repo", read_description(skill_file), [skill_id]))
    for skill_id, scope in generated:
        triggers = [*ownership_labels(scope), skill_id]
        entries.append((
            skill_id, "experimental", "maintainer", scope["pathBoundary"],
            scope["responsibility"], triggers,
        ))
    lines = [
        "schema: mst/v1",
        "name: agentlab-generated-maintainer-skill-tree",
        "authority: AGENTS.md",
        "purpose: Evidence-backed repository maintenance using the SkillsGit standard.",
        f"source_standard_revision: {standard_revision}",
        "selection:",
        "  default_strategy: smallest_relevant_set",
        "  precedence:",
        "    - safety_or_boundary_skill",
        "    - nearest_path_specific_skill",
        "    - stable_skill",
        "    - experimental_skill",
        "  conflict_resolution:",
        "    - Prefer the narrower path scope.",
        "    - Repository evidence never overrides safety or governance skills.",
        "skills:",
    ]
    for skill_id, status, klass, scope, purpose, triggers in entries:
        lines.extend([
            f"  - id: {skill_id}",
            f"    path: .agents/skills/{skill_id}",
            f"    status: {status}",
            f"    class: {klass}",
            f"    scope: {json.dumps(scope)}",
            f"    purpose: {json.dumps(purpose)}",
            "    triggers:",
            *(f"      - {json.dumps(trigger)}" for trigger in triggers),
        ])
    (output / ".agents/skills.registry.yaml").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--skillsgit-root", type=Path, required=True)
    parser.add_argument("--skillsgit-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    actual_revision = subprocess.check_output(
        ["git", "-C", str(args.skillsgit_root), "rev-parse", "HEAD"], text=True,
    ).strip()
    if actual_revision != args.skillsgit_revision:
        raise ValueError("SkillsGit checkout revision differs")
    if args.output.exists():
        raise ValueError("output already exists")
    subprocess.run([
        str(args.skillsgit_root / "scripts/apply-pack.sh"), str(args.output),
        "--profile", "minimal",
    ], cwd=args.skillsgit_root, check=True, stdout=sys.stderr, stderr=sys.stderr)

    for skill_id in CORE_SKILLS:
        source = args.skillsgit_root / ".agents/skills" / skill_id
        target = args.output / ".agents/skills" / skill_id
        if target.exists():
            continue
        shutil.copytree(source, target)
    scripts = args.output / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy2(args.skillsgit_root / "scripts/validate-mst.sh", scripts / "validate-mst.sh")
    (scripts / "validate-mst.sh").chmod(0o755)

    cut = load(args.knowledge / "maintainer-knowledge-cut.json")
    source = next((row for row in cut["repositories"] if row["id"] == args.repository), None)
    if source is None:
        raise ValueError("repository is absent from knowledge cut")
    assessment, material = semantic_scope_material(args.knowledge, args.repository)
    generated = []
    for scope, state, facts in material:
        skill_id, body = render_scope_skill(args.repository, scope, state, facts)
        directory = args.output / ".agents/skills" / skill_id
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(body)
        generated.append((skill_id, scope))
    write_registry(args.output, actual_revision, generated)

    (args.output / "AGENTS.md").write_text(f"""# AGENTS.md

You are operating as a repository maintainer agent for `{args.repository}`.

Canonical sources:

- Current handoff: `.agents/HANDOFF.md`
- Skill registry: `.agents/skills.registry.yaml`
- Maintainer skills: `.agents/skills/**/SKILL.md`

Before changing code, read the handoff, select the smallest relevant skill set,
confirm the source revision, run the required repository-native verification,
and report residual gaps. Tool adapters and runtime/product skills are not
maintenance authority. Generated path skills remain experimental until reviewed.
""")
    (args.output / ".agents/HANDOFF.md").write_text(f"""# Maintainer Handoff

## 0. Status

- Generated from AgentLab knowledge round {assessment['roundIndex']}.
- Source revision: `{source['revision']}`.
- SkillsGit standard revision: `{actual_revision}`.

## 1. North Star

Maintain the pinned repository through evidence-backed, repository-owned Skills.

## 2. Current Focus

Review generated path Skills and close their retained build, runtime, and device gaps.

## 3. Recent Progress

- Materialized {len(generated)} semantic-ready scope Skills.

## 4. Current Action

Run repository-native verification for the next highest-value residual gap.

## 5. Next Actions

1. Review generated Skills against the pinned blobs.
2. Execute missing build/test/emulator evidence.
3. Refresh the AgentLab knowledge cut before accepting source drift.

## 6. Validation Commands

```text
./scripts/validate-mst.sh
```

## 7. Do Not Do

- Do not treat static analysis as runtime proof.
- Do not mix runtime/product Skills into `.agents/skills`.

## 8. Recovery / Resume Commands

```text
git status --short --branch
sed -n '1,220p' .agents/HANDOFF.md
./scripts/validate-mst.sh
```
""")
    (args.output / ".agents/transformation.yaml").write_text(
        "schema: mst-transformation/v1\n"
        "source:\n"
        "  pack: repository-transformation-v0.1\n"
        f"  skillsgit_revision: {actual_revision}\n"
        "  producer: agentlab-maintainer-skill-flywheel\n"
        "target:\n"
        f"  repository: {source['repository']}\n"
        f"  revision: {source['revision']}\n"
        f"  repository_id: {args.repository}\n"
    )
    subprocess.run(
        ["./scripts/validate-mst.sh"], cwd=args.output, check=True,
        stdout=sys.stderr, stderr=sys.stderr,
    )

    files = []
    for path in sorted(item for item in args.output.rglob("*") if item.is_file()):
        files.append({
            "path": str(path.relative_to(args.output)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        })
    receipt = {
        "schema": "agentlab.skillsgit_materialization_receipt.v1",
        "repositoryId": args.repository,
        "sourceRevision": source["revision"],
        "knowledgeRound": assessment["roundIndex"],
        "tableGitAuthority": cut["tableGitAuthority"],
        "skillsgit": {
            "repository": "https://github.com/yxsorg/skillsgit.git",
            "revision": actual_revision,
            "pack": "repository-transformation-v0.1",
        },
        "generatedScopeSkillCount": len(generated),
        "generatedScopeSkillIds": [item[0] for item in generated],
        "validation": {"command": "./scripts/validate-mst.sh", "passed": True},
        "files": files,
        "automaticPromotion": False,
    }
    (args.output / ".agents/materialization-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "repositoryId": args.repository,
        "generatedScopeSkillCount": len(generated),
        "tableGitRevision": cut["tableGitAuthority"]["revision"],
        "skillsgitRevision": actual_revision,
        "validationPassed": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
