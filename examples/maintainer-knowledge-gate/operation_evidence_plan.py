#!/usr/bin/env python3
"""Plan revision-bound operation evidence without promoting Maintainer Skills."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA = "agentlab.maintainer_skill_operation_evidence_plan.v1"
LANE_ORDER = {
    "build-test": 0,
    "build-only": 1,
    "test-only": 2,
    "support-config": 3,
    "source-only": 4,
}


def load(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def lane_for(capabilities):
    capabilities = set(capabilities or [])
    build = "build-maintenance" in capabilities
    test = "test-maintenance" in capabilities
    source = "source-maintenance" in capabilities
    if build and test:
        return "build-test"
    if build:
        return "build-only"
    if test:
        return "test-only"
    if source:
        return "source-only"
    return "support-config"


def lane_contract(lane):
    contracts = {
        "build-test": {
            "shareableEvidence": [
                "exact-revision-source-identity",
                "qualified-toolchain",
                "repository-or-module-build-closure",
            ],
            "scopeRequiredEvidence": [
                "scope-covered-by-successful-build-receipt",
                "scope-test-entrypoint-executed",
                "scope-test-verdict-pass",
            ],
            "preferredOperationFactKind": "runtime-verification",
        },
        "build-only": {
            "shareableEvidence": [
                "exact-revision-source-identity",
                "qualified-toolchain",
                "repository-or-module-build-closure",
            ],
            "scopeRequiredEvidence": [
                "scope-covered-by-successful-build-receipt",
                "build-artifact-or-build-task-verdict-pass",
            ],
            "preferredOperationFactKind": "build-verification",
        },
        "test-only": {
            "shareableEvidence": [
                "exact-revision-source-identity",
                "qualified-test-runtime",
            ],
            "scopeRequiredEvidence": [
                "scope-test-entrypoint-executed",
                "scope-test-verdict-pass",
            ],
            "preferredOperationFactKind": "runtime-verification",
        },
        "support-config": {
            "shareableEvidence": [
                "exact-revision-source-identity",
                "qualified-toolchain-when-required",
            ],
            "scopeRequiredEvidence": [
                "configuration-or-support-operation-executed",
                "scope-specific-verdict-pass",
            ],
            "preferredOperationFactKind": "configuration-verification",
        },
        "source-only": {
            "shareableEvidence": [
                "exact-revision-source-identity",
                "qualified-execution-or-analysis-runtime",
            ],
            "scopeRequiredEvidence": [
                "bounded-maintenance-operation-executed",
                "scope-specific-observable-or-preservation-check-pass",
                "meaningful-negative-control-or-equivalent-failure-attribution",
            ],
            "preferredOperationFactKind": "maintenance-verification",
        },
    }
    return contracts[lane]


def has_operation_gap(row):
    return any(
        gap.get("code") == "MS-OPERATION-EVIDENCE-MISSING"
        for gap in row.get("gaps", [])
        if isinstance(gap, dict)
    )


def build_plan(assessment, repository_id):
    require(
        assessment.get("schema") == "agentlab.maintainer_skill_assessment.v1",
        "unsupported assessment schema",
    )
    skills = [
        row for row in assessment.get("skills", [])
        if row.get("repositoryId") == repository_id
    ]
    require(skills, f"repository is absent from assessment: {repository_id}")

    revisions = {row.get("sourceRevision") for row in skills}
    require(None not in revisions and len(revisions) == 1, "repository source revision is ambiguous")
    source_revision = next(iter(revisions))

    pending = [
        row for row in skills
        if row.get("checks", {}).get("semanticReady") is True
        and row.get("checks", {}).get("maintenanceReady") is not True
        and has_operation_gap(row)
    ]
    rows = []
    for row in pending:
        lane = lane_for(row.get("capabilities", []))
        contract = lane_contract(lane)
        rows.append({
            "skillId": row["skillId"],
            "sourceRevision": row["sourceRevision"],
            "lane": lane,
            "priority": LANE_ORDER[lane],
            "capabilities": row.get("capabilities", []),
            "shareableEvidence": contract["shareableEvidence"],
            "scopeRequiredEvidence": contract["scopeRequiredEvidence"],
            "preferredOperationFactKind": contract["preferredOperationFactKind"],
            "operationFactRequirements": {
                "dimensions": ["operation"],
                "scopeSkillIds": [row["skillId"]],
                "sourceRevision": row["sourceRevision"],
                "exactScopeBindingRequired": True,
                "passReceiptRequired": True,
            },
            "automaticPromotion": False,
        })
    rows.sort(key=lambda row: (row["priority"], row["skillId"]))

    lane_counts = {}
    for row in rows:
        lane_counts[row["lane"]] = lane_counts.get(row["lane"], 0) + 1

    return {
        "schema": SCHEMA,
        "repositoryId": repository_id,
        "sourceRevision": source_revision,
        "assessmentId": assessment.get("assessmentId"),
        "summary": {
            "scopeCount": len(skills),
            "operationEvidencePendingCount": len(rows),
            "laneCounts": lane_counts,
        },
        "sharedEvidencePolicy": {
            "reuseAllowedOnlyWhen": [
                "same repositoryId",
                "same exact sourceRevision",
                "receipt coverage explicitly includes the target scope or its owning module",
                "receipt verdict is pass/qualified rather than blocked, partial, planned, or inferred",
            ],
            "neverSufficientAlone": [
                "operation plan",
                "toolchain presence",
                "descriptive build-test entrypoint",
                "failed or blocked preflight",
                "unscoped repository claim",
            ],
            "scopeSpecificOperationFactRequired": True,
        },
        "lanes": rows,
        "decision": "collect-operation-evidence" if rows else "operation-evidence-complete",
        "automaticPromotion": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan(load(args.assessment), args.repository)
    write(args.output, plan)
    print(json.dumps(plan["summary"], separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
