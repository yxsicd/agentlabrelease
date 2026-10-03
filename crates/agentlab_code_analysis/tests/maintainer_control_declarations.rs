use agentlab_code_analysis::{digest, maintainer_control_declarations::reconcile};
use serde_json::{json, Value};
fn bytes(v: &Value) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn fixture() -> (Value, Value) {
    let source = json!({"repositoryId":"unrelated-repository","repository":"https://example.invalid/arbitrary.git","revision":"a".repeat(40)});
    let scope = json!({"id":"owner","repositoryId":source["repositoryId"],"repository":source["repository"],
        "sourceRevision":source["revision"],"pathBoundary":"src","sourceFileCount":1,"buildEntrypoints":[],"testFileCount":0,"testEntrypoints":[]});
    let definitions = [
        ("initial", "baseline", "A", vec![]),
        ("valid", "reference", "B", vec![]),
        ("wrong", "wrong", "C", vec!["first", "second"]),
    ];
    let controls=definitions.iter().map(|(id,role,_,failed)| json!({"id":id,"role":role,
        "command":{"program":"/fixture/node","programSha256":"b".repeat(64),"args":[id],"cwd":".","timeoutMs":1000},
        "expectedFailedCheckIds":failed})).collect::<Vec<_>>();
    let recipe = json!({"schema":"agentlab.maintainer_source_operation_recipe.v1","reviewed":true,"automaticPromotion":false,
        "operationKind":"source-only","scopeSkillId":"owner","source":source,
        "sourceInputs":[{"path":"src/state","sha256":digest(b"A"),"gitBlobOid":"c".repeat(40)}],
        "methodInputs":[{"path":"/fixture/method.cjs","sha256":"d".repeat(64)}],
        "checks":[{"id":"first","pointer":"/value","expected":1},{"id":"second","pointer":"/value","expected":1}],"controls":controls});
    let streams=definitions.iter().map(|(id,role,variant,_)| {
        let raw=json!({"id":id,"sourceSha256":digest(b"A"),"submittedSourceSha256":digest(variant.as_bytes()),"value":if *role=="wrong" {0} else {1}});
        json!({"stdout":String::from_utf8(bytes(&raw)).unwrap(),"stderr":""})
    }).collect::<Vec<_>>();
    let captures=controls.iter().zip(&streams).enumerate().map(|(i,(c,s))| {
        let mut v=json!({"label":c["id"],"command":c["command"],"status":"successful","termination":"completed",
            "exitCode":0,"durationMs":1,"pid":i+1});
        for name in ["stdout","stderr"] {
            let raw=s[name].as_str().unwrap().as_bytes();
            v[name]=json!({"path":format!("{}.{}",c["id"].as_str().unwrap(),name),"bytes":raw.len(),"sha256":digest(raw),"complete":true});
        }
        v
    }).collect::<Vec<_>>();
    let execution = json!({"schema":"agentlab.maintainer_source_operation_execution.v1","status":"successful","qualified":false,
        "automaticPromotion":false,"authorityWritePerformed":false,"source":source,"scopeSkillId":"owner",
        "recipeSha256":digest(&bytes(&recipe)),"scopeSha256":digest(&bytes(&scope)),"beforeAssessmentSha256":"e".repeat(64),"captures":captures});
    let reference = json!({"schema":"agentlab.maintainer_scope_source_qualification.v1","status":"qualified","automaticPromotion":false,
        "authorityWritePerformed":false,"source":source,"scopeSkillId":"owner","recipe":recipe,"recipeOriginal":String::from_utf8(bytes(&recipe)).unwrap(),
        "scopeOriginal":String::from_utf8(bytes(&scope)).unwrap(),"execution":execution,"executionOriginal":String::from_utf8(bytes(&execution)).unwrap(),
        "executionReceiptSha256":digest(&bytes(&execution)),"streams":streams,
        "qualificationScope":{"sourceMaintenance":true,"build":false,"runtime":false,"tests":false,"performance":false},"verificationBoundary":"Synthetic recorded-content fixture, not authentic execution."});
    let profile = json!({"schema":"agentlab.reviewed_behavior_profile.v1","reviewed":true,"automaticPromotion":false,
        "candidateId":"arbitrary-task","repository":source["repository"],"sourceRevision":source["revision"],"originalSourcePath":"src/state",
        "sources":[{"path":"src/state","sha256":digest(b"A")}],
        "checks":[{"id":"first","input":null,"expected":1},{"id":"second","input":{"x":2},"expected":1}],
        "controls":[{"id":"initial","role":"baseline","edits":[],"expectedFailedCheckIds":[]},
            {"id":"valid","role":"accepted","edits":[{"from":"A","to":"B"}],"expectedFailedCheckIds":[]},
            {"id":"wrong","role":"wrong","edits":[{"from":"A","to":"C"}],"expectedFailedCheckIds":["first"]}]});
    (profile, reference)
}

#[test]
fn reconstructs_prior_declarations_without_inventing_review_or_changing_predicates() {
    let (profile, reference) = fixture();
    let result = reconcile(&bytes(&profile), &bytes(&reference), b"A").unwrap();
    assert_eq!(result["corrections"].as_array().unwrap().len(), 1);
    assert_eq!(
        result["proposedProfile"]["controls"][2]["expectedFailedCheckIds"],
        json!(["first", "second"])
    );
    assert_eq!(result["proposedProfile"]["checks"], profile["checks"]);
    assert_eq!(result["proposedProfile"]["reviewed"], false);
    assert_eq!(result["qualified"], false);
    assert_eq!(result["executionPerformed"], false);
    assert_eq!(
        result,
        reconcile(&bytes(&profile), &bytes(&reference), b"A").unwrap()
    );
}

#[test]
fn borrowed_variant_role_predicate_and_corrupt_original_bytes_never_reconcile() {
    let (profile, reference) = fixture();
    for changed in [
        "source",
        "role",
        "expected",
        "missing",
        "variant",
        "duplicate",
    ] {
        let mut p = profile.clone();
        match changed {
            "source" => p["sourceRevision"] = json!("b".repeat(40)),
            "role" => p["controls"][2]["role"] = json!("accepted"),
            "expected" => p["checks"][1]["expected"] = json!(2),
            "missing" => {
                p["controls"].as_array_mut().unwrap().pop();
            }
            "variant" => p["controls"][2]["edits"][0]["to"] = json!("D"),
            _ => p["checks"][1]["id"] = json!("first"),
        }
        assert!(
            reconcile(&bytes(&p), &bytes(&reference), b"A").is_err(),
            "{changed}"
        );
    }
    let mut r = reference.clone();
    r["recipeOriginal"] = json!("{}");
    assert!(reconcile(&bytes(&profile), &bytes(&r), b"A").is_err());
    assert!(reconcile(&bytes(&profile), &bytes(&reference), b"changed").is_err());
}

#[test]
fn public_validator_binds_parent_and_rejects_unchanged_value_with_changed_input() {
    use std::{fs, process::Command};
    let (parent, reference) = fixture();
    let parent_bytes = bytes(&parent);
    let reference_bytes = bytes(&reference);
    let draft = reconcile(&parent_bytes, &reference_bytes, b"A").unwrap();
    let mut profile = draft["proposedProfile"].clone();
    profile["reviewed"] = json!(true);
    profile["controlDeclarationReference"] =
        json!({"sha256":digest(&reference_bytes),"parentProfile":{"sha256":digest(&parent_bytes)}});
    let root = std::env::temp_dir().join(format!(
        "agentlab-control-reference-cli-{}",
        std::process::id()
    ));
    fs::create_dir(&root).unwrap();
    for (name, body) in [
        ("parent.json", parent_bytes),
        ("reference.json", reference_bytes),
        ("source", b"A".to_vec()),
    ] {
        fs::write(root.join(name), body).unwrap();
    }
    for (index, damage) in ["none", "input", "candidate", "parent"].iter().enumerate() {
        let mut proposed = profile.clone();
        match *damage {
            "input" => proposed["checks"][1]["input"] = json!({"x":99}),
            "candidate" => proposed["candidateId"] = json!("borrowed"),
            "parent" => {
                proposed["controlDeclarationReference"]["parentProfile"]["sha256"] =
                    json!("0".repeat(64))
            }
            _ => {}
        }
        fs::write(root.join("profile.json"), bytes(&proposed)).unwrap();
        let output_path = root.join(format!("out-{index}.json"));
        let run = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--validate-control-declaration-reference")
            .args(["--profile", root.join("profile.json").to_str().unwrap()])
            .args([
                "--parent-profile",
                root.join("parent.json").to_str().unwrap(),
            ])
            .args([
                "--control-reference",
                root.join("reference.json").to_str().unwrap(),
            ])
            .args(["--source-bytes", root.join("source").to_str().unwrap()])
            .args(["--output", output_path.to_str().unwrap()])
            .output()
            .unwrap();
        assert_eq!(
            run.status.success(),
            *damage == "none",
            "{}",
            String::from_utf8_lossy(&run.stderr)
        );
        assert_eq!(output_path.exists(), *damage == "none");
    }
    fs::remove_dir_all(root).unwrap();
}
