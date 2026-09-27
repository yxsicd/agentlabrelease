use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    agentlab: PathBuf,
    qualification: PathBuf,
    source: PathBuf,
    upstream: PathBuf,
    contract: PathBuf,
    packet: PathBuf,
    gate: PathBuf,
    base: String,
    published: String,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-exact-patch-publication-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

fn git(root: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "git {} failed: {}",
        args.join(" "),
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn fixture() -> Fixture {
    let root = temp_root();
    let agentlab = root.join("agentlab");
    let qualification = agentlab.join("qualifications");
    let author = root.join("author");
    let upstream = root.join("upstream.git");
    let source = root.join("published");
    fs::create_dir_all(&qualification).unwrap();
    fs::create_dir_all(&author).unwrap();
    git(&author, &["init"]);
    git(&author, &["config", "user.name", "AgentLab Test"]);
    git(
        &author,
        &["config", "user.email", "agentlab-test@example.invalid"],
    );
    fs::write(author.join("purchase.ets"), "export const version = 1;\n").unwrap();
    git(&author, &["add", "purchase.ets"]);
    git(&author, &["commit", "-m", "base"]);
    let base = git(&author, &["rev-parse", "HEAD"]);
    fs::write(
        author.join("purchase.ets"),
        "export const version = 2;\nexport const tested = true;\n",
    )
    .unwrap();
    git(&author, &["add", "purchase.ets"]);
    git(&author, &["commit", "-m", "reviewed patch"]);
    let published = git(&author, &["rev-parse", "HEAD"]);
    let patch = Command::new("git")
        .arg("-C")
        .arg(&author)
        .args(["format-patch", "-1", "--stdout", &published])
        .output()
        .unwrap();
    assert!(patch.status.success());
    let patch_path = qualification.join("candidate.patch");
    fs::write(&patch_path, &patch.stdout).unwrap();
    git(&root, &["init", "--bare", upstream.to_str().unwrap()]);
    git(
        &author,
        &["remote", "add", "origin", upstream.to_str().unwrap()],
    );
    git(&author, &["push", "origin", "HEAD:refs/heads/main"]);
    let clone = Command::new("git")
        .args([
            "clone",
            upstream.to_str().unwrap(),
            source.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        clone.status.success(),
        "{}",
        String::from_utf8_lossy(&clone.stderr)
    );
    git(&source, &["checkout", &published]);
    git(&source, &["config", "user.name", "AgentLab Test"]);
    git(
        &source,
        &["config", "user.email", "agentlab-test@example.invalid"],
    );

    let source_packet = qualification.join("source-review.json");
    write(
        &source_packet,
        &json!({
            "schema": "agentlab.purchase_data_ohostest_review_packet.v1",
            "sourceRepository": upstream.to_str().unwrap(),
            "baseRevision": base,
            "candidateRevision": published,
            "artifacts": {"patch": {
                "path": "qualifications/candidate.patch",
                "sha256": digest(&patch.stdout),
                "byteLength": patch.stdout.len()
            }}
        }),
    );
    let lineage = json!({
        "baseRevision": base,
        "candidateRevision": published,
        "analysisSourceSetSha256": "1".repeat(64),
        "runtimeSourceSetSha256": "2".repeat(64)
    });
    let packet = qualification.join("integrated-packet.json");
    write(
        &packet,
        &json!({
            "schema": "agentlab.purchase_data_integrated_review_packet.v1",
            "sourceLineage": lineage,
            "evidenceAttachments": {"source-review-packet": {
                "path": "source-review.json",
                "sha256": digest(&fs::read(&source_packet).unwrap()),
                "byteLength": fs::metadata(&source_packet).unwrap().len()
            }}
        }),
    );
    let packet_sha = digest(&fs::read(&packet).unwrap());
    let contract = qualification.join("contract.json");
    write(
        &contract,
        &json!({
            "schema": "agentlab.purchase_data_unseen_agent_cohort_contract.v1",
            "status": "execution-contract-frozen-prerequisites-pending",
            "packetSha256": packet_sha,
            "allowsCaseContract": false,
            "automaticPromotion": false
        }),
    );
    let gate = qualification.join("gate.json");
    write(
        &gate,
        &json!({
            "schema": "agentlab.purchase_data_integrated_review_gate.v1",
            "status": "independent-dual-review-approved-next-calibration-only",
            "packetSha256": packet_sha,
            "sourceLineage": lineage,
            "semanticDecisionSha256": "3".repeat(64),
            "oracleDecisionSha256": "4".repeat(64),
            "reviewers": [
                {"identity": "github:semantic-reviewer"},
                {"identity": "github:oracle-reviewer"}
            ],
            "distinctAuthenticatedReviewerCount": 2,
            "semanticAlignmentVerified": true,
            "independentSourceReviewCompleted": true,
            "independentOracleReviewCompleted": true,
            "allowsExactPatchPublication": true,
            "requiresUpstreamRevisionReexecution": true,
            "allowsCaseContract": false,
            "automaticPromotion": false
        }),
    );
    Fixture {
        root,
        agentlab,
        qualification,
        source,
        upstream,
        contract,
        packet,
        gate,
        base,
        published,
    }
}

fn run(fixture: &Fixture, published: &str, output: &Path) -> Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-exact-patch-publication"
    ))
    .args([
        "--contract",
        fixture.contract.to_str().unwrap(),
        "--integrated-packet",
        fixture.packet.to_str().unwrap(),
        "--review-gate",
        fixture.gate.to_str().unwrap(),
        "--qualification-root",
        fixture.qualification.to_str().unwrap(),
        "--agentlab-root",
        fixture.agentlab.to_str().unwrap(),
        "--source-repository-root",
        fixture.source.to_str().unwrap(),
        "--published-revision",
        published,
        "--review-gate-run-id",
        "10001",
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn records_only_an_exact_reviewed_patch_visible_on_origin() {
    let fixture = fixture();
    let output = fixture.root.join("publication.json");
    let result = run(&fixture, &fixture.published, &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["status"], "exact-reviewed-patch-published");
    assert_eq!(value["publishedRevision"], fixture.published);
    assert_eq!(value["repository"], fixture.upstream.to_str().unwrap());
    assert_eq!(value["publishedRevisionContainsExactReviewedPatch"], true);
    assert_eq!(value["verifiedOnline"], true);
    assert_eq!(value["automaticPromotion"], false);
}

#[test]
fn rejects_a_published_revision_with_extra_tree_changes() {
    let fixture = fixture();
    fs::write(fixture.source.join("extra.txt"), "unreviewed\n").unwrap();
    git(&fixture.source, &["add", "extra.txt"]);
    git(
        &fixture.source,
        &["commit", "-m", "unreviewed extra change"],
    );
    let extra = git(&fixture.source, &["rev-parse", "HEAD"]);
    git(&fixture.source, &["push", "origin", "HEAD:refs/heads/main"]);
    let result = run(&fixture, &extra, &fixture.root.join("publication.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("published revision exact reviewed-patch tree differs"));
}

#[test]
fn rejects_an_exact_tree_revision_that_is_not_on_origin() {
    let fixture = fixture();
    git(
        &fixture.source,
        &["commit", "--allow-empty", "-m", "local only"],
    );
    let local = git(&fixture.source, &["rev-parse", "HEAD"]);
    let result = run(&fixture, &local, &fixture.root.join("publication.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("published revision is absent from the upstream origin"));
}

#[test]
fn rejects_a_non_approved_integrated_gate() {
    let fixture = fixture();
    let mut gate = read(&fixture.gate);
    gate["allowsExactPatchPublication"] = json!(false);
    write(&fixture.gate, &gate);
    let result = run(
        &fixture,
        &fixture.published,
        &fixture.root.join("publication.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("integrated review gate allowsExactPatchPublication differs"));
}

#[test]
fn rejects_base_lineage_drift() {
    let fixture = fixture();
    let mut source = read(&fixture.qualification.join("source-review.json"));
    source["baseRevision"] = json!(fixture.published);
    write(&fixture.qualification.join("source-review.json"), &source);
    let result = run(
        &fixture,
        &fixture.published,
        &fixture.root.join("publication.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("source-review packet digest differs"));
}

#[test]
fn fixture_retains_distinct_base_and_published_revisions() {
    let fixture = fixture();
    assert_ne!(fixture.base, fixture.published);
}

#[test]
fn trusted_main_workflow_uses_the_rust_producer_and_attests_its_receipt() {
    let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf();
    let workflow = fs::read_to_string(
        repository.join(".github/workflows/purchase-data-exact-patch-publication.yml"),
    )
    .unwrap();
    assert!(workflow.contains("github.ref == 'refs/heads/main'"));
    assert!(workflow.contains("purchase-data-integrated-oracle-review.yml"));
    assert!(workflow.contains("agentlab-purchase-data-exact-patch-publication"));
    assert!(workflow.contains("git clone --no-checkout \"$SOURCE_REPOSITORY\""));
    assert!(workflow.contains("--published-revision \"$PUBLISHED_REVISION\""));
    assert!(workflow.contains("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"));
    assert!(!workflow.contains("git push"));
}
