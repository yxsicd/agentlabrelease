use agentlab_code_analysis::digest;
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

#[test]
fn first_four_catalog_partitions_every_tracked_file_into_maintainer_scope_skills() {
    let directory = root().join("examples/maintainer-knowledge-gate/first-four");
    let catalog_bytes = fs::read(directory.join("maintainer_scope_skills.jsonl")).unwrap();
    let summary: Value =
        serde_json::from_slice(&fs::read(directory.join("maintainer-skill-summary.json")).unwrap())
            .unwrap();
    assert_eq!(
        summary["schema"],
        "agentlab.maintainer_skill_catalog_summary.v1"
    );
    assert_eq!(summary["catalogSha256"], digest(&catalog_bytes));
    assert_eq!(summary["repositoryCount"], 4);
    assert_eq!(summary["scopeSkillCount"], 489);
    assert_eq!(summary["trackedFilesAssignedExactlyOnce"], true);
    assert_eq!(summary["automaticPromotion"], false);

    let expected = BTreeMap::from([
        ("code-workshop", (1512u64, 25u64)),
        ("guide-snippets", (39298, 416)),
        ("harmony-iap-client", (44, 14)),
        ("hms-cordova-iap", (3713, 34)),
    ]);
    for repository in summary["repositories"].as_array().unwrap() {
        let id = repository["repositoryId"].as_str().unwrap();
        let (files, scope_skills) = expected[id];
        assert_eq!(repository["trackedFileCount"], files);
        assert_eq!(repository["assignedFileCount"], files);
        assert_eq!(repository["unassignedFileCount"], 0);
        assert_eq!(repository["scopeSkillCount"], scope_skills);
    }
    assert_eq!(summary["repositories"][1]["sampleProjectRootCount"], 410);

    let mut ids = BTreeSet::new();
    let mut file_totals = BTreeMap::<String, u64>::new();
    let mut kind_counts = BTreeMap::<(String, String), usize>::new();
    let mut row_count = 0usize;
    for line in String::from_utf8(catalog_bytes).unwrap().lines() {
        let row: Value = serde_json::from_str(line).unwrap();
        assert_eq!(row["schema"], "agentlab.maintainer_scope_skill.v1");
        assert_eq!(row["skillLayer"], "instance");
        assert_eq!(row["stage"], "repository-scope");
        assert_eq!(row["ownershipPlane"], "target-operations");
        let id = row["id"].as_str().unwrap();
        assert!(ids.insert(id.to_owned()), "duplicate scope Skill {id}");
        assert!(!id.ends_with('-'));
        assert!(row["responsibility"]
            .as_str()
            .is_some_and(|text| !text.is_empty()));
        assert_eq!(row["automaticPromotion"], false);
        let tracked = row["trackedFileCount"].as_u64().unwrap();
        assert!(tracked > 0);
        let language_total: u64 = row["languages"]
            .as_object()
            .unwrap()
            .values()
            .map(|value| value.as_u64().unwrap())
            .sum();
        assert_eq!(language_total, tracked, "{id}");
        let evidence = row["evidence"].as_array().unwrap();
        assert!(!evidence.is_empty());
        for item in evidence {
            let oid = item["gitBlobOid"].as_str().unwrap();
            assert_eq!(oid.len(), 40);
            assert!(oid.bytes().all(|byte| byte.is_ascii_hexdigit()));
        }
        let repository = row["repositoryId"].as_str().unwrap().to_owned();
        *file_totals.entry(repository.clone()).or_default() += tracked;
        *kind_counts
            .entry((repository, row["kind"].as_str().unwrap().to_owned()))
            .or_default() += 1;
        row_count += 1;
    }
    assert_eq!(row_count, 489);
    for (repository, (files, _)) in expected {
        assert_eq!(file_totals[repository], files);
    }
    assert_eq!(
        kind_counts[&("guide-snippets".to_owned(), "sample-project".to_owned())],
        410
    );
    assert_eq!(
        kind_counts[&("harmony-iap-client".to_owned(), "source-unit".to_owned())],
        9
    );
    assert_eq!(
        kind_counts[&("hms-cordova-iap".to_owned(), "plugin".to_owned())],
        23
    );
    assert_eq!(
        kind_counts[&("hms-cordova-iap".to_owned(), "iap-layer".to_owned())],
        9
    );
}
