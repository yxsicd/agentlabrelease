from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


QUALIFY = load_module(
    "external_sink_contract_qualification",
    ROOT / "scripts/qualify-external-sink-contracts.py",
)


class ExternalSinkContractQualificationTests(unittest.TestCase):
    def fixture(self, root: Path):
        repository = root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        files = {
            "example.ts": (
                'import { Api } from "pkg";\n'
                "constructor(private api: Api) {}\n"
                "api.consume({ value: source.values[index] });\n"
            ),
            "types.d.ts": (
                "interface Source { values: string[]; }\n"
                "interface Request { value: string; }\n"
                "declare function consume(request: Request): Promise<Result>;\n"
            ),
            "implementation.ts": (
                "export function consume(request: Request): Promise<Result> { return invoke(request); }\n"
            ),
        }
        for name, content in files.items():
            (repository / name).write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
        ).strip()

        program = root / "program.json"
        program.write_text(json.dumps({
            "schema": QUALIFY.PROGRAM_SCHEMA,
            "status": "bounded-program-flow-partially-resolved-review-required",
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "reviewPacketSha256": "b" * 64,
            "flowReplayExact": True,
            "coverage": {"externalSinkCount": 2},
            "flows": [
                {
                    "repositoryId": "repo",
                    "steps": [{
                        "kind": "call-argument-to-sink",
                        "callFactId": "sink-a",
                        "targetExpression": "this.api.consume",
                    }],
                },
                {
                    "repositoryId": "other",
                    "steps": [{
                        "kind": "call-argument-to-sink",
                        "callFactId": "sink-b",
                        "targetExpression": "sdk.finish",
                        "argumentIndex": 1,
                    }],
                },
            ],
            "unresolved": [
                {"id": "external-sink-signature:repo:sink-a", "class": "external-call-contract"},
                {"id": "external-sink-signature:other:sink-b", "class": "external-call-contract"},
                {"id": "global:control", "class": "control-flow"},
            ],
            "unresolvedCount": 3,
        }) + "\n")

        authority_files = []
        snippets = {
            "example.ts": [
                'import { Api } from "pkg";',
                "constructor(private api: Api) {}",
            ],
            "types.d.ts": [
                "interface Source { values: string[]; }",
                "interface Request { value: string; }",
                "declare function consume(request: Request): Promise<Result>;",
            ],
            "implementation.ts": [
                "export function consume(request: Request): Promise<Result> { return invoke(request); }",
            ],
        }
        for name in files:
            blob = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", f"HEAD:{name}"], text=True
            ).strip()
            authority_files.append({
                "path": name,
                "gitBlobOid": blob,
                "contentSha256": hashlib.sha256((repository / name).read_bytes()).hexdigest(),
                "exactSnippets": snippets[name],
            })
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": QUALIFY.PLAN_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "contracts": [{
                "contractId": "repo-consume",
                "repositoryId": "repo",
                "sinkCallFactId": "sink-a",
                "targetExpression": "this.api.consume",
                "authority": {
                    "kind": "git-blob-set",
                    "sourceRevision": revision,
                    "files": authority_files,
                },
                "receiverBinding": {"property": "api", "typeExpression": "Api"},
                "sourceType": {"interface": "Source", "field": "values", "typeExpression": "string[]"},
                "requestField": {"interface": "Request", "field": "value", "typeExpression": "string"},
                "signature": {"callable": "consume", "parameterName": "request", "parameterType": "Request", "returnType": "Promise<Result>"},
            }],
        }) + "\n")
        return program, plan, {"repo": repository}

    def sdk_fixture(self, root: Path):
        program, plan, repositories = self.fixture(root)
        source = root / "sdk-source"
        members = {
            "sdk/kits/@kit.Test.d.ts": (
                "import sdk from '@hms.core.api';\n"
                "export { sdk };\n"
            ),
            "sdk/config/@kit.Test.json": json.dumps({
                "symbols": {"sdk": {"source": "@hms.core.api.d.ts", "bindings": "default"}}
            }, indent=2) + "\n",
            "sdk/api/@hms.core.api.d.ts": (
                "declare namespace api {\n"
                "  interface FinishRequest {\n"
                "    productType: ProductType;\n"
                "    purchaseToken: string;\n"
                "    purchaseOrderId: string;\n"
                "  }\n"
                "  function finish(context: Context, parameter: FinishRequest): Promise<void>;\n"
                "}\n"
            ),
        }
        for name, content in members.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        archive = root / "sdk.tar"
        with tarfile.open(archive, mode="w") as bundle:
            for name in members:
                bundle.add(source / name, arcname=name)
        value = json.loads(plan.read_text())
        value["schema"] = QUALIFY.PLAN_SCHEMA_V2
        value["contracts"].append({
            "contractId": "sdk-finish",
            "repositoryId": "other",
            "sinkCallFactId": "sink-b",
            "targetExpression": "sdk.finish",
            "authority": {
                "kind": "sdk-archive-member-set",
                "assetId": "sdk-test",
                "archiveFormat": "tar",
                "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "releaseTag": "sdk-test-v1",
                "releaseUrl": "https://example.invalid/sdk-test-v1",
                "members": [
                    {
                        "path": name,
                        "contentSha256": hashlib.sha256((source / name).read_bytes()).hexdigest(),
                        "exactSnippets": [
                            {
                                "sdk/kits/@kit.Test.d.ts": "import sdk from '@hms.core.api';",
                                "sdk/config/@kit.Test.json": '"source": "@hms.core.api.d.ts"',
                                "sdk/api/@hms.core.api.d.ts": "function finish(context: Context, parameter: FinishRequest): Promise<void>;",
                            }[name]
                        ],
                    }
                    for name in members
                ],
            },
            "moduleBinding": {
                "symbol": "sdk",
                "sourceModule": "@hms.core.api",
                "sourceDeclaration": "@hms.core.api.d.ts",
                "kitDeclarationMember": "sdk/kits/@kit.Test.d.ts",
                "kitConfigMember": "sdk/config/@kit.Test.json",
                "sourceDeclarationMember": "sdk/api/@hms.core.api.d.ts",
            },
            "requestType": {
                "interface": "FinishRequest",
                "fields": [
                    {"field": "productType", "typeExpression": "ProductType"},
                    {"field": "purchaseToken", "typeExpression": "string"},
                    {"field": "purchaseOrderId", "typeExpression": "string"},
                ],
            },
            "signature": {
                "callable": "finish",
                "contextType": "Context",
                "parameterIndex": 1,
                "parameterName": "parameter",
                "parameterType": "FinishRequest",
                "returnType": "Promise<void>",
            },
        })
        plan.write_text(json.dumps(value) + "\n")
        return program, plan, repositories, {"sdk-test": archive}

    def test_one_exact_contract_reduces_but_does_not_hide_unresolved_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            result = QUALIFY.qualify(*self.fixture(Path(directory)))
            self.assertEqual(result["resolvedExternalSinkCount"], 1)
            self.assertEqual(result["remainingExternalSinkCount"], 1)
            self.assertEqual(result["originalUnresolvedCount"], 3)
            self.assertEqual(result["remainingUnresolvedCount"], 2)
            self.assertTrue(result["contracts"][0]["sourceToRequestTypeCompatible"])
            self.assertFalse(result["externalCallContractsResolved"])
            self.assertFalse(result["allowsCaseContract"])
            self.assertFalse(result["automaticPromotion"])

    def test_changed_git_blob_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            program, plan, repositories = self.fixture(Path(directory))
            repository = repositories["repo"]
            (repository / "types.d.ts").write_text("changed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "types.d.ts"], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "changed"], check=True)
            with self.assertRaisesRegex(
                QUALIFY.ExternalSinkContractError,
                "checkout revision differs",
            ):
                QUALIFY.qualify(program, plan, repositories)

    def test_source_and_request_types_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            program, plan, repositories = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["contracts"][0]["requestField"]["typeExpression"] = "number"
            plan.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(
                QUALIFY.ExternalSinkContractError,
                "source and request field types differ",
            ):
                QUALIFY.qualify(program, plan, repositories)

    def test_snippet_must_occur_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            program, plan, repositories = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["contracts"][0]["authority"]["files"][0]["exactSnippets"][0] = "missing"
            plan.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(
                QUALIFY.ExternalSinkContractError,
                "snippet occurrence differs",
            ):
                QUALIFY.qualify(program, plan, repositories)

    def test_exact_sdk_archive_resolves_remaining_external_sink(self):
        with tempfile.TemporaryDirectory() as directory:
            result = QUALIFY.qualify(*self.sdk_fixture(Path(directory)))
            self.assertEqual(result["schema"], QUALIFY.SCHEMA_V2)
            self.assertEqual(result["status"], "external-sink-contracts-qualified-review-required")
            self.assertEqual(result["resolvedExternalSinkCount"], 2)
            self.assertEqual(result["remainingExternalSinkCount"], 0)
            self.assertEqual(result["remainingUnresolvedCount"], 1)
            self.assertTrue(result["externalCallContractsResolved"])
            self.assertEqual(result["contracts"][1]["authority"], "exact-sdk-archive-member-set")
            self.assertFalse(result["allowsCaseContract"])

    def test_changed_sdk_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            program, plan, repositories, archives = self.sdk_fixture(Path(directory))
            archives["sdk-test"].write_bytes(archives["sdk-test"].read_bytes() + b"changed")
            with self.assertRaisesRegex(
                QUALIFY.ExternalSinkContractError,
                "SDK archive digest differs",
            ):
                QUALIFY.qualify(program, plan, repositories, archives)

    def test_sdk_request_field_must_match_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            program, plan, repositories, archives = self.sdk_fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["contracts"][1]["requestType"]["fields"][1]["typeExpression"] = "number"
            plan.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(
                QUALIFY.ExternalSinkContractError,
                "SDK request field differs: purchaseToken",
            ):
                QUALIFY.qualify(program, plan, repositories, archives)


if __name__ == "__main__":
    unittest.main()
