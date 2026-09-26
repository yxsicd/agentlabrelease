import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/calibrate-purchase-data-behavior-oracle.py"
spec = importlib.util.spec_from_file_location("purchase_data_behavior_oracle", SCRIPT)
CALIBRATION = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(CALIBRATION)


HARMONY = """
dealPurchaseData(purchaseData: string) {
  try {
    const value = (JSON.parse(purchaseData) as PurchaseData).jwsPurchaseOrder;
    if (!value) { Logger.error(TAG, 'missing'); return; }
    const order = JSON.parse(JWSUtil.decodeJwsObj(value)) as PurchaseOrderPayload;
    if (order && order.finishStatus !== FinishStatus.FINISHED) this.finishPurchase(order);
  } catch (error) { Logger.error(TAG, 'invalid'); }
}

finishPurchase(purchaseOrder: PurchaseOrderPayload) {
  if (!purchaseOrder.productType) { Logger.error(TAG, 'missing type'); return; }
  const parameter: iap.FinishPurchaseParameter = {
    productType: Number(purchaseOrder.productType),
    purchaseToken: purchaseOrder.purchaseToken,
    purchaseOrderId: purchaseOrder.purchaseOrderId
  };
  iap.finishPurchase(this.context, parameter).then(() => {
    Logger.info(TAG, 'finished');
  }).catch((err: BusinessError) => {
    Logger.error(TAG, `finish failed ${err.message}`);
  });
}
""".lstrip()


CORDOVA = """
obtainOwnedPurchasesFromType = async (pType) => {
  try {
    let message = await this.iap.obtainOwnedPurchases({ priceType: PRODUCTS[pType].type });
    console.log(message);
    message.itemList.map((pId, ind) =>
      this.createPurchasedProductOnList(pId, message.inAppPurchaseDataList[ind], pType)
    );
  } catch (err) { console.log(err); }
};

createPurchasedProductOnList = (productId, purchaseData, productType) => {
  let product = this.getProduct(productId, productType);
  product.purchaseData = purchaseData;
  switch (productType) {
    case "consumable": this.products.purchased_consumable.push(product); break;
    case "nonconsumable": this.products.purchased_nonconsumable.push(product); break;
    case "subscription": this.products.purchased_subscription.push(product); break;
    default: break;
  }
};

consumeOwnedPurchase = async (productId, purchaseData, productType) => {
  try {
    let message = await this.iap.consumeOwnedPurchase({
      inAppPurchaseData: purchaseData,
      developerChallenge: DEVELOPERCHALLENGE,
    });
    if (message.returnCode === 0) {
      this.products = {
        consumable: [], nonconsumable: [], subscription: [],
        purchased_consumable: [], purchased_nonconsumable: [], purchased_subscription: [],
        purchased_record_consumable: [], purchased_record_subscription: [],
      };
      this.getProductsInformation();
    } else {
      alert(JSON.stringify(message, null, 4));
      console.log("Consume was not successful.");
    }
  } catch (err) { console.log(err); }
};
""".lstrip()


CHECK_IDS = [
    "harmony-invalid-data-is-not-finished",
    "harmony-finished-order-is-not-finished-again",
    "harmony-pending-order-forwards-exact-identity",
    "harmony-missing-product-type-blocks-finish",
    "harmony-finish-rejection-is-observable",
    "cordova-owned-items-preserve-indexed-purchase-data",
    "cordova-consume-forwards-exact-purchase-data",
    "cordova-success-resets-and-reloads",
    "cordova-business-failure-retains-state-and-alerts",
    "cordova-rejection-retains-state-and-logs",
]


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def run(*args, cwd: Path):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class PurchaseDataBehaviorOracleCalibrationTests(unittest.TestCase):
    def fixture(self, root: Path):
        repositories = {}
        files = {
            "harmony-iap-client": ("src/ConsumablesPage.ets", HARMONY),
            "hms-cordova-iap": ("src/home.page.ts", CORDOVA),
        }
        for repository_id, (relative, content) in files.items():
            repository = root / repository_id
            repository.mkdir()
            run("git", "init", "-q", cwd=repository)
            run("git", "config", "user.email", "tests@example.invalid", cwd=repository)
            run("git", "config", "user.name", "AgentLab Tests", cwd=repository)
            path = repository / relative
            path.parent.mkdir(parents=True)
            path.write_text(content)
            run("git", "add", relative, cwd=repository)
            run("git", "commit", "-qm", "fixture", cwd=repository)
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            blob = subprocess.check_output(["git", "rev-parse", f"HEAD:{relative}"], cwd=repository, text=True).strip()
            repositories[repository_id] = {
                "root": repository,
                "revision": revision,
                "path": relative,
                "blob": blob,
                "contentSha256": sha_bytes(content.encode()),
            }

        candidate_id = "difficulty-test-purchase-data"
        source_set = "1" * 64
        packet = root / "packet.json"
        packet.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_review_packet.v11",
            "status": "independent-semantic-review-required",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "semanticAlignmentVerified": False,
            "behaviorOracleVerified": False,
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }))
        qualification = root / "qualification.json"
        qualification.write_text(json.dumps({
            "schema": "agentlab.selected_control_flow_qualification.v1",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "remainingUnresolvedCount": 0,
            "reachabilityAndDominanceResolved": True,
            "semanticAlignmentVerified": False,
            "behaviorOracleVerified": False,
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }))

        method_rows = []
        specs = [
            ("dealPurchaseData", "harmony", "harmony-iap-client", "dealPurchaseData(purchaseData: string) {", [
                {"find": " as PurchaseData", "replace": "", "occurrences": 1},
                {"find": " as PurchaseOrderPayload", "replace": "", "occurrences": 1},
            ]),
            ("finishPurchase", "harmony", "harmony-iap-client", "finishPurchase(purchaseOrder: PurchaseOrderPayload) {", [
                {"find": ": iap.FinishPurchaseParameter", "replace": "", "occurrences": 1},
                {"find": "(err: BusinessError)", "replace": "(err)", "occurrences": 1},
            ]),
            ("obtainOwnedPurchasesFromType", "cordova", "hms-cordova-iap", "obtainOwnedPurchasesFromType = async (pType) => {", []),
            ("createPurchasedProductOnList", "cordova", "hms-cordova-iap", "createPurchasedProductOnList = (productId, purchaseData, productType) => {", []),
            ("consumeOwnedPurchase", "cordova", "hms-cordova-iap", "consumeOwnedPurchase = async (productId, purchaseData, productType) => {", []),
        ]
        for method_id, runtime, repository_id, start, replacements in specs:
            source = HARMONY if runtime == "harmony" else CORDOVA
            method, body = CALIBRATION.extract_method(source, start)
            method_rows.append({
                "id": method_id,
                "runtime": runtime,
                "repositoryId": repository_id,
                "path": repositories[repository_id]["path"],
                "startSnippet": start,
                "methodSha256": sha_bytes(method.encode()),
                "bodySha256": sha_bytes(body.encode()),
                "transpileReplacements": replacements,
            })

        variants = [
            {"id": "exact-source", "role": "exact-source", "mutations": [], "expectedFailedChecks": []},
            {"id": "wrong-finish-status-polarity", "role": "meaningful-wrong", "mutations": [
                {"runtime": "harmony", "methodId": "dealPurchaseData", "find": "finishStatus !== FinishStatus.FINISHED", "replace": "finishStatus === FinishStatus.FINISHED", "occurrences": 1}
            ], "expectedFailedChecks": ["harmony-finished-order-is-not-finished-again", "harmony-pending-order-forwards-exact-identity"]},
            {"id": "wrong-finish-token-source", "role": "meaningful-wrong", "mutations": [
                {"runtime": "harmony", "methodId": "finishPurchase", "find": "purchaseToken: purchaseOrder.purchaseToken", "replace": "purchaseToken: purchaseOrder.purchaseOrderId", "occurrences": 1}
            ], "expectedFailedChecks": ["harmony-pending-order-forwards-exact-identity"]},
            {"id": "wrong-owned-data-index", "role": "meaningful-wrong", "mutations": [
                {"runtime": "cordova", "methodId": "obtainOwnedPurchasesFromType", "find": "message.inAppPurchaseDataList[ind]", "replace": "message.inAppPurchaseDataList[0]", "occurrences": 1}
            ], "expectedFailedChecks": ["cordova-owned-items-preserve-indexed-purchase-data"]},
            {"id": "wrong-consume-data-source", "role": "meaningful-wrong", "mutations": [
                {"runtime": "cordova", "methodId": "consumeOwnedPurchase", "find": "inAppPurchaseData: purchaseData", "replace": "inAppPurchaseData: productId", "occurrences": 1}
            ], "expectedFailedChecks": ["cordova-consume-forwards-exact-purchase-data"]},
            {"id": "wrong-consume-success-polarity", "role": "meaningful-wrong", "mutations": [
                {"runtime": "cordova", "methodId": "consumeOwnedPurchase", "find": "message.returnCode === 0", "replace": "message.returnCode !== 0", "occurrences": 1}
            ], "expectedFailedChecks": ["cordova-business-failure-retains-state-and-alerts", "cordova-success-resets-and-reloads"]},
        ]
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": "agentlab.purchase_data_behavior_oracle_plan.v1",
            "methodRevision": "2" * 40,
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "reviewPacketSha256": sha(packet),
            "controlFlowQualificationSha256": sha(qualification),
            "seamExecutableSha256": sha(ROOT / "scripts/purchase-data-behavior-seam.js"),
            "repositories": [
                {
                    "id": repository_id,
                    "repository": f"https://example.invalid/{repository_id}.git",
                    "revision": row["revision"],
                    "files": [{"path": row["path"], "gitBlobOid": row["blob"], "contentSha256": row["contentSha256"]}],
                }
                for repository_id, row in repositories.items()
            ],
            "methods": method_rows,
            "checks": [{"id": value, "stage": "fixture", "behavior": value} for value in CHECK_IDS],
            "variants": variants,
            "qualificationBoundary": {"selectedMethodBodiesOnly": True},
        }))
        return plan, packet, qualification, repositories

    def test_exact_methods_pass_and_meaningful_wrong_variants_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, packet, qualification, repositories = self.fixture(root)
            result = CALIBRATION.qualify(
                plan,
                packet,
                qualification,
                {key: value["root"] for key, value in repositories.items()},
                "node",
            )
            self.assertTrue(result["sourceSeamCalibrated"])
            self.assertEqual(result["methodRevision"], "2" * 40)
            self.assertTrue(result["coverage"]["exactSourceAllChecksPassed"])
            self.assertTrue(result["coverage"]["allNegativeControlsDetected"])
            self.assertEqual(result["coverage"]["checkCount"], 10)
            self.assertEqual(result["coverage"]["negativeControlCount"], 5)
            self.assertFalse(result["behaviorOracleVerified"])
            self.assertFalse(result["allowsCaseContract"])
            retained_root = ROOT / "release/qualifications/alpha13-payment-feedback-analysis-165bcbd"
            retained_plan = json.loads((retained_root / "purchase-data-behavior-oracle-plan.json").read_text())
            retained = json.loads((retained_root / "purchase-data-behavior-oracle-calibration.json").read_text())
            self.assertEqual(retained["planSha256"], sha(retained_root / "purchase-data-behavior-oracle-plan.json"))
            self.assertEqual(retained["methodRevision"], retained_plan["methodRevision"])
            self.assertEqual(retained["coverage"]["checkCount"], 10)
            self.assertEqual(retained["coverage"]["negativeControlCount"], 5)
            self.assertTrue(retained["coverage"]["allNegativeControlsDetected"])
            self.assertFalse(retained["behaviorOracleVerified"])

    def test_changed_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, packet, qualification, repositories = self.fixture(root)
            changed = repositories["harmony-iap-client"]["root"]
            (changed / "extra.txt").write_text("drift")
            run("git", "add", "extra.txt", cwd=changed)
            run("git", "commit", "-qm", "drift", cwd=changed)
            with self.assertRaisesRegex(CALIBRATION.CalibrationError, "checkout differs"):
                CALIBRATION.qualify(
                    plan,
                    packet,
                    qualification,
                    {key: value["root"] for key, value in repositories.items()},
                    "node",
                )

    def test_negative_control_expectation_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, packet, qualification, repositories = self.fixture(root)
            value = json.loads(plan.read_text())
            value["variants"][1]["expectedFailedChecks"] = []
            plan.write_text(json.dumps(value))
            with self.assertRaisesRegex(CALIBRATION.CalibrationError, "expectation differs"):
                CALIBRATION.qualify(
                    plan,
                    packet,
                    qualification,
                    {key: item["root"] for key, item in repositories.items()},
                    "node",
                )


if __name__ == "__main__":
    unittest.main()
