#!/usr/bin/env python3
"""Qualify exact expression facts without claiming resolved dataflow."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "agentlab.multi_repo_expression_fact_qualification.v1"
PACKET_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v5"
ANALYSIS_SCHEMA = "agentlab.ast_analysis.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
EXPRESSION_FIELDS = {
    "symbol": ("parameterExpressions",),
    "property": ("parameterExpressions", "initializerExpression"),
    "binding": ("initializerExpression",),
    "assignment": ("leftExpression", "rightExpression"),
    "call": ("targetExpression", "argumentExpressions"),
    "object-entry": ("keyExpression", "valueExpression"),
    "return": ("expression",),
}


class ExpressionQualificationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ExpressionQualificationError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExpressionQualificationError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def parse_mapping(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        require(separator == "=" and repository_id and raw_path, f"{label} mapping is invalid")
        require(repository_id not in result, f"duplicate {label} repository id")
        result[repository_id] = Path(raw_path)
    return result


def packet_sources(packet: dict[str, Any]) -> tuple[dict[str, str], dict[str, set[str]]]:
    require(packet.get("schema") == PACKET_SCHEMA, "unsupported candidate review packet")
    revisions: dict[str, str] = {}
    paths: dict[str, set[str]] = {}
    for fact in packet.get("domainFactEvidence") or []:
        require(isinstance(fact, dict), "packet domain fact is invalid")
        repository_id = fact.get("repositoryId")
        source_identity = fact.get("sourceIdentity")
        path = fact.get("path")
        require(isinstance(repository_id, str) and repository_id, "packet repository id is invalid")
        require(isinstance(source_identity, str) and "@" in source_identity, "packet source identity is invalid")
        revision = source_identity.rsplit("@", 1)[-1]
        require(REVISION.fullmatch(revision), "packet source revision is invalid")
        require(revisions.setdefault(repository_id, revision) == revision, "packet revisions differ")
        require(isinstance(path, str) and path, "packet fact path is invalid")
        paths.setdefault(repository_id, set()).add(path)
    require(len(revisions) >= 2, "packet does not span repositories")
    return revisions, paths


def identifier_variants(contract: dict[str, Any]) -> set[str]:
    tokens = contract.get("tokens")
    require(isinstance(tokens, list) and len(tokens) >= 2, "domain identifier tokens are invalid")
    require(all(isinstance(token, str) and token for token in tokens), "domain identifier token is invalid")
    camel = tokens[0].lower() + "".join(token[:1].upper() + token[1:].lower() for token in tokens[1:])
    values = {
        "".join(token.lower() for token in tokens),
        camel.lower(),
        "_".join(token.lower() for token in tokens).replace("_", ""),
        "-".join(token.lower() for token in tokens).replace("-", ""),
    }
    normalized = contract.get("normalizedIdentifier")
    require(isinstance(normalized, str) and normalized, "normalized domain identifier is invalid")
    values.add(re.sub(r"[^a-z0-9]", "", normalized.lower()))
    return {value for value in values if value}


def normalized_text(value: Any) -> str:
    if isinstance(value, list):
        value = "\n".join(item for item in value if isinstance(item, str))
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def compact_value(value: Any) -> Any:
    if isinstance(value, list):
        return [compact_value(item) for item in value]
    if not isinstance(value, str) or len(value) <= 400:
        return value
    return {
        "sha256": digest_bytes(value.encode("utf-8")),
        "length": len(value),
        "preview": value[:200],
    }


def read_facts(path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    require(path.is_file() and not path.is_symlink(), "program facts must be a regular file")
    raw = path.read_bytes()
    require(digest_bytes(raw) == expected_sha256, "program facts digest differs")
    rows = []
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExpressionQualificationError(f"invalid program fact at line {number}: {error}") from error
        require(isinstance(value, dict), f"program fact at line {number} is not an object")
        rows.append(value)
    return rows


def qualify(packet_path: Path, analyses: dict[str, Path], facts: dict[str, Path]) -> dict[str, Any]:
    packet = load(packet_path, "candidate review packet")
    revisions, selected_paths = packet_sources(packet)
    require(set(analyses) == set(facts) == set(revisions), "analysis repositories differ from packet")
    variants = identifier_variants(packet.get("domainIdentifierContract") or {})
    analyzer_digests: set[str] = set()
    grammar_digests: set[str] = set()
    repository_receipts = []
    total_selected = 0
    for repository_id in sorted(revisions):
        analysis = load(analyses[repository_id], f"{repository_id} analysis")
        require(analysis.get("schema") == ANALYSIS_SCHEMA, "unsupported AST analysis")
        require(analysis.get("sourceRevision") == revisions[repository_id], "analysis revision differs")
        analyzer_digest = analysis.get("analyzerDigest")
        grammar_digest = analysis.get("grammarDigest")
        facts_sha256 = analysis.get("sha256")
        require(isinstance(analyzer_digest, str) and SHA256.fullmatch(analyzer_digest), "analyzer digest is invalid")
        require(isinstance(grammar_digest, str) and SHA256.fullmatch(grammar_digest), "grammar digest is invalid")
        require(isinstance(facts_sha256, str) and SHA256.fullmatch(facts_sha256), "facts digest is invalid")
        analyzer_digests.add(analyzer_digest)
        grammar_digests.add(grammar_digest)
        rows = read_facts(facts[repository_id], facts_sha256)
        require(analysis.get("rows") == len(rows), "analysis row count differs")
        selected = []
        for row in rows:
            kind = row.get("kind")
            fields = EXPRESSION_FIELDS.get(kind)
            if not fields or row.get("path") not in selected_paths[repository_id]:
                continue
            for field in fields:
                require(field in row, f"{kind} fact lacks {field}")
            matched = [field for field in fields if any(value in normalized_text(row[field]) for value in variants)]
            if not matched:
                continue
            selected.append({
                "factId": row.get("id"),
                "kind": kind,
                "path": row.get("path"),
                "owner": row.get("owner"),
                "span": row.get("span"),
                "matchedFields": matched,
                "expressions": {field: compact_value(row[field]) for field in fields},
            })
        require(selected, f"{repository_id} has no selected expression facts")
        selected.sort(key=lambda row: (row["path"], (row.get("span") or {}).get("startByte", -1), row["factId"]))
        total_selected += len(selected)
        repository_receipts.append({
            "repositoryId": repository_id,
            "sourceRevision": revisions[repository_id],
            "analysisSha256": digest(analyses[repository_id]),
            "programFactsSha256": facts_sha256,
            "rowCount": len(rows),
            "selectedExpressionFactCount": len(selected),
            "selectedExpressionFacts": selected,
        })
    require(len(analyzer_digests) == 1, "repositories used different analyzers")
    require(len(grammar_digests) == 1, "repositories used different grammars")
    return {
        "schema": SCHEMA,
        "status": "expression-facts-qualified-dataflow-unresolved",
        "candidateId": packet.get("candidateId"),
        "sourceSetSha256": packet.get("sourceSetSha256"),
        "reviewPacketSha256": digest(packet_path),
        "domainIdentifierContract": packet.get("domainIdentifierContract"),
        "analyzerDigest": next(iter(analyzer_digests)),
        "grammarDigest": next(iter(grammar_digests)),
        "repositoryCount": len(repository_receipts),
        "selectedExpressionFactCount": total_selected,
        "repositories": repository_receipts,
        "interpretation": "Exact expression-bearing CST facts are qualified; call targets, types, interprocedural dataflow and behavior remain unresolved.",
        "semanticAlignmentVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--analysis", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--facts", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(
        args.packet,
        parse_mapping(args.analysis, "analysis"),
        parse_mapping(args.facts, "facts"),
    )
    require(not args.output.exists(), "refusing to overwrite expression qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": result["status"], "selectedExpressionFactCount": result["selectedExpressionFactCount"]}, sort_keys=True))


if __name__ == "__main__":
    main()
