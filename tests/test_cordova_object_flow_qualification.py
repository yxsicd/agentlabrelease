from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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
    "cordova_object_flow_qualification",
    ROOT / "scripts/qualify-cordova-object-flow.py",
)


class CordovaObjectFlowQualificationTests(unittest.TestCase):
    def fixture(self, root: Path):
        repository = root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        source_path = "example.ts"
        template_path = "example.html"
        source = (
            "createPurchasedProductOnList = (productId, purchaseData, productType) => {\n"
            "  let product = this.getProduct(productId, productType);\n"
            "  product.purchaseData = purchaseData;\n"
            "  this.products.a.push(product);\n"
            "  this.products.b.push(product);\n"
            "  this.products.c.push(product);\n"
            "};\n"
            "consumeOwnedPurchase = async (productId, purchaseData, productType) => {\n"
            "  return this.api.consume({ inAppPurchaseData: purchaseData, });\n"
            "};\n"
        )
        template = (
            '<ion-item *ngFor="let product of products.a">\n'
            '  <button (click)="consumeOwnedPurchase(product, product.purchaseData, \'consumable\')"></button>\n'
            '</ion-item>\n'
            '<ion-item *ngFor="let product of products.b">\n'
            '  <button (click)="consumeOwnedPurchase(product, product.purchaseData, \'consumable\')"></button>\n'
            '</ion-item>\n'
        )
        (repository / source_path).write_text(source)
        (repository / template_path).write_text(template)
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        template_blob = subprocess.check_output(["git", "-C", str(repository), "rev-parse", f"HEAD:{template_path}"], text=True).strip()

        program = root / "program.json"
        program.write_text(json.dumps({
            "schema": QUALIFY.PROGRAM_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "reviewPacketSha256": "b" * 64,
            "flows": [{
                "flowId": "cordova-flow",
                "repositoryId": "hms-cordova-iap",
                "stepCount": 4,
                "steps": [
                    {
                        "index": 0,
                        "kind": "call-argument-to-parameter",
                        "status": "verified",
                        "callFactId": "call",
                        "callableFactId": "creator",
                        "argumentExpression": "message.values[ind]",
                        "parameterExpression": "purchaseData",
                        "parameterTypeExpression": None,
                    },
                    {
                        "index": 1,
                        "kind": "assignment-dependency",
                        "status": "verified",
                        "factId": "assignment",
                        "leftExpression": "product.purchaseData",
                        "rightExpression": "purchaseData",
                    },
                    {
                        "index": 2,
                        "kind": "template-event-bridge",
                        "status": "verified",
                        "path": template_path,
                        "gitBlobOid": template_blob,
                    },
                    {
                        "index": 3,
                        "kind": "call-argument-to-sink",
                        "status": "verified",
                        "callFactId": "sink",
                        "dependencyExpression": "purchaseData",
                    },
                ],
            }],
        }) + "\n")
        unresolved = [
            {"id": "parameter", "class": "parameter-type", "factId": "creator"},
            {"id": "member", "class": "alias-and-object-identity", "factId": "assignment"},
            {"id": "template", "class": "alias-and-object-identity", "factId": "consumer"},
            {"id": "control", "class": "control-flow"},
        ]
        external = root / "external.json"
        external.write_text(json.dumps({
            "schema": QUALIFY.EXTERNAL_SCHEMA,
            "status": "external-sink-contracts-qualified-review-required",
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "programAnalysisSha256": hashlib.sha256(program.read_bytes()).hexdigest(),
            "externalCallContractsResolved": True,
            "contracts": [{
                "contractId": "source-contract",
                "sourceType": {"typeExpression": "string[]"},
            }],
            "remainingUnresolved": unresolved,
            "remainingUnresolvedCount": 4,
        }) + "\n")

        def file_entry(path: str, snippets: list[str]):
            return {
                "path": path,
                "gitBlobOid": subprocess.check_output(
                    ["git", "-C", str(repository), "rev-parse", f"HEAD:{path}"], text=True
                ).strip(),
                "contentSha256": hashlib.sha256((repository / path).read_bytes()).hexdigest(),
                "exactSnippets": snippets,
            }

        call_expression = "consumeOwnedPurchase(product, product.purchaseData, 'consumable')"
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": QUALIFY.PLAN_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "programAnalysisSha256": hashlib.sha256(program.read_bytes()).hexdigest(),
            "externalSinkQualificationSha256": hashlib.sha256(external.read_bytes()).hexdigest(),
            "repositoryId": "hms-cordova-iap",
            "sourceRevision": revision,
            "flowId": "cordova-flow",
            "sourcePath": source_path,
            "templatePath": template_path,
            "files": [
                file_entry(source_path, [
                    "createPurchasedProductOnList = (productId, purchaseData, productType) => {",
                    "consumeOwnedPurchase = async (productId, purchaseData, productType) => {",
                ]),
                file_entry(template_path, [
                    '<ion-item *ngFor="let product of products.a">',
                    '<ion-item *ngFor="let product of products.b">',
                ]),
            ],
            "parameterFlow": {
                "callFactId": "call",
                "callableFactId": "creator",
                "argumentExpression": "message.values[ind]",
                "argumentIndex": 1,
                "parameterIndex": 1,
                "parameterName": "purchaseData",
                "effectiveType": "string",
                "sourceContractId": "source-contract",
            },
            "memberAssignment": {
                "factId": "assignment",
                "leftExpression": "product.purchaseData",
                "rightExpression": "purchaseData",
            },
            "creatorFlow": {
                "signature": "createPurchasedProductOnList = (productId, purchaseData, productType) => {",
                "objectBinding": "product",
                "bindingExpression": "this.getProduct(productId, productType)",
                "pushTargets": ["this.products.a", "this.products.b", "this.products.c"],
            },
            "templateBindings": [
                {"variable": "product", "collection": "products.a", "member": "purchaseData", "callExpression": call_expression},
                {"variable": "product", "collection": "products.b", "member": "purchaseData", "callExpression": call_expression},
            ],
            "sinkFlow": {
                "signature": "consumeOwnedPurchase = async (productId, purchaseData, productType) => {",
                "parameterName": "purchaseData",
                "requestFieldExpression": "inAppPurchaseData: purchaseData,",
                "sinkCallFactId": "sink",
            },
            "resolvedBoundaries": [
                {"id": "parameter", "class": "parameter-type", "factId": "creator"},
                {"id": "member", "class": "alias-and-object-identity", "factId": "assignment"},
                {"id": "template", "class": "alias-and-object-identity", "factId": "consumer"},
            ],
        }) + "\n")
        return program, external, plan, repository

    def test_exact_object_flow_resolves_three_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            result = QUALIFY.qualify(*self.fixture(Path(directory)))
            self.assertEqual(result["remainingUnresolvedCount"], 1)
            self.assertTrue(result["selectedFlowParameterTypeResolved"])
            self.assertTrue(result["memberObjectIdentityResolved"])
            self.assertTrue(result["templateObjectIdentityResolved"])
            self.assertTrue(result["typeResolutionComplete"])
            self.assertTrue(result["aliasResolutionComplete"])
            self.assertFalse(result["allowsCaseContract"])

    def test_changed_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            program, external, plan, repository = self.fixture(Path(directory))
            (repository / "new.txt").write_text("changed\n")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "changed"], check=True)
            with self.assertRaisesRegex(QUALIFY.CordovaObjectFlowError, "checkout revision differs"):
                QUALIFY.qualify(program, external, plan, repository)

    def test_object_reassignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            program, external, plan, repository = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["creatorFlow"]["bindingExpression"] = "this.other(productId)"
            plan.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(QUALIFY.CordovaObjectFlowError, "object binding differs"):
                QUALIFY.qualify(program, external, plan, repository)

    def test_template_collection_must_be_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            program, external, plan, repository = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["templateBindings"][0]["collection"] = "products.missing"
            plan.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(QUALIFY.CordovaObjectFlowError, "template collection occurrence differs"):
                QUALIFY.qualify(program, external, plan, repository)


if __name__ == "__main__":
    unittest.main()
