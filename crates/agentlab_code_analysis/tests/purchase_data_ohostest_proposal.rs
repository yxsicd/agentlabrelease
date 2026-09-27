use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    repository: PathBuf,
    plan: PathBuf,
    build: PathBuf,
    output: PathBuf,
}

impl Fixture {
    fn new(hypium: bool) -> Self {
        let root = std::env::temp_dir().join(format!(
            "agentlab-ohostest-proposal-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let repository = root.join("repository");
        fs::create_dir_all(repository.join("entry/src/main/ets/pages")).unwrap();
        fs::write(
            repository.join("entry/src/main/ets/pages/ConsumablesPage.ets"),
            b"import { iap } from '@kit.IAPKit';\nimport { JWSUtil } from '../common/JWSUtil';\n@Component\nstruct ConsumablesPage {\n  dealPurchaseData(purchaseData: string) { JWSUtil.decodeJwsObj(purchaseData); }\n  finishPurchase(order: Object) { iap.finishPurchase({}, order); }\n  build() { Column() {} }\n}\n",
        )
        .unwrap();
        fs::write(
            repository.join("entry/build-profile.json5"),
            "{ targets: [{ name: 'default' }, { name: 'ohosTest' }] }\n",
        )
        .unwrap();
        fs::write(
            repository.join("oh-package.json5"),
            if hypium {
                "{ devDependencies: { '@ohos/hypium': '1.0.6' } }\n"
            } else {
                "{ devDependencies: {} }\n"
            },
        )
        .unwrap();
        for args in [
            vec!["init", "--quiet"],
            vec!["config", "user.name", "AgentLab Test"],
            vec!["config", "user.email", "agentlab@example.invalid"],
            vec!["add", "."],
            vec!["commit", "--quiet", "-m", "fixture"],
        ] {
            assert!(Command::new("git")
                .arg("-C")
                .arg(&repository)
                .args(args)
                .status()
                .unwrap()
                .success());
        }
        let revision = git_text(&repository, &["rev-parse", "HEAD"]);
        let path = "entry/src/main/ets/pages/ConsumablesPage.ets";
        let source = fs::read(repository.join(path)).unwrap();
        let blob = git_text(&repository, &["rev-parse", &format!("HEAD:{path}")]);
        let plan = root.join("plan.json");
        write_json(
            &plan,
            &json!({
                "schema":"agentlab.purchase_data_behavior_oracle_plan.v1",
                "candidateId":"candidate",
                "sourceSetSha256":"1".repeat(64),
                "reviewPacketSha256":"2".repeat(64),
                "repositories":[{
                    "id":"harmony-iap-client",
                    "revision":revision,
                    "files":[{"path":path,"gitBlobOid":blob,"contentSha256":digest(&source)}]
                }],
                "methods":[
                    {"id":"dealPurchaseData","runtime":"harmony"},
                    {"id":"finishPurchase","runtime":"harmony"},
                    {"id":"cordovaMethod","runtime":"cordova"}
                ],
                "checks":[
                    {"id":"harmony-invalid-data-is-not-finished","stage":"harmony-finalization"},
                    {"id":"harmony-finished-order-is-not-finished-again","stage":"harmony-finalization"},
                    {"id":"harmony-pending-order-forwards-exact-identity","stage":"harmony-finalization"},
                    {"id":"harmony-missing-product-type-blocks-finish","stage":"harmony-finalization"},
                    {"id":"harmony-finish-rejection-is-observable","stage":"harmony-finalization"},
                    {"id":"cordova-check","stage":"cordova-consumption"}
                ]
            }),
        );
        let build = root.join("build.json");
        write_json(
            &build,
            &json!({
                "schema":"agentlab.multi_repo_source_build_qualification.v1",
                "status":"partial-build-qualified-review-required",
                "candidateId":"candidate",
                "sourceSetSha256":"1".repeat(64),
                "reviewPacketSha256":"3".repeat(64),
                "allowsCaseContract":false,
                "automaticPromotion":false
            }),
        );
        Self {
            root: root.clone(),
            repository,
            plan,
            build,
            output: root.join("proposal.json"),
        }
    }

    fn run(&self) -> Output {
        Command::new(env!(
            "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-proposal"
        ))
        .args([
            "--behavior-plan",
            self.plan.to_str().unwrap(),
            "--build-qualification",
            self.build.to_str().unwrap(),
            "--repository",
            &format!("harmony-iap-client={}", self.repository.display()),
            "--output",
            self.output.to_str().unwrap(),
        ])
        .output()
        .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if self.root.exists() {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
}

fn git_text(root: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(output.status.success());
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

fn write_json(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read_json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn stderr(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

#[test]
fn identifies_real_ohostest_lane_and_testability_blockers() {
    let fixture = Fixture::new(true);
    let result = fixture.run();
    assert!(result.status.success(), "{}", stderr(&result));
    let proposal = read_json(&fixture.output);
    assert_eq!(
        proposal["status"],
        "testability-refactor-required-before-standard-test-authoring"
    );
    assert_eq!(
        proposal["observedStandardLane"]["framework"],
        "instrument-test-ohosTest-hypium"
    );
    assert_eq!(
        proposal["observedStandardLane"]["buildTargetDeclared"],
        true
    );
    assert_eq!(
        proposal["observedStandardLane"]["hypiumDependencyDeclared"],
        true
    );
    assert_eq!(proposal["observedStandardLane"]["sourceTestCount"], 0);
    assert_eq!(
        proposal["blockedBehaviorCheckIds"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
    assert_eq!(proposal["programAnalysis"]["componentExported"], false);
    assert_eq!(
        proposal["lineage"]["behaviorPlanReviewPacketSha256"],
        "2".repeat(64)
    );
    assert_eq!(
        proposal["lineage"]["buildQualificationReviewPacketSha256"],
        "3".repeat(64)
    );
    assert!(proposal["blockers"]
        .as_array()
        .unwrap()
        .contains(&json!("finish-sink-is-static-direct-dependency")));
    assert_eq!(
        proposal["qualificationBoundary"]["ohosTestSourceAuthored"],
        false
    );
    assert_eq!(
        proposal["qualificationBoundary"]["allowsRuntimeCalibration"],
        false
    );
}

#[test]
fn rejects_source_identity_drift() {
    let fixture = Fixture::new(true);
    let mut plan = read_json(&fixture.plan);
    plan["repositories"][0]["files"][0]["contentSha256"] = json!("0".repeat(64));
    write_json(&fixture.plan, &plan);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(stderr(&result).contains("source content digest differs"));
}

#[test]
fn rejects_repository_without_hypium_standard_lane() {
    let fixture = Fixture::new(false);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(stderr(&result).contains("lacks the declared OHOS Test lane"));
}

#[test]
fn refuses_to_overwrite_proposal() {
    let fixture = Fixture::new(true);
    fs::write(&fixture.output, b"preserve\n").unwrap();
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(stderr(&result).contains("refusing to overwrite output"));
    assert_eq!(fs::read(&fixture.output).unwrap(), b"preserve\n");
}
