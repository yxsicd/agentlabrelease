use agentlab_code_analysis::{
    digest,
    maintainer_operation_qualification::{canonical_har, qualify},
};
use flate2::{Compression, GzBuilder};
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};

fn archive(content: &[u8], time: u32, duplicate: bool) -> Vec<u8> {
    let mut builder = tar::Builder::new(Vec::new());
    let mut directory = tar::Header::new_gnu();
    directory.set_size(0);
    directory.set_mode(0o755);
    directory.set_entry_type(tar::EntryType::Directory);
    directory.set_cksum();
    builder
        .append_data(&mut directory, "package/", &[][..])
        .unwrap();
    for _ in 0..if duplicate { 2 } else { 1 } {
        let mut header = tar::Header::new_gnu();
        header.set_size(content.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        builder
            .append_data(&mut header, "package/fixture.txt", content)
            .unwrap();
    }
    let tar = builder.into_inner().unwrap();
    use std::io::Write;
    let mut gz = GzBuilder::new()
        .mtime(time)
        .write(Vec::new(), Compression::default());
    gz.write_all(&tar).unwrap();
    gz.finish().unwrap()
}
fn save(root: &Path, name: &str, value: &Value) -> String {
    let bytes = serde_json::to_vec_pretty(value).unwrap();
    fs::write(root.join(name), &bytes).unwrap();
    digest(&bytes)
}

#[test]
fn capture_qualification_reads_original_bytes_and_rejects_borrowed_or_changed_evidence() {
    let root = std::env::temp_dir().join(format!(
        "agentlab-capture-qualification-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let source = json!({"repositoryId":"arbitrary", "repository":"https://example.invalid/arbitrary.git", "revision":"1".repeat(40)});
    let command = json!({"program":"/reviewed/tool", "programSha256":"2".repeat(64), "args":[], "cwd":".", "timeoutMs":1000});
    let mut build = command.clone();
    build["args"] = json!(["clean", "assembleHar"]);
    let recipe = json!({"schema":"agentlab.maintainer_build_operation_recipe.v1", "source":source, "scopeSkillId":"scope-alpha", "lane":"build-only", "cleanBuild":true,
        "automaticPromotion":false,"probes":[command],"dependencyPreparation":command,"build":build,
        "artifact":"arbitrary-module/output.har"});
    let before = json!({"schema":"agentlab.maintainer_skill_assessment.v1"});
    let plan = json!({"schema":"agentlab.maintainer_flywheel_next_plan.v1", "assessment":before,
        "decision":"propose-next-batch", "automaticPromotion":false, "authorityWritePerformed":false, "closedLoopQualified":false,
        "nextLane":"operation-verification", "selectedScopeIds":["scope-alpha"], "policy":{"availableOperationKinds":["build-only"]},
        "scopes":[{"skillId":"scope-alpha", "selected":true, "operationKind":"build-only", "repositoryId":source["repositoryId"],
            "repository":source["repository"], "sourceRevision":source["revision"], "pathBoundary":"arbitrary-module",
            "ownershipSelectors":[{"type":"files", "paths":["arbitrary-module/build.config"]}]}]});
    let mut captures = Vec::new();
    for (index, label) in ["probe-0", "dependency", "build-1", "build-2"]
        .iter()
        .enumerate()
    {
        let mut record = json!({"label":label, "command":if index < 2 {&command} else {&build}, "pid":100+index,
            "status":"successful", "termination":"completed", "exitCode":0, "durationMs":1});
        for stream in ["stdout", "stderr"] {
            let name = format!("{label}.{stream}");
            fs::write(root.join(&name), b"retained\n").unwrap();
            record[stream] =
                json!({"path":name, "complete":true, "bytes":9, "sha256":digest(b"retained\n")});
        }
        captures.push(record);
    }
    let mut artifacts = Vec::new();
    for index in 1..=2 {
        let bytes = archive(b"stable-member", index, false);
        let name = format!("attempt-{index}.artifact");
        fs::write(root.join(&name), &bytes).unwrap();
        artifacts.push(json!({"attempt":index,"retainedPath":name,"sourcePath":recipe["artifact"],"bytes":bytes.len(),"sha256":digest(&bytes)}));
    }
    let original = json!({"schema":"agentlab.maintainer_operation_execution.v1", "status":"successful", "qualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false,"sourceCleanAfter":true,"source":source,"scopeSkillId":"scope-alpha",
        "recipeSha256":save(&root,"input-recipe.json",&recipe),"selectionPlanSha256":save(&root,"input-plan.json",&plan),
        "beforeAssessmentSha256":save(&root,"input-before.json",&before),"captures":captures,"artifacts":artifacts});
    let sha = save(&root, "execution-receipt.json", &original);
    let result = qualify(&root, &sha, "arbitrary-module").unwrap();
    assert_eq!(result["status"], "qualified");
    assert_eq!(result["rawArchiveReproducible"], false);
    assert_eq!(result["artifacts"][0]["canonical"]["memberCount"], 2);
    assert_eq!(result["qualificationScope"]["runtime"], false);
    let output_path = root.join("qualified.json");
    let invoke = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--qualify-operation-capture",
                "--execution-root",
                root.to_str().unwrap(),
                "--execution-receipt-sha256",
                &sha,
                "--module-root",
                "arbitrary-module",
                "--output",
                output_path.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let first = invoke();
    assert!(first.status.success(), "{:?}", first);
    let qualified_bytes = fs::read(&output_path).unwrap();
    assert_eq!(
        serde_json::from_slice::<Value>(&qualified_bytes).unwrap(),
        result
    );
    assert!(!invoke().status.success());
    assert_eq!(fs::read(&output_path).unwrap(), qualified_bytes);
    assert!(qualify(&root, &sha, "sibling-module").is_err());
    assert!(qualify(&root, &"0".repeat(64), "arbitrary-module").is_err());
    fs::write(root.join("build-1.stderr"), "tampered").unwrap();
    assert!(qualify(&root, &sha, "arbitrary-module").is_err());
    fs::write(root.join("build-1.stderr"), b"retained\n").unwrap();
    for mutation in 0..3 {
        let mut bad = original.clone();
        match mutation {
            0 => bad["captures"][2]["exitCode"] = json!(7),
            1 => bad["captures"][2]["pid"] = bad["captures"][3]["pid"].clone(),
            _ => bad["captures"][2]["stdout"]["complete"] = json!(false),
        }
        let sha = save(&root, "execution-receipt.json", &bad);
        assert!(qualify(&root, &sha, "arbitrary-module").is_err());
    }
    let sha = save(&root, "execution-receipt.json", &original);
    fs::write(root.join("attempt-2.artifact"), b"changed").unwrap();
    assert!(qualify(&root, &sha, "arbitrary-module").is_err());
    assert!(canonical_har(&archive(b"stable-member", 1, true)).is_err());
    let mut trailing = archive(b"stable-member", 1, false);
    trailing.extend_from_slice(b"unexamined-payload");
    assert!(canonical_har(&trailing).is_err());
    assert_ne!(
        canonical_har(&archive(b"first", 1, false)).unwrap(),
        canonical_har(&archive(b"second", 1, false)).unwrap()
    );
    fs::remove_dir_all(root).unwrap();
}
