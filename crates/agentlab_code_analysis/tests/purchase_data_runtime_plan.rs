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
    calibration: PathBuf,
    ohostest_proposal: PathBuf,
    closure: PathBuf,
    target: PathBuf,
    registry: PathBuf,
    gate: PathBuf,
    output: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .unwrap()
            .to_path_buf();
        let root = std::env::temp_dir().join(format!(
            "agentlab-purchase-data-runtime-plan-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        let evidence =
            repository.join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd");
        let plan = evidence.join("purchase-data-behavior-oracle-plan.json");
        let calibration = evidence.join("purchase-data-behavior-oracle-calibration.json");
        let plan_value = read_json(&plan);
        let gate = root.join("oracle-gate.json");
        write_json(
            &gate,
            &json!({
                "schema":"agentlab.purchase_data_behavior_oracle_gate.v1",
                "status":"approved-for-runtime-calibration",
                "candidateId":plan_value["candidateId"],
                "sourceSetSha256":plan_value["sourceSetSha256"],
                "methodRevision":plan_value["methodRevision"],
                "planSha256":file_digest(&plan),
                "calibrationSha256":file_digest(&calibration),
                "semanticReviewer":"github:semantic-reviewer",
                "oracleReviewer":"github:oracle-reviewer",
                "verdict":"approve-for-runtime-calibration",
                "semanticAlignmentVerified":true,
                "behaviorOracleCandidateReviewed":true,
                "behaviorOracleVerified":false,
                "allowsRuntimeCalibration":true,
                "allowsCaseContract":false,
                "automaticPromotion":false,
                "nextGate":"runtime-calibration-and-independent-runtime-oracle-validation"
            }),
        );
        Self {
            root: root.clone(),
            repository: repository.clone(),
            plan,
            calibration,
            ohostest_proposal: evidence.join("purchase-data-ohostest-proposal.json"),
            closure: repository.join("release/closures/v0.1.0-alpha.13.json"),
            target: repository.join("release/targets/generic-linux-agentlab.json"),
            registry: repository.join("release/components/registry.json"),
            gate,
            output: root.join("runtime-plan.json"),
        }
    }

    fn run(&self) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-purchase-data-runtime-plan"))
            .args([
                "--oracle-gate",
                self.gate.to_str().unwrap(),
                "--behavior-plan",
                self.plan.to_str().unwrap(),
                "--behavior-calibration",
                self.calibration.to_str().unwrap(),
                "--ohostest-proposal",
                self.ohostest_proposal.to_str().unwrap(),
                "--release-closure",
                self.closure.to_str().unwrap(),
                "--target",
                self.target.to_str().unwrap(),
                "--component-registry",
                self.registry.to_str().unwrap(),
                "--output",
                self.output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn copy_to_root(&self, source: &Path, name: &str) -> PathBuf {
        let destination = self.root.join(name);
        fs::copy(source, &destination).unwrap();
        destination
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if self.root.exists() {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
}

fn read_json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn write_json(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn file_digest(path: &Path) -> String {
    digest(&fs::read(path).unwrap())
}

fn stderr(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

#[test]
fn binds_exact_runtime_inputs_and_preserves_testability_blocker() {
    let fixture = Fixture::new();
    let result = fixture.run();
    assert!(result.status.success(), "{}", stderr(&result));
    let plan = read_json(&fixture.output);
    assert_eq!(
        plan["schema"],
        "agentlab.purchase_data_runtime_calibration_plan.v1"
    );
    assert_eq!(
        plan["status"],
        "runtime-calibration-blocked-testability-refactor-required"
    );
    assert_eq!(plan["stages"].as_array().unwrap().len(), 3);
    assert_eq!(
        plan["stages"][0]["status"],
        "blocked-testability-refactor-required"
    );
    assert_eq!(plan["stages"][1]["status"], "blocked-upstream-stage");
    assert_eq!(plan["immutableAssets"].as_array().unwrap().len(), 3);
    assert_eq!(plan["stages"][1]["checkIds"].as_array().unwrap().len(), 10);
    assert_eq!(plan["execution"]["sourceBuildExecuted"], false);
    assert_eq!(plan["execution"]["ohosTestExecuted"], false);
    assert_eq!(plan["execution"]["emulatorExecuted"], false);
    assert_eq!(plan["execution"]["performanceProfileExecuted"], false);
    assert_eq!(plan["behaviorOracleVerified"], false);
    assert_eq!(plan["allowsCaseContract"], false);
    assert_eq!(
        plan["lineage"]["releaseClosureSha256"],
        file_digest(&fixture.closure)
    );
    assert_eq!(
        plan["lineage"]["componentRegistrySha256"],
        file_digest(&fixture.registry)
    );
    assert_eq!(
        plan["lineage"]["ohosTestProposalSha256"],
        file_digest(&fixture.ohostest_proposal)
    );
    assert_eq!(plan["release"]["version"], "0.1.0-alpha.13");
    assert_eq!(plan["environment"]["acceleration"], "kvm");
    assert_eq!(
        plan["stages"][2]["absolutePowerThermal"],
        "unavailable-on-emulator"
    );
}

#[test]
fn rejects_non_independent_or_unapproved_gate() {
    let fixture = Fixture::new();
    let mut gate = read_json(&fixture.gate);
    gate["oracleReviewer"] = gate["semanticReviewer"].clone();
    write_json(&fixture.gate, &gate);
    let collision = fixture.run();
    assert!(!collision.status.success());
    assert!(stderr(&collision).contains("not distinct GitHub identities"));

    gate["oracleReviewer"] = json!("github:oracle-reviewer");
    gate["status"] = json!("deferred-for-more-evidence");
    write_json(&fixture.gate, &gate);
    let deferred = fixture.run();
    assert!(!deferred.status.success());
    assert!(stderr(&deferred).contains("Oracle gate status differs"));
}

#[test]
fn advances_to_planned_only_with_source_bound_ohostest_inventory() {
    let mut fixture = Fixture::new();
    fixture.ohostest_proposal =
        fixture.copy_to_root(&fixture.ohostest_proposal, "ohostest-ready.json");
    let mut proposal = read_json(&fixture.ohostest_proposal);
    proposal["status"] = json!("source-bound-ohostest-ready-for-execution");
    proposal["observedStandardLane"]["existingTestSourcePaths"] =
        json!(["entry/src/ohosTest/ets/test/PurchaseFinalization.test.ets"]);
    proposal["observedStandardLane"]["sourceTestCount"] = json!(1);
    proposal["qualificationBoundary"]["ohosTestSourceAuthored"] = json!(true);
    write_json(&fixture.ohostest_proposal, &proposal);
    let result = fixture.run();
    assert!(result.status.success(), "{}", stderr(&result));
    let plan = read_json(&fixture.output);
    assert_eq!(plan["status"], "runtime-calibration-planned-not-executed");
    assert_eq!(plan["stages"][0]["status"], "planned-not-executed");
    assert_eq!(plan["stages"][1]["status"], "planned-not-executed");
    assert_eq!(
        plan["nextGate"],
        "execute-all-stages-and-independently-validate-runtime-receipts"
    );
}

#[test]
fn rejects_registry_or_calibration_digest_drift() {
    let mut fixture = Fixture::new();
    fixture.registry = fixture.copy_to_root(&fixture.registry, "registry.json");
    let mut registry = read_json(&fixture.registry);
    registry["components"][0]["status"] = json!("changed");
    write_json(&fixture.registry, &registry);
    let changed_registry = fixture.run();
    assert!(!changed_registry.status.success());
    assert!(stderr(&changed_registry).contains("component registry digest differs"));

    fixture.registry = fixture.repository.join("release/components/registry.json");
    fixture.calibration = fixture.copy_to_root(&fixture.calibration, "calibration.json");
    let mut calibration = read_json(&fixture.calibration);
    calibration["coverage"]["methodCount"] = json!(4);
    write_json(&fixture.calibration, &calibration);
    let changed_calibration = fixture.run();
    assert!(!changed_calibration.status.success());
    assert!(
        stderr(&changed_calibration).contains("Oracle gate calibration digest differs"),
        "{}",
        stderr(&changed_calibration)
    );
}

#[test]
fn refuses_to_overwrite_a_runtime_plan() {
    let fixture = Fixture::new();
    fs::write(&fixture.output, b"already exists\n").unwrap();
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(stderr(&result).contains("refusing to overwrite output"));
    assert_eq!(fs::read(&fixture.output).unwrap(), b"already exists\n");
}
