use std::{fs, path::PathBuf};

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .expect("crate must live below the repository root")
        .to_path_buf()
}

#[test]
fn candidate_review_revalidates_exact_maintainer_knowledge() {
    let workflow = fs::read_to_string(
        repository().join(".github/workflows/multi-repo-candidate-review-packet.yml"),
    )
    .unwrap();
    for required in [
        "knowledge_run_id:",
        "knowledge_artifact:",
        "expected_knowledge_cut_sha256:",
        ".github/workflows/maintainer-knowledge-cut.yml",
        "agentlab-maintainer-knowledge-gate",
        "--stage candidate",
        "maintainer-knowledge-gate-receipt.json",
    ] {
        assert!(workflow.contains(required), "missing {required}");
    }
}

#[test]
fn purchase_data_successor_workflows_fail_closed_at_the_required_stage() {
    let workflows = [
        ("purchase-data-behavior-oracle-review.yml", "construction"),
        ("purchase-data-ohostest-source-review.yml", "construction"),
        (
            "purchase-data-integrated-semantic-review.yml",
            "calibration",
        ),
        ("purchase-data-integrated-oracle-review.yml", "calibration"),
        ("purchase-data-exact-patch-publication.yml", "calibration"),
        (
            "purchase-data-published-revision-reexecution.yml",
            "calibration",
        ),
        ("purchase-data-trusted-case-freeze.yml", "freeze"),
    ];
    for (name, stage) in workflows {
        let workflow = fs::read_to_string(repository().join(".github/workflows").join(name))
            .unwrap_or_else(|error| panic!("read {name}: {error}"));
        for required in [
            "knowledge_gate_run_id:",
            "knowledge_gate_artifact:",
            "expected_knowledge_gate_receipt_sha256:",
            "uses: ./.github/actions/require-maintainer-knowledge-gate",
            "candidate_id: difficulty-c75c82b3a697d8053e74bb37",
        ] {
            assert!(workflow.contains(required), "{name} is missing {required}");
        }
        assert!(
            workflow.contains(&format!("minimum_stage: {stage}")),
            "{name} does not require {stage}"
        );
    }
}

#[test]
fn reusable_gate_accepts_only_the_trusted_main_qualification_workflow() {
    let action = fs::read_to_string(
        repository().join(".github/actions/require-maintainer-knowledge-gate/action.yml"),
    )
    .unwrap();
    for required in [
        "value['head_branch']=='main'",
        "value['path']=='.github/workflows/maintainer-knowledge-cut.yml'",
        "value['conclusion']=='success'",
        "maintainer-knowledge-gate-receipt.json",
        "sha256sum -c -",
    ] {
        assert!(action.contains(required), "missing {required}");
    }
}
