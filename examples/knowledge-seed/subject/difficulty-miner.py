#!/usr/bin/env python3
"""Mine repeatable Agent difficulty candidates from retained Harness evidence.

The miner is deliberately post-hoc and read-only.  It never changes the assessed
workspace, never promotes guidance, and excludes infrastructure/transport failures
from task difficulty.  One observation is only a candidate; repeated independent
run/phase observations are required before `reproducible=true`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


PHASES = ("turn-1", "parent-turn-2", "fresh-fork-turn-2")
INFRA_TOKENS = ("frp", "http 404", "404 <!doctype", "502", "gateway", "readiness", "preflight")
ARKTS_CODE = re.compile(r"\barkts-[a-z0-9-]+\b", re.I)
TS_CODE = re.compile(r"\b(?:TS|ETS)\d{3,6}\b")
GENERIC_CODE = re.compile(r"\b(?:error|warning)\s*\[([^\]]{2,80})\]", re.I)


def load(path: Path):
    return json.loads(path.read_text())


def stable_id(category: str, signature: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{category}-{signature}".lower()).strip("-")[:72]
    digest = hashlib.sha256(f"{category}\0{signature}".encode()).hexdigest()[:10]
    return f"{slug}-{digest}" if slug else f"difficulty-{digest}"


def compiler_signatures(text: str) -> list[str]:
    values = []
    for regex in (ARKTS_CODE, TS_CODE, GENERIC_CODE):
        for match in regex.finditer(text):
            value = match.group(1) if regex is GENERIC_CODE else match.group(0)
            value = re.sub(r"\s+", " ", value.strip()).lower()
            if value and value not in values:
                values.append(value)
    if values:
        return values[:16]
    # Preserve a bounded normalized compiler line when the tool has no stable code.
    for line in text.splitlines():
        if "error" in line.lower():
            line = re.sub(r"(?:[A-Za-z]:)?[/\\][^\s:]+", "<path>", line)
            line = re.sub(r"\b\d+:\d+\b", "<loc>", line)
            line = re.sub(r"\s+", " ", line.strip()).lower()
            if line:
                return [line[:240]]
    return []


def find_phase_file(root: Path, phase: str, suffixes: tuple[str, ...]) -> Path | None:
    variants = [phase, phase.replace("-", "_"), phase.replace("-turn-", "-turn")]
    for base in variants:
        for suffix in suffixes:
            path = root / f"{base}{suffix}"
            if path.is_file():
                return path
    # Existing captures may nest logs below build/phase directories.
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if phase.lower() in name and any(name.endswith(s.lower()) for s in suffixes):
            return path
    return None


def infra_phases(decision: dict) -> set[str]:
    result = set()
    if decision.get("infrastructureAvailable") is False:
        result.update(PHASES)
    for row in decision.get("launchErrors", []):
        error = str(row.get("error", "")).lower()
        if any(token in error for token in INFRA_TOKENS):
            result.add(row.get("phase", ""))
    return result


def observations(run_id: str, decision_path: Path, evidence_root: Path | None) -> list[dict]:
    decision = load(decision_path)
    blocked = infra_phases(decision)
    process = {row.get("phase"): row for row in decision.get("participantProcess", [])}
    rows = []
    for verdict in decision.get("phaseVerdicts", []):
        phase = verdict.get("phase")
        if not phase or phase in blocked:
            continue
        behavior, build = verdict.get("behaviorPass"), verdict.get("buildPass")
        proc = process.get(phase, {})
        checkpoint = None
        if evidence_root:
            candidate = evidence_root / "difficulty-checkpoints" / phase / "checkpoint.json"
            if candidate.is_file():
                data = load(candidate)
                checkpoint = dict(path=str(candidate.relative_to(evidence_root)), schema=data.get("schema"),
                                  formalSessionFsSnapshot=data.get("formalSessionFsSnapshot"),
                                  readyForControlledFork=data.get("readyForControlledFork"),
                                  nativeSession=data.get("nativeSession"))
        common = dict(runId=run_id, phase=phase, behaviorPass=behavior, buildPass=build,
                      timedOut=proc.get("timedOut"), firstSourceMutationMs=proc.get("firstSourceMutationMs"),
                      providerReasoningEffort=proc.get("providerReasoningEffort"), completedToolCalls=proc.get("completedToolCalls"),
                      checkpointCandidate=checkpoint)
        if proc.get("timedOut") and proc.get("firstSourceMutationMs") is None:
            rows.append(dict(**common, category="localization-planning", signature="timeout-before-source-mutation",
                             evidence=["participantProcess:firstSourceMutationMs=null", "participantProcess:timedOut=true"]))
        if behavior is False and build is True:
            rows.append(dict(**common, category="semantic", signature="behavior-fail-build-pass",
                             evidence=["phaseVerdict:behaviorPass=false", "phaseVerdict:buildPass=true"]))
        if behavior is True and build is False:
            signatures = []
            evidence = ["phaseVerdict:behaviorPass=true", "phaseVerdict:buildPass=false"]
            if evidence_root:
                path = find_phase_file(evidence_root, phase, ("-build-stderr.log", "build-stderr.log", ".stderr.log"))
                if path:
                    signatures = compiler_signatures(path.read_text(errors="replace"))
                    evidence.append(str(path.relative_to(evidence_root)))
            if signatures:
                for signature in signatures:
                    rows.append(dict(**common, category="language-build", signature=signature, evidence=evidence))
            else:
                rows.append(dict(**common, category="language-build", signature="behavior-pass-build-fail", evidence=evidence))
    return rows


def context_sensitivity(obs: list[dict]) -> dict:
    phases = {row["phase"] for row in obs}
    parent = "parent-turn-2" in phases
    fresh = "fresh-fork-turn-2" in phases
    if parent and fresh:
        label = "context-independent-observed"
    elif parent:
        label = "parent-only-observed"
    elif fresh:
        label = "fresh-only-observed"
    else:
        label = "undetermined"
    return {"classification": label, "parentObserved": parent, "freshForkObserved": fresh}


def aggregate(all_obs: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in all_obs:
        groups[(row["category"], row["signature"])].append(row)
    result = []
    for (category, signature), obs in groups.items():
        run_ids = sorted({row["runId"] for row in obs})
        phase_keys = sorted({f"{row['runId']}:{row['phase']}" for row in obs})
        independent = len(phase_keys)
        reproducible = len(run_ids) >= 2 or independent >= 2
        severity = "high" if any(row.get("behaviorPass") is True and row.get("buildPass") is False for row in obs) else "medium"
        result.append(dict(
            difficultyId=stable_id(category, signature), category=category, signature=signature,
            status=("reproducible" if reproducible else "candidate"), reproducible=reproducible,
            occurrenceCount=len(obs), independentPhaseCount=independent, runCount=len(run_ids), runIds=run_ids,
            phases=sorted({row["phase"] for row in obs}), severity=severity,
            contextSensitivity=context_sensitivity(obs), observations=obs,
            checkpointPolicy={
                "eligible": reproducible,
                "requireExactObservableState": True,
                "preferredContextMode": "sessionfs-native-session-checkpoint" if reproducible else "collect-more-evidence",
                "capturedCandidateCount":sum(bool(row.get("checkpointCandidate")) for row in obs),
                "formalSnapshotCount":sum(bool((row.get("checkpointCandidate") or {}).get("formalSessionFsSnapshot")) for row in obs),
                "neverPersist": ["provider-hidden-state", "process-memory", "pid", "tcp-connection"],
            },
            allowedNextVariables=["model", "reasoning-effort", "guidance", "tool-policy", "context-mode"],
            agentDecisionRequired=True,
        ))
    return sorted(result, key=lambda x: (-x["runCount"], -x["independentPhaseCount"], x["difficultyId"]))


def parse_named(values: list[str], flag: str) -> dict[str, Path]:
    out = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"{flag} requires RUN_ID=PATH")
        run_id, raw = value.split("=", 1)
        if not run_id or run_id in out:
            raise SystemExit(f"invalid/duplicate run id for {flag}: {run_id!r}")
        out[run_id] = Path(raw)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--decision", action="append", default=[], metavar="RUN_ID=PATH", required=True)
    p.add_argument("--evidence", action="append", default=[], metavar="RUN_ID=DIR")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    decisions, evidence = parse_named(a.decision, "--decision"), parse_named(a.evidence, "--evidence")
    unknown = set(evidence) - set(decisions)
    if unknown:
        raise SystemExit(f"evidence without decision: {sorted(unknown)}")
    obs = []
    for run_id, path in decisions.items():
        obs.extend(observations(run_id, path, evidence.get(run_id)))
    candidates = aggregate(obs)
    payload = dict(
        schema="agentlab.difficulty_candidates.v1", runIds=sorted(decisions), candidateCount=len(candidates),
        reproducibleCount=sum(row["reproducible"] for row in candidates), candidates=candidates,
        methodology={
            "definition":"A difficulty is a repeatable, evidence-linked failure invariant under a fixed task/source/oracle; a single failure remains only a candidate.",
            "infrastructureExcluded":True,
            "harnessAuthority":"observe-cluster-score-only",
            "agentAuthority":"confirm-difficulty-and-select-next-controlled-experiment",
        },
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
