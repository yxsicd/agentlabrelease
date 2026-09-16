#!/usr/bin/env python3
"""Persist one live AgentLab experiment milestone through cbgroom MCP only.

The script keeps `experiment_runs` as the current-state index and appends one
immutable `run_events` row in the same revision-fenced TableGit transaction.
It never talks to the cbgroom Git remote directly.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from typing import Optional


def truthy(value: Optional[str]) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def inspector(url: str, tool: str, args: dict) -> dict:
    cmd = [
        "npx", "--yes", "--package", "node@22.20.0",
        "--package", "@modelcontextprotocol/inspector@2.6.0",
        "mcp-inspector", "--cli", url, "--transport", "http",
        "--format", "json", "--method", "tools/call",
        "--tool-name", tool, "--tool-args-json",
        json.dumps(args, separators=(",", ":")),
    ]
    outer = json.loads(subprocess.check_output(cmd, text=True))
    return outer["result"]["structuredContent"]


def query_run(url: str, person: str, run_id: str) -> dict:
    payload = {
        "skill_id": "table.query", "skill_version": "2.2.0",
        "operation": "table_query", "caller_person_id": person,
        "arguments": {
            "repo": "agentlabtablegit", "path": "experiment_runs",
            "keys": [run_id], "limit": 1,
        },
    }
    structured = inspector(url, "skill_run_read", payload)
    if structured.get("outcome") != "executed":
        raise RuntimeError(structured)
    return structured["result"]


def query_table(url: str, person: str, path: str, revision: str, limit: int = 100,
                order_by: Optional[list] = None) -> dict:
    arguments = {
        "repo": "agentlabtablegit", "path": path, "limit": limit,
        "view": {"kind": "committed", "revision": revision},
    }
    if order_by:
        arguments["order_by"] = order_by
    payload = {
        "skill_id": "table.query", "skill_version": "2.2.0",
        "operation": "table_query", "caller_person_id": person,
        "arguments": arguments,
    }
    structured = inspector(url, "skill_run_read", payload)
    if structured.get("outcome") != "executed":
        raise RuntimeError(structured)
    result = structured["result"]
    if result["revision"] != revision:
        raise RuntimeError(f"projection revision drift for {path}")
    return result


def refresh_live_projection(url: str, person: str, source_revision: str) -> str:
    runs = query_table(url, person, "experiment_runs", source_revision, 30,
                       [{"field": "latestHeartbeat", "direction": "desc"}])
    events = query_table(url, person, "run_events", source_revision, 120,
                         [{"field": "timestamp", "direction": "desc"}])
    crossings = query_table(url, person, "crossings", source_revision, 500)
    decisions = query_table(url, person, "decisions", source_revision, 200)
    interventions = query_table(url, person, "interventions", source_revision, 200)
    difficulties = query_table(url, person, "difficulty_points", source_revision, 200)
    claims = query_table(url, person, "research_claims", source_revision, 100)
    claim_events = query_table(url, person, "claim_events", source_revision, 200)
    claim_independence = query_table(url, person, "claim_evidence_independence", source_revision, 1000)

    crossing_rows = [r.get("row", r) for r in crossings.get("rows", [])]
    intervention_rows = [r.get("row", r) for r in interventions.get("rows", [])]
    difficulty_rows = [r.get("row", r) for r in difficulties.get("rows", [])]

    def family_stats(arm: str) -> dict:
        rows = [r for r in crossing_rows if r.get("arm") == arm]
        return {
            "trials": len(rows),
            "behaviorPass": sum(r.get("behaviorPass") is True for r in rows),
            "buildPass": sum(r.get("buildPass") is True for r in rows),
            "scopeClean": sum(r.get("scopeDrift") is False for r in rows),
            "fullPass": sum(
                r.get("behaviorPass") is True
                and r.get("buildPass") is True
                and r.get("scopeDrift") is False
                for r in rows
            ),
        }

    def intervention_stats(variable: str) -> dict:
        intervention_ids = {
            r.get("id") for r in intervention_rows if r.get("variable") == variable
        }
        rows = [
            r for r in crossing_rows
            if r.get("arm") == "timeout-feedback"
            and r.get("interventionId") in intervention_ids
        ]
        return {
            "trials": len(rows),
            "behaviorPass": sum(r.get("behaviorPass") is True for r in rows),
            "buildPass": sum(r.get("buildPass") is True for r in rows),
            "scopeClean": sum(r.get("scopeDrift") is False for r in rows),
            "fullPass": sum(
                r.get("behaviorPass") is True
                and r.get("buildPass") is True
                and r.get("scopeDrift") is False
                for r in rows
            ),
        }

    maturity_lag = []
    legacy_timeout_without_cadence_metadata = [
        r.get("id") for r in intervention_rows
        if r.get("variable") == "timeoutFeedbackOnly"
        and "verificationCadenceGuidance" not in (r.get("variantValue") or {})
    ]
    timeout_trials = family_stats("timeout-feedback")["trials"]
    for row in difficulty_rows:
        if (
            row.get("mechanism") == "timeout-before-source-mutation"
            and row.get("maturityState") in {"candidate", "reproduced"}
            and timeout_trials >= 3
        ):
            maturity_lag.append({
                "difficultyId": row.get("id"),
                "rawMaturity": row.get("maturityState"),
                "observedTimeoutTrials": timeout_trials,
            })

    projection = {
        "schema": "agentlab.live_research_projection.v1",
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {"repo": "agentlabtablegit", "revision": source_revision},
        "counts": {
            "runs": runs.get("row_count", 0),
            "events": events.get("row_count", 0),
            "crossings": crossings.get("row_count", 0),
            "decisions": decisions.get("row_count", 0),
            "interventions": interventions.get("row_count", 0),
            "difficulties": difficulties.get("row_count", 0),
            "claims": claims.get("row_count", 0),
            "claimEvents": claim_events.get("row_count", 0),
            "claimEvidenceIndependence": claim_independence.get("row_count", 0),
        },
        "runs": runs.get("rows", []),
        "recentEvents": events.get("rows", []),
        "crossingSummary": {
            "behaviorPass": sum(r.get("behaviorPass") is True for r in crossing_rows),
            "buildPass": sum(r.get("buildPass") is True for r in crossing_rows),
            "scopeClean": sum(r.get("scopeDrift") is False for r in crossing_rows),
        },
        "families": {
            "compilerFeedback": family_stats("compiler-feedback"),
            "timeoutFeedback": family_stats("timeout-feedback"),
            "timeoutOnly": intervention_stats("timeoutFeedbackOnly"),
            "timeoutWithVerificationCadence": intervention_stats("timeoutFeedbackWithVerificationCadence"),
        },
        "difficultyPoints": difficulty_rows,
        "interventions": intervention_rows[-30:],
        "dataQuality": {
            "maturityLag": maturity_lag,
            "legacyTimeoutCadenceMetadataMissing": {
                "count": len(legacy_timeout_without_cadence_metadata),
                "interventionIds": legacy_timeout_without_cadence_metadata,
            },
        },
        "recentDecisions": decisions.get("rows", [])[-20:],
        "claims": claims.get("rows", []),
        "claimEvents": claim_events.get("rows", [])[-50:],
        "claimEvidenceIndependence": claim_independence.get("rows", []),
    }
    content = json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
    for attempt in range(5):
        status_payload = {
            "skill_id": "repo.read", "skill_version": "2.2.0",
            "operation": "repo_status", "caller_person_id": person,
            "arguments": {"repo": "works"},
        }
        status = inspector(url, "skill_run_read", status_payload)
        if status.get("outcome") != "executed":
            raise RuntimeError(status)
        works_revision = status["result"]["head"]
        write_payload = {
            "skill_id": "repo.author", "skill_version": "2.2.0",
            "operation": "write_file", "caller_person_id": person,
            "arguments": {
                "repo": "works", "path": "live/agentlab.json", "content": content,
                "expected_revision": works_revision,
                "message": f"works: refresh AgentLab live projection at {source_revision[:12]}",
            },
        }
        written = inspector(url, "skill_run_write", write_payload)
        if written.get("outcome") == "executed":
            return written["result"]["revision"]
        if attempt == 4:
            raise RuntimeError(written)
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def uid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--status", default="running")
    p.add_argument("--phase", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--source-revision", default="")
    p.add_argument("--checkpoint-id", default="")
    p.add_argument("--intervention-id", default="")
    p.add_argument("--first-mutation-ms", type=int)
    p.add_argument("--behavior-status", default="")
    p.add_argument("--build-status", default="")
    p.add_argument("--persistence-status", default="")
    p.add_argument("--completed", action="store_true")
    p.add_argument("--report-eligible", default="true")
    p.add_argument("--payload-json", default="{}")
    args = p.parse_args()

    url = os.environ["AGENTLAB_TABLEGIT_MCP_URL"]
    person = os.environ["AGENTLAB_TABLEGIT_PERSON_ID"]
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ["AGENTLAB_CAPTURE_RUN_ID"]
    scenario = os.environ.get("AGENTLAB_ASSESSMENT_SCENARIO", "unknown")
    model = os.environ.get("AGENTLAB_MODEL", "unknown")
    reasoning = os.environ.get("AGENTLAB_REASONING_EFFORT", "default")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    extra = json.loads(args.payload_json)

    for attempt in range(5):
        current = query_run(url, person, run_id)
        revision = current["revision"]
        found = current.get("returned_count", 0) == 1
        old = current["rows"][0] if found else None
        sequence = (old["row"].get("latestEventSequence") or 0) + 1 if old else 1
        event_id = f"{run_id}-{sequence:06d}"

        state_set = {
            "status": args.status,
            "currentStage": args.stage,
            "latestEventSequence": sequence,
            "latestHeartbeat": now,
            "reportEligible": truthy(args.report_eligible),
        }
        optional = {
            "sourceRevision": args.source_revision,
            "checkpointId": args.checkpoint_id,
            "interventionId": args.intervention_id,
            "behaviorStatus": args.behavior_status,
            "buildStatus": args.build_status,
            "persistenceStatus": args.persistence_status,
        }
        state_set.update({k: v for k, v in optional.items() if v})
        if args.first_mutation_ms is not None:
            state_set["firstMutationMs"] = args.first_mutation_ms
        if args.completed:
            state_set["completedAt"] = now

        if found:
            run_op = {
                "op": "update", "operation_id": uid(f"{run_id}:{sequence}:run-update"),
                "key": run_id, "expected_row_version": old["row_version"],
                "set": state_set,
            }
        else:
            run_row = {
                "id": run_id, "status": args.status, "startedAt": now,
                "scenario": scenario, "model": model, "reasoningEffort": reasoning,
                "currentStage": args.stage, "latestEventSequence": sequence,
                "latestHeartbeat": now, "workflowRunId": run_id,
                "reportEligible": truthy(args.report_eligible),
                "metadata": {
                    "repository": os.environ.get("GITHUB_REPOSITORY"),
                    "workflow": os.environ.get("GITHUB_WORKFLOW"),
                    "sha": os.environ.get("GITHUB_SHA"),
                },
            }
            run_row.update({k: v for k, v in state_set.items() if k not in run_row})
            run_op = {
                "op": "insert", "operation_id": uid(f"{run_id}:{sequence}:run-insert"),
                "key": run_id, "row": run_row,
            }

        event = {
            "id": event_id, "runId": run_id, "sequence": sequence,
            "timestamp": now, "kind": args.kind,
            "phase": args.phase or args.stage,
            "summary": args.summary,
            "payload": extra,
        }
        if args.source_revision:
            event["sourceCut"] = args.source_revision

        tx_seed = f"{run_id}:{sequence}:{args.kind}"
        write_args = {
            "repo": "agentlabtablegit", "topic_id": "main",
            "expected_revision": revision,
            "transaction_id": uid(tx_seed + ":tx"),
            "idempotency_key": tx_seed,
            "actor": "agentlab-release-live-events",
            "message": f"agentlab live event {run_id} #{sequence} {args.kind}",
            "tables": [
                {"path": "experiment_runs", "operations": [run_op]},
                {"path": "run_events", "operations": [{
                    "op": "insert", "operation_id": uid(tx_seed + ":event"),
                    "key": event_id, "row": event,
                }]},
            ],
        }
        payload = {
            "skill_id": "table.author", "skill_version": "2.2.0",
            "operation": "worktree_table_batch_transaction",
            "caller_person_id": person, "arguments": write_args,
        }
        structured = inspector(url, "skill_run_write", payload)
        if structured.get("outcome") == "executed":
            works_revision = refresh_live_projection(
                url, person, structured["result"]["revision"]
            )
            print(json.dumps({
                "runId": run_id, "sequence": sequence, "kind": args.kind,
                "revision": structured["result"]["revision"],
                "worksRevision": works_revision,
            }, sort_keys=True))
            return
        if attempt == 4:
            raise RuntimeError(structured)
        time.sleep(0.5 * (attempt + 1))


if __name__ == "__main__":
    main()
