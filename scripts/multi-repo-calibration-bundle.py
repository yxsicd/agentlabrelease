#!/usr/bin/env python3
"""Review, stage, validate and execute an immutable calibration bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
PUBLIC_GITHUB_REPOSITORY = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?"
)
SOURCE_SCHEMA = "agentlab.multi_repo_calibration_bundle_source.v1"
PORTABLE_SOURCE_SCHEMA = "agentlab.multi_repo_calibration_bundle_portable_source.v1"
PROPOSAL_SCHEMA = "agentlab.multi_repo_calibration_bundle_proposal.v1"
REVIEW_SCHEMA = "agentlab.multi_repo_calibration_bundle_review.v1"
CONTRACT_SCHEMA = "agentlab.multi_repo_calibration_bundle.v1"
RUN_SCHEMA = "agentlab.multi_repo_calibration_bundle_run.v1"
CONSTRUCTION_SCHEMA = "agentlab.multi_repo_construction_contract.v1"
RISK_IDS = {
    "alternative-valid-solution-unverified",
    "driver-semantics-unverified",
    "oracle-independence-unverified",
    "reference-correctness-unverified",
    "wrong-variant-discrimination-unverified",
}
VARIANT_ROLES = {"baseline", "reference", "wrong", "alternative-valid"}


class BundleError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise BundleError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path}")
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_relative(value: Any, label: str) -> Path:
    require(
        isinstance(value, str)
        and value
        and len(value) <= 4096
        and "\\" not in value,
        f"{label} is invalid",
    )
    path = Path(value)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts), f"{label} is unsafe")
    return path


def within(root: Path, relative: Path, label: str) -> Path:
    require(root.is_dir() and not root.is_symlink(), f"{label} root must be a non-symlink directory")
    root = root.resolve()
    target = root / relative
    require(target.resolve().is_relative_to(root), f"{label} escapes its root")
    return target


def file_manifest(root: Path, relative_root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    directory = within(root, relative_root, "reference")
    require(directory.is_dir() and not directory.is_symlink(), "reference must be a non-symlink directory")
    rows = []
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), f"reference contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            rows.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            })
    require(rows, "reference has no files")
    return rows


def manifest_digest(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def complete_file_manifest(root: Path) -> list[dict[str, Any]]:
    require(root.is_dir() and not root.is_symlink(), "portable bundle root must be a non-symlink directory")
    root = root.resolve()
    rows = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"portable bundle contains a symlink: {path.relative_to(root)}")
        require(path.is_dir() or path.is_file(), f"portable bundle contains a special file: {path.relative_to(root)}")
        if path.is_file():
            rows.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            })
    require(rows, "portable bundle has no files")
    return rows


def portable_source_receipt(
    bundle_root: Path,
    construction_path: Path,
    repository: str,
    revision: str,
    bundle_path: str,
) -> dict[str, Any]:
    require(
        isinstance(repository, str) and PUBLIC_GITHUB_REPOSITORY.fullmatch(repository) is not None,
        "portable source repository must be a credential-free public GitHub HTTPS URL",
    )
    require(GIT_SHA.fullmatch(revision) is not None, "portable source revision must be a full Git SHA")
    relative_bundle = safe_relative(bundle_path, "portable source bundle path")
    descriptor_path = bundle_root / "descriptor.json"
    bundled_construction = bundle_root / "construction-contract.json"
    proposal_path = bundle_root / "calibration-bundle-proposal.json"
    require(digest(bundled_construction) == digest(construction_path), "portable source construction contract differs")
    proposal = load(proposal_path, "portable source calibration proposal")
    require(
        proposal == propose(bundle_root, descriptor_path, bundled_construction),
        "portable source proposal differs from exact bundle bytes",
    )
    construction = load(construction_path, "reviewed construction contract")
    files = complete_file_manifest(bundle_root)
    return {
        "schema": PORTABLE_SOURCE_SCHEMA,
        "status": "staged-for-calibration-proposal",
        "source": {
            "repository": repository,
            "revision": revision,
            "bundlePath": relative_bundle.as_posix(),
        },
        "candidateId": construction["candidateId"],
        "candidateSha256": construction["candidateSha256"],
        "sourceSetSha256": construction["sourceSetSha256"],
        "constructionContractSha256": digest(construction_path),
        "descriptorSha256": digest(descriptor_path),
        "proposalSha256": digest(proposal_path),
        "files": files,
        "fileManifestSha256": manifest_digest(files),
        "automaticPromotion": False,
    }


def validate_portable_source_receipt(receipt_path: Path, bundle_root: Path, construction_path: Path) -> dict[str, Any]:
    receipt = load(receipt_path, "portable calibration bundle source receipt")
    require(receipt.get("schema") == PORTABLE_SOURCE_SCHEMA, "unsupported portable source receipt")
    require(receipt.get("status") == "staged-for-calibration-proposal", "portable source receipt status differs")
    require(receipt.get("automaticPromotion") is False, "portable source receipt can auto-promote")
    source = receipt.get("source")
    require(isinstance(source, dict), "portable source identity is absent")
    expected = portable_source_receipt(
        bundle_root,
        construction_path,
        source.get("repository"),
        source.get("revision"),
        source.get("bundlePath"),
    )
    require(receipt == expected, "portable source receipt differs from exact bundle bytes")
    return receipt


def validate_draft(
    bundle_root: Path,
    descriptor_path: Path,
    oracle_contract: dict[str, Any],
) -> dict[str, Any]:
    descriptor = load(descriptor_path, "calibration bundle descriptor")
    require(descriptor.get("schema") == SOURCE_SCHEMA, "unsupported calibration bundle descriptor")
    require(descriptor.get("automaticPromotion") is False, "calibration bundle descriptor can auto-promote")
    require(
        isinstance(oracle_contract, dict)
        and oracle_contract.get("schema") == "agentlab.multi_repo_oracle_contract.v1",
        "unsupported Oracle contract",
    )
    runtime = descriptor.get("runtime")
    require(runtime == "python3", "calibration driver runtime must be python3")
    driver_relative = safe_relative(descriptor.get("driverPath"), "driver path")
    oracle_relative = safe_relative(descriptor.get("oraclePath"), "Oracle path")
    reference_relative = safe_relative(descriptor.get("referenceRoot"), "reference root")
    reserved = {Path("descriptor.json"), Path("construction-contract.json"), Path("calibration-bundle-proposal.json")}
    require(driver_relative != oracle_relative, "driver and Oracle paths must differ")
    require(driver_relative not in reserved and oracle_relative not in reserved, "bundle executable path collides with staged authority")
    require(reference_relative not in driver_relative.parents and reference_relative not in oracle_relative.parents, "executables must remain outside the reference tree")
    driver = within(bundle_root, driver_relative, "driver")
    oracle = within(bundle_root, oracle_relative, "Oracle")
    require(driver.is_file() and not driver.is_symlink(), "driver must be a regular non-symlink file")
    require(oracle.is_file() and not oracle.is_symlink(), "Oracle must be a regular non-symlink file")
    require(digest(oracle) == oracle_contract.get("oracleSha256"), "Oracle bytes differ from construction contract")
    require(descriptor.get("receiptSchema") == oracle_contract.get("receiptSchema"), "receipt schema differs from construction contract")
    expectations = oracle_contract.get("calibrationExpectations")
    require(isinstance(expectations, dict) and {"baseline", "reference"}.issubset(expectations), "construction contract lacks calibration expectations")
    variant_ids = descriptor.get("variantIds")
    require(
        isinstance(variant_ids, list)
        and variant_ids
        and len(variant_ids) == len(set(variant_ids))
        and all(isinstance(value, str) and TOKEN.fullmatch(value) for value in variant_ids),
        "calibration variant ids are invalid",
    )
    require(set(variant_ids) == set(expectations) - {"baseline", "reference"}, "calibration variant ids differ from construction contract")
    variant_roles = descriptor.get("variantRoles")
    require(
        isinstance(variant_roles, dict)
        and set(variant_roles) == set(expectations)
        and all(isinstance(name, str) and role in VARIANT_ROLES for name, role in variant_roles.items()),
        "calibration variant roles are invalid",
    )
    require(variant_roles.get("baseline") == "baseline", "baseline variant role differs")
    require(variant_roles.get("reference") == "reference", "reference variant role differs")
    require(
        sum(role == "baseline" for role in variant_roles.values()) == 1
        and sum(role == "reference" for role in variant_roles.values()) == 1,
        "baseline and reference roles must be unique",
    )
    wrong_ids = sorted(name for name, role in variant_roles.items() if role == "wrong")
    alternative_ids = sorted(name for name, role in variant_roles.items() if role == "alternative-valid")
    require(wrong_ids, "bundle requires a wrong variant")
    require(alternative_ids, "bundle requires an alternative valid solution")
    alternative_roots = descriptor.get("alternativeVariantRoots")
    require(
        isinstance(alternative_roots, dict) and set(alternative_roots) == set(alternative_ids),
        "alternative variant roots differ from alternative-valid roles",
    )
    stages = oracle_contract.get("stageOrder")
    require(isinstance(stages, list) and len(stages) >= 2, "Oracle stage order is invalid")
    require(not all(expectations["baseline"].get(stage) is True for stage in stages), "baseline must fail at least one stage")
    require(all(expectations["reference"].get(stage) is True for stage in stages), "reference must pass every stage")
    require(
        all(not all(expectations[name].get(stage) is True for stage in stages) for name in wrong_ids),
        "every wrong variant must fail at least one stage",
    )
    crossing = any(
        any(expectations[name].get(stage) is True for stage in stages[:-1])
        and any(expectations[name].get(stage) is False for stage in stages[1:])
        for name in wrong_ids
    )
    require(crossing, "bundle requires a wrong variant that passes an earlier stage and fails later")
    require(
        all(all(expectations[name].get(stage) is True for stage in stages) for name in alternative_ids),
        "every alternative valid solution must pass every stage",
    )
    alternatives = []
    occupied_roots = [reference_relative]
    for name in alternative_ids:
        relative_root = safe_relative(alternative_roots[name], f"alternative root for {name}")
        require(
            all(
                relative_root != occupied
                and relative_root not in occupied.parents
                and occupied not in relative_root.parents
                for occupied in occupied_roots
            ),
            f"alternative root overlaps another solution tree: {name}",
        )
        require(
            relative_root not in driver_relative.parents
            and relative_root not in oracle_relative.parents
            and driver_relative not in relative_root.parents
            and oracle_relative not in relative_root.parents,
            f"alternative root overlaps executable bytes: {name}",
        )
        files = file_manifest(bundle_root, relative_root)
        alternatives.append({
            "id": name,
            "root": relative_root.as_posix(),
            "treeSha256": manifest_digest(files),
            "files": files,
        })
        occupied_roots.append(relative_root)
    reference_files = file_manifest(bundle_root, reference_relative)
    return {
        "descriptor": descriptor,
        "driver": driver,
        "oracle": oracle,
        "referenceFiles": reference_files,
        "referenceTreeSha256": manifest_digest(reference_files),
        "alternatives": alternatives,
        "variantRoles": variant_roles,
    }


def validate_source(bundle_root: Path, descriptor_path: Path, construction_path: Path) -> dict[str, Any]:
    construction = load(construction_path, "reviewed construction contract")
    require(
        construction.get("schema") == CONSTRUCTION_SCHEMA
        and construction.get("status") == "reviewed-for-model-construction"
        and construction.get("automaticPromotion") is False,
        "construction contract is not reviewed",
    )
    validated = validate_draft(bundle_root, descriptor_path, construction.get("oracleContract") or {})
    validated["construction"] = construction
    return validated


def validate_authoring_source(
    receipt_path: Path,
    authoring_root: Path,
    construction: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    receipt = load(receipt_path, "calibration authoring receipt")
    require(
        receipt.get("schema") == "agentlab.multi_repo_calibration_authoring_receipt.v1"
        and receipt.get("status") == "review-required"
        and receipt.get("automaticPromotion") is False,
        "calibration authoring receipt is not review-required",
    )
    require(authoring_root.is_dir() and not authoring_root.is_symlink(), "calibration authoring root is invalid")
    draft = authoring_root / "draft"
    draft_files = complete_file_manifest(draft)
    require(receipt.get("draftFiles") == draft_files, "calibration authoring draft manifest differs")
    require(receipt.get("draftManifestSha256") == manifest_digest(draft_files), "calibration authoring draft digest differs")
    lineage = construction.get("calibrationAuthoring") or {}
    require(lineage.get("receiptSha256") == digest(receipt_path), "construction contract authoring receipt differs")
    require(lineage.get("draftManifestSha256") == receipt.get("draftManifestSha256"), "construction contract authoring draft differs")
    require(receipt.get("candidateId") == construction.get("candidateId"), "calibration authoring candidate differs")
    require(receipt.get("candidateSha256") == construction.get("candidateSha256"), "calibration authoring candidate bytes differ")
    require(receipt.get("sourceSetSha256") == construction.get("sourceSetSha256"), "calibration authoring source set differs")
    require(load(draft / "source-surface.json", "authored source surface") == construction.get("sourceSurface"), "authored source surface differs from construction contract")
    oracle_contract = load(draft / "oracle-contract.json", "authored Oracle contract")
    require(oracle_contract == construction.get("oracleContract"), "authored Oracle contract differs from construction contract")
    authored = validate_draft(draft / "bundle", draft / "bundle/calibration-bundle.json", oracle_contract)
    require(authored["descriptor"] == current["descriptor"], "authored calibration descriptor differs")
    require(digest(authored["driver"]) == digest(current["driver"]), "authored calibration driver differs")
    require(digest(authored["oracle"]) == digest(current["oracle"]), "authored calibration Oracle differs")
    require(authored["referenceFiles"] == current["referenceFiles"], "authored reference tree differs")
    require(authored["alternatives"] == current["alternatives"], "authored alternative trees differ")
    return receipt


def propose(
    bundle_root: Path,
    descriptor_path: Path,
    construction_path: Path,
    source_receipt_path: Path | None = None,
    authoring_receipt_path: Path | None = None,
    authoring_root: Path | None = None,
) -> dict[str, Any]:
    validated = validate_source(bundle_root, descriptor_path, construction_path)
    descriptor = validated["descriptor"]
    construction = validated["construction"]
    require(
        not (source_receipt_path is not None and authoring_receipt_path is not None),
        "portable and authored calibration sources are mutually exclusive",
    )
    require(
        (authoring_receipt_path is None) == (authoring_root is None),
        "authoring receipt and root must be supplied together",
    )
    result = {
        "schema": PROPOSAL_SCHEMA,
        "status": "review-required",
        "candidateId": construction["candidateId"],
        "candidateSha256": construction["candidateSha256"],
        "sourceSetSha256": construction["sourceSetSha256"],
        "constructionContractSha256": digest(construction_path),
        "descriptor": descriptor,
        "descriptorSha256": digest(descriptor_path),
        "driver": {"path": descriptor["driverPath"], "sha256": digest(validated["driver"])},
        "oracle": {"path": descriptor["oraclePath"], "sha256": digest(validated["oracle"])},
        "reference": {
            "root": descriptor["referenceRoot"],
            "treeSha256": validated["referenceTreeSha256"],
            "files": validated["referenceFiles"],
        },
        "variantIds": descriptor["variantIds"],
        "variantRoles": validated["variantRoles"],
        "alternatives": validated["alternatives"],
        "calibrationExpectations": construction["oracleContract"]["calibrationExpectations"],
        "risks": [
            {"id": "driver-semantics-unverified", "statement": "Reviewing exact driver bytes does not prove their execution semantics or runtime portability."},
            {"id": "alternative-valid-solution-unverified", "statement": "A structurally different passing implementation requires explicit review before it can qualify Oracle breadth."},
            {"id": "oracle-independence-unverified", "statement": "The Oracle matches the construction contract but its independence still requires explicit review."},
            {"id": "reference-correctness-unverified", "statement": "The exact reference tree still requires human confirmation as a valid solution."},
            {"id": "wrong-variant-discrimination-unverified", "statement": "Declared wrong variants still require retained executable calibration evidence."},
        ],
        "reviewPolicy": {
            "requiredDecisionSchema": REVIEW_SCHEMA,
            "requiredVerdict": "approve-for-calibration",
            "mustAcknowledgeEveryRisk": True,
        },
        "automaticPromotion": False,
    }
    if source_receipt_path is not None:
        source = validate_portable_source_receipt(source_receipt_path, bundle_root, construction_path)
        result["portableSource"] = {
            "receiptSha256": digest(source_receipt_path),
            "repository": source["source"]["repository"],
            "revision": source["source"]["revision"],
            "bundlePath": source["source"]["bundlePath"],
            "fileManifestSha256": source["fileManifestSha256"],
        }
    if authoring_receipt_path is not None:
        source = validate_authoring_source(
            authoring_receipt_path, authoring_root, construction, validated
        )
        participant = source["participant"]
        result["calibrationAuthoring"] = {
            "receiptSha256": digest(authoring_receipt_path),
            "draftManifestSha256": source["draftManifestSha256"],
            "participantId": participant["id"],
            "participantSha256": participant["sha256"],
            "methodRevision": participant.get("methodRevision"),
        }
    return result


def decide(proposal_path: Path, expected_sha256: str, reviewer: str, acknowledged: str, rationale: str) -> dict[str, Any]:
    proposal = load(proposal_path, "calibration bundle proposal")
    require(proposal.get("schema") == PROPOSAL_SCHEMA and proposal.get("status") == "review-required", "calibration bundle proposal is not review-required")
    require(SHA256.fullmatch(expected_sha256) is not None and digest(proposal_path) == expected_sha256, "calibration bundle proposal digest differs")
    require(isinstance(reviewer, str) and reviewer.strip(), "reviewer is required")
    require(isinstance(rationale, str) and len(rationale.strip()) >= 20, "review rationale is too short")
    acknowledged_ids = {value.strip() for value in acknowledged.split(",") if value.strip()}
    require(acknowledged_ids == RISK_IDS, "review must acknowledge every calibration bundle risk exactly")
    return {
        "schema": REVIEW_SCHEMA,
        "proposalSha256": expected_sha256,
        "reviewer": reviewer.strip(),
        "rationale": rationale.strip(),
        "verdict": "approve-for-calibration",
        "acknowledgedRiskIds": sorted(acknowledged_ids),
        "automaticPromotion": False,
    }


def compile_contract(proposal_path: Path, review_path: Path) -> dict[str, Any]:
    proposal = load(proposal_path, "calibration bundle proposal")
    review = load(review_path, "calibration bundle review")
    require(proposal.get("schema") == PROPOSAL_SCHEMA and proposal.get("status") == "review-required", "calibration bundle proposal is not review-required")
    require(review.get("schema") == REVIEW_SCHEMA, "unsupported calibration bundle review")
    require(review.get("proposalSha256") == digest(proposal_path), "calibration bundle review proposal digest differs")
    require(review.get("verdict") == "approve-for-calibration", "calibration bundle review verdict differs")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], "calibration bundle reviewer is absent")
    require(isinstance(review.get("rationale"), str) and review["rationale"], "calibration bundle review rationale is absent")
    require(set(review.get("acknowledgedRiskIds") or []) == RISK_IDS, "calibration bundle review risks differ")
    require(review.get("automaticPromotion") is False and proposal.get("automaticPromotion") is False, "calibration bundle can auto-promote")
    return {
        **proposal,
        "schema": CONTRACT_SCHEMA,
        "status": "reviewed-for-calibration",
        "review": {
            "authority": "explicit-maintainer-calibration-bundle-review",
            "reviewer": review.get("reviewer"),
            "rationale": review.get("rationale"),
            "verdict": review["verdict"],
            "acknowledgedRiskIds": sorted(RISK_IDS),
            "proposalSha256": digest(proposal_path),
            "decisionSha256": digest(review_path),
        },
        "automaticPromotion": False,
    }


def validate(
    contract_path: Path,
    proposal_path: Path,
    review_path: Path,
    bundle_root: Path,
    descriptor_path: Path,
    construction_path: Path,
    source_receipt_path: Path | None = None,
    authoring_receipt_path: Path | None = None,
    authoring_root: Path | None = None,
) -> dict[str, Any]:
    actual = load(contract_path, "reviewed calibration bundle")
    require(
        load(proposal_path, "calibration bundle proposal")
        == propose(
            bundle_root, descriptor_path, construction_path, source_receipt_path,
            authoring_receipt_path, authoring_root,
        ),
        "calibration bundle proposal differs from exact inputs",
    )
    require(actual == compile_contract(proposal_path, review_path), "reviewed calibration bundle differs from exact review")
    require(actual.get("status") == "reviewed-for-calibration", "calibration bundle status differs")
    return actual


def stage(
    bundle_root: Path,
    descriptor_path: Path,
    construction_path: Path,
    proposal_path: Path,
    output: Path,
    source_receipt_path: Path | None = None,
    authoring_receipt_path: Path | None = None,
    authoring_root: Path | None = None,
) -> None:
    require(not output.exists(), f"refusing to overwrite output: {output}")
    expected = propose(
        bundle_root, descriptor_path, construction_path, source_receipt_path,
        authoring_receipt_path, authoring_root,
    )
    require(load(proposal_path, "calibration bundle proposal") == expected, "calibration bundle proposal differs from exact inputs")
    output.mkdir(parents=True)
    shutil.copyfile(descriptor_path, output / "descriptor.json")
    shutil.copyfile(construction_path, output / "construction-contract.json")
    shutil.copyfile(proposal_path, output / "calibration-bundle-proposal.json")
    driver_relative = safe_relative(expected["driver"]["path"], "driver path")
    oracle_relative = safe_relative(expected["oracle"]["path"], "Oracle path")
    staged_driver = output / driver_relative
    staged_oracle = output / oracle_relative
    staged_driver.parent.mkdir(parents=True, exist_ok=True)
    staged_oracle.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(within(bundle_root, driver_relative, "driver"), staged_driver)
    shutil.copyfile(within(bundle_root, oracle_relative, "Oracle"), staged_oracle)
    reference = output / safe_relative(expected["reference"]["root"], "reference root")
    reference.mkdir()
    source_reference = within(bundle_root, safe_relative(expected["reference"]["root"], "reference root"), "reference")
    for row in expected["reference"]["files"]:
        source = within(bundle_root, safe_relative(row["path"], "reference file path"), "reference file")
        relative = source.relative_to(source_reference)
        target = reference / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for alternative in expected["alternatives"]:
        alternative_root = output / safe_relative(alternative["root"], f"alternative root for {alternative['id']}")
        alternative_root.mkdir(parents=True)
        source_root = within(bundle_root, safe_relative(alternative["root"], "alternative root"), "alternative")
        for row in alternative["files"]:
            source = within(bundle_root, safe_relative(row["path"], "alternative file path"), "alternative file")
            relative = source.relative_to(source_root)
            target = alternative_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def validate_summary(summary: dict[str, Any], contract: dict[str, Any]) -> None:
    require(summary.get("schema") == "agentlab.multi_repo_calibration.v1", "unsupported calibration summary")
    require(summary.get("candidateId") == contract.get("candidateId"), "calibration candidate differs")
    require(summary.get("sourceSetSha256") == contract.get("sourceSetSha256"), "calibration source set differs")
    require(summary.get("oracleSha256") == contract["oracle"]["sha256"], "calibration Oracle differs")
    require(summary.get("receiptSchema") == contract["descriptor"]["receiptSchema"], "calibration receipt schema differs")
    require(summary.get("infrastructureAvailable") is True, "calibration infrastructure was unavailable")
    expectations = contract["calibrationExpectations"]
    roles = contract["variantRoles"]
    variants = summary.get("variants")
    require(isinstance(variants, dict) and set(variants) == set(expectations), "calibration variants differ")
    require(summary.get("variantRoles") == roles, "calibration variant roles differ")
    for variant, stage_expectations in expectations.items():
        actual = variants.get(variant, {}).get("stages")
        require(isinstance(actual, dict) and set(actual) == set(stage_expectations), f"calibration stages differ for {variant}")
        for stage, expected in stage_expectations.items():
            require(actual[stage].get("pass") is expected, f"calibration verdict differs for {variant}/{stage}")
            require(SHA256.fullmatch(actual[stage].get("receiptSha256", "")) is not None, f"calibration receipt digest missing for {variant}/{stage}")


def run_bundle(
    bundle_root: Path,
    contract_path: Path,
    proposal_path: Path,
    review_path: Path,
    construction_path: Path,
    baseline: Path,
    output: Path,
    source_receipt_path: Path | None = None,
    authoring_receipt_path: Path | None = None,
    authoring_root: Path | None = None,
) -> dict[str, Any]:
    descriptor_path = bundle_root / "descriptor.json"
    contract = validate(
        contract_path,
        proposal_path,
        review_path,
        bundle_root,
        descriptor_path,
        construction_path,
        source_receipt_path,
        authoring_receipt_path,
        authoring_root,
    )
    require(baseline.is_dir() and not baseline.is_symlink(), "baseline must be a non-symlink directory")
    require(not output.exists(), f"refusing to overwrite output: {output}")
    descriptor = contract["descriptor"]
    driver_path = within(bundle_root, safe_relative(descriptor["driverPath"], "driver path"), "driver")
    oracle_path = within(bundle_root, safe_relative(descriptor["oraclePath"], "Oracle path"), "Oracle")
    reference_path = within(bundle_root, safe_relative(descriptor["referenceRoot"], "reference root"), "reference")
    command = [
        sys.executable,
        str(driver_path),
        "--baseline", str(baseline),
        "--reference", str(reference_path),
        "--oracle", str(oracle_path),
        "--source-set-sha256", contract["sourceSetSha256"],
        "--candidate-id", contract["candidateId"],
        "--output", str(output),
    ]
    for alternative in contract["alternatives"]:
        path = within(bundle_root, safe_relative(alternative["root"], "alternative root"), "alternative")
        command.extend(["--alternate", f"{alternative['id']}={path}"])
    process = subprocess.run(command, text=True, capture_output=True, timeout=900)
    require(process.returncode == 0, f"calibration driver failed: {process.stderr[-2000:]}")
    summary_path = output / "summary.json"
    summary = load(summary_path, "calibration summary")
    validate_summary(summary, contract)
    receipt = {
        "schema": RUN_SCHEMA,
        "status": "passed",
        "candidateId": contract["candidateId"],
        "sourceSetSha256": contract["sourceSetSha256"],
        "calibrationBundleSha256": digest(contract_path),
        "constructionContractSha256": digest(construction_path),
        "descriptorSha256": digest(descriptor_path),
        "driverSha256": digest(driver_path),
        "oracleSha256": digest(oracle_path),
        "referenceTreeSha256": contract["reference"]["treeSha256"],
        "alternativeTrees": [
            {"id": row["id"], "root": row["root"], "treeSha256": row["treeSha256"]}
            for row in contract["alternatives"]
        ],
        "summarySha256": digest(summary_path),
        "variantIds": sorted(summary["variants"]),
        "variantRoles": summary["variantRoles"],
        "automaticPromotion": False,
    }
    write(output / "calibration-run.json", receipt)
    (output / "driver.stdout.log").write_text(process.stdout, encoding="utf-8")
    (output / "driver.stderr.log").write_text(process.stderr, encoding="utf-8")
    return receipt


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    propose_command = commands.add_parser("propose")
    for command in (propose_command,):
        command.add_argument("--bundle-root", type=Path, required=True)
        command.add_argument("--descriptor", type=Path, required=True)
        command.add_argument("--construction-contract", type=Path, required=True)
        command.add_argument("--source-receipt", type=Path)
        command.add_argument("--authoring-receipt", type=Path)
        command.add_argument("--authoring-root", type=Path)
    propose_command.add_argument("--output", type=Path, required=True)
    decide_command = commands.add_parser("decide")
    decide_command.add_argument("--proposal", type=Path, required=True)
    decide_command.add_argument("--expected-sha256", required=True)
    decide_command.add_argument("--reviewer", required=True)
    decide_command.add_argument("--acknowledged-risk-ids", required=True)
    decide_command.add_argument("--rationale", required=True)
    decide_command.add_argument("--output", type=Path, required=True)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--proposal", type=Path, required=True)
    compile_command.add_argument("--review", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--bundle-root", type=Path, required=True)
    validate_command.add_argument("--descriptor", type=Path, required=True)
    validate_command.add_argument("--construction-contract", type=Path, required=True)
    validate_command.add_argument("--proposal", type=Path, required=True)
    validate_command.add_argument("--review", type=Path, required=True)
    validate_command.add_argument("--contract", type=Path, required=True)
    validate_command.add_argument("--source-receipt", type=Path)
    validate_command.add_argument("--authoring-receipt", type=Path)
    validate_command.add_argument("--authoring-root", type=Path)
    stage_command = commands.add_parser("stage")
    stage_command.add_argument("--bundle-root", type=Path, required=True)
    stage_command.add_argument("--descriptor", type=Path, required=True)
    stage_command.add_argument("--construction-contract", type=Path, required=True)
    stage_command.add_argument("--proposal", type=Path, required=True)
    stage_command.add_argument("--output", type=Path, required=True)
    stage_command.add_argument("--source-receipt", type=Path)
    stage_command.add_argument("--authoring-receipt", type=Path)
    stage_command.add_argument("--authoring-root", type=Path)
    run_command = commands.add_parser("run")
    run_command.add_argument("--bundle-root", type=Path, required=True)
    run_command.add_argument("--contract", type=Path, required=True)
    run_command.add_argument("--proposal", type=Path, required=True)
    run_command.add_argument("--review", type=Path, required=True)
    run_command.add_argument("--construction-contract", type=Path, required=True)
    run_command.add_argument("--baseline", type=Path, required=True)
    run_command.add_argument("--output", type=Path, required=True)
    run_command.add_argument("--source-receipt", type=Path)
    run_command.add_argument("--authoring-receipt", type=Path)
    run_command.add_argument("--authoring-root", type=Path)
    source_command = commands.add_parser("source-receipt")
    source_command.add_argument("--bundle-root", type=Path, required=True)
    source_command.add_argument("--construction-contract", type=Path, required=True)
    source_command.add_argument("--repository", required=True)
    source_command.add_argument("--revision", required=True)
    source_command.add_argument("--bundle-path", required=True)
    source_command.add_argument("--output", type=Path, required=True)
    validate_source_command = commands.add_parser("validate-source-receipt")
    validate_source_command.add_argument("--receipt", type=Path, required=True)
    validate_source_command.add_argument("--bundle-root", type=Path, required=True)
    validate_source_command.add_argument("--construction-contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "propose":
            value = propose(
                args.bundle_root, args.descriptor, args.construction_contract,
                args.source_receipt, args.authoring_receipt, args.authoring_root,
            )
            write(args.output, value)
            result = {"ok": True, "proposalSha256": digest(args.output), "status": value["status"]}
        elif args.command == "decide":
            value = decide(args.proposal, args.expected_sha256, args.reviewer, args.acknowledged_risk_ids, args.rationale)
            write(args.output, value)
            result = {"ok": True, "reviewSha256": digest(args.output), "verdict": value["verdict"]}
        elif args.command == "compile":
            value = compile_contract(args.proposal, args.review)
            write(args.output, value)
            result = {"ok": True, "contractSha256": digest(args.output), "status": value["status"]}
        elif args.command == "validate":
            value = validate(
                args.contract,
                args.proposal,
                args.review,
                args.bundle_root,
                args.descriptor,
                args.construction_contract,
                args.source_receipt,
                args.authoring_receipt,
                args.authoring_root,
            )
            result = {"ok": True, "contractSha256": digest(args.contract), "status": value["status"]}
        elif args.command == "stage":
            stage(
                args.bundle_root,
                args.descriptor,
                args.construction_contract,
                args.proposal,
                args.output,
                args.source_receipt,
                args.authoring_receipt,
                args.authoring_root,
            )
            result = {"ok": True, "output": str(args.output)}
        elif args.command == "run":
            value = run_bundle(
                args.bundle_root,
                args.contract,
                args.proposal,
                args.review,
                args.construction_contract,
                args.baseline,
                args.output,
                args.source_receipt,
                args.authoring_receipt,
                args.authoring_root,
            )
            result = {"ok": True, "runSha256": digest(args.output / "calibration-run.json"), "status": value["status"]}
        elif args.command == "source-receipt":
            value = portable_source_receipt(
                args.bundle_root,
                args.construction_contract,
                args.repository,
                args.revision,
                args.bundle_path,
            )
            write(args.output, value)
            result = {"ok": True, "sourceReceiptSha256": digest(args.output), "status": value["status"]}
        else:
            value = validate_portable_source_receipt(args.receipt, args.bundle_root, args.construction_contract)
            result = {"ok": True, "sourceReceiptSha256": digest(args.receipt), "status": value["status"]}
        print(json.dumps(result, sort_keys=True))
    except (BundleError, OSError, subprocess.TimeoutExpired, ValueError) as error:
        print(f"multi-repository calibration bundle invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
