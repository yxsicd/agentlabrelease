use agentlab_code_analysis::{digest, maintainer_guidance::bind};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: PathBuf,
    selection: Value,
}
impl Fixture {
    fn new(repo: &str) -> Self {
        let root = std::env::temp_dir().join(format!(
            "agentlab-guidance-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let source = "a".repeat(40);
        let lineage = json!({"repository":"operations-repo","revision":"c".repeat(40),"lessonId":"lesson-mechanism","tablePrefix":"data/","lessonFileDigest":"d".repeat(64)});
        let provenance = json!({"repositoryId":repo,"sourceRevision":source,"methodRevision":"b".repeat(40),
            "methodDigest":"e".repeat(64),"sourceLessonId":"lesson-mechanism","sourceLessonExportDigest":"d".repeat(64),"lessonSource":lineage});
        let mut skill = provenance.clone();
        for (key, value) in json!({"id":"reviewed-method","body":"Observe every declared phase and require intended wrong variants to fail; startup alone is not configuration delivery.",
            "role":"maintenance","stage":"calibration","objectId":"lesson-mechanism","factIds":["reviewed-fact"],
            "ownershipPlane":"target-operations","automaticPromotion":false}).as_object().unwrap() {
            skill[key] = value.clone();
        }
        let mut fact = provenance;
        fact["id"] = json!("reviewed-fact");
        fact["qualification"] = json!({"caseQualified":false,"harmonyRuntimeQualified":false});
        let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1","automaticPromotion":false,
            "tableGitAuthority":{"repo":"knowledge-repo","revision":"f".repeat(40)},
            "repositories":[{"id":repo,"revision":source}],"tables":{}});
        for (name, file, rows) in [
            (
                "maintainerSkills",
                "maintainer_skills.jsonl",
                vec![skill.clone()],
            ),
            ("programFacts", "program_facts.jsonl", vec![fact]),
            (
                "maintainerScopeSkills",
                "maintainer_scope_skills.jsonl",
                vec![],
            ),
            (
                "maintainerSkillRefreshRounds",
                "maintainer_skill_refresh_rounds.jsonl",
                vec![],
            ),
            ("evaluationCases", "evaluation_cases.jsonl", vec![]),
        ] {
            let bytes: Vec<u8> = rows
                .iter()
                .flat_map(|r| {
                    let mut b = serde_json::to_vec(r).unwrap();
                    b.push(b'\n');
                    b
                })
                .collect();
            fs::write(root.join(file), &bytes).unwrap();
            cut["tables"][name] = json!({"path":file,"sha256":digest(&bytes)});
        }
        let cut_bytes = serde_json::to_vec(&cut).unwrap();
        fs::write(root.join("maintainer-knowledge-cut.json"), &cut_bytes).unwrap();
        let selection = json!({"schema":"agentlab.maintainer_guidance_selection.v1","automaticPromotion":false,
            "knowledgeCutSha256":digest(&cut_bytes),"knowledgeRevision":"f".repeat(40),"stage":"calibration",
            "sources":[{"repositoryId":repo,"sourceRevision":source}],
            "skills":[{"id":"reviewed-method","objectId":"lesson-mechanism","rowSha256":digest(&serde_json::to_vec(&skill).unwrap()),
                "applicabilityReason":"The selected task exercises the same declared configuration lifecycle mechanism."}]});
        Self { root, selection }
    }
    fn bind(&self, selection: &Value) -> Result<Value, String> {
        bind(&self.root, &serde_json::to_vec(selection).unwrap())
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn explicit_guidance_rejects_stage_source_row_object_and_cut_drift() {
    let f = Fixture::new("arbitrary-repo-one");
    let packet = f.bind(&f.selection).unwrap();
    assert_eq!(
        packet["guidance"][0]["facts"][0]["qualification"]["caseQualified"],
        false
    );
    assert_eq!(packet["agentConsumptionVerified"], false);
    assert_eq!(packet["learningBenefitVerified"], false);
    assert_eq!(packet["remoteCommitAuthenticated"], false);
    assert_eq!(packet, f.bind(&f.selection).unwrap());
    for (pointer, value) in [
        ("/stage", json!("semantic-analysis")),
        ("/sources/0/sourceRevision", json!("0".repeat(40))),
        ("/sources/0/repositoryId", json!("different-repo")),
        ("/skills/0/rowSha256", json!("0".repeat(64))),
        ("/skills/0/objectId", json!("unrelated-mechanism")),
        ("/skills/0/applicabilityReason", json!("")),
        ("/knowledgeRevision", json!("0".repeat(40))),
        ("/knowledgeCutSha256", json!("0".repeat(64))),
        ("/automaticPromotion", json!(true)),
    ] {
        let mut bad = f.selection.clone();
        *bad.pointer_mut(pointer).unwrap() = value;
        assert!(f.bind(&bad).is_err(), "accepted changed {pointer}");
    }
    let mut bad = f.selection.clone();
    bad["skills"]
        .as_array_mut()
        .unwrap()
        .push(f.selection["skills"][0].clone());
    assert!(f.bind(&bad).is_err());
    fs::write(f.root.join("evaluation_cases.jsonl"), b"{}\n").unwrap();
    assert!(f.bind(&f.selection).is_err());
}

#[test]
fn actual_cli_and_author_prompt_preserve_body_provenance_and_limits_for_two_identities() {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    for repo in ["arbitrary-repo-one", "arbitrary-repo-two"] {
        let f = Fixture::new(repo);
        let input = f.root.join("selection.json");
        let output = f.root.join("packet.json");
        fs::write(&input, serde_json::to_vec(&f.selection).unwrap()).unwrap();
        let command = || {
            Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
                .args(["--bind-maintainer-guidance", "--knowledge"])
                .arg(&f.root)
                .arg("--guidance-request")
                .arg(&input)
                .arg("--output")
                .arg(&output)
                .output()
                .unwrap()
        };
        assert!(command().status.success());
        let bytes = fs::read(&output).unwrap();
        assert!(!command().status.success());
        assert_eq!(fs::read(&output).unwrap(), bytes);
        let packet: Value = serde_json::from_slice(&bytes).unwrap();
        let request = json!({"sources":[{"repositoryId":repo,"revision":"a".repeat(40)}],"maintainerGuidance":packet});
        let request_path = f.root.join("author-request.json");
        fs::write(&request_path, serde_json::to_vec(&request).unwrap()).unwrap();
        let code = "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('a',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.guidance_prompt(json.load(open(sys.argv[2]))))";
        let prompt = Command::new("python3")
            .arg("-c")
            .arg(code)
            .arg(repo_root.join("examples/multi-repo-case/pi-calibration-author.py"))
            .arg(&request_path)
            .output()
            .unwrap();
        assert!(
            prompt.status.success(),
            "{}",
            String::from_utf8_lossy(&prompt.stderr)
        );
        let prompt = String::from_utf8(prompt.stdout).unwrap();
        assert!(prompt.contains(
            request["maintainerGuidance"]["guidance"][0]["skill"]["body"]
                .as_str()
                .unwrap()
        ));
        assert!(prompt.contains("operations-repo"));
        assert!(prompt.contains("caseQualified\": false"));
        // Prompt assembly is not proof that a real Agent received or learned it.
        let mut forged = request.clone();
        forged["maintainerGuidance"]["guidance"][0]["skill"]["body"] = json!("forged body");
        fs::write(&request_path, serde_json::to_vec(&forged).unwrap()).unwrap();
        let rejected = Command::new("python3")
            .arg("-c")
            .arg(code)
            .arg(repo_root.join("examples/multi-repo-case/pi-calibration-author.py"))
            .arg(&request_path)
            .output()
            .unwrap();
        assert!(!rejected.status.success());
    }
}

#[test]
fn actual_authoring_producer_binds_complete_inputs_and_refuses_unrelated_sources() {
    let f = Fixture::new("arbitrary-author-source");
    let selection = f.root.join("selection.json");
    fs::write(&selection, serde_json::to_vec(&f.selection).unwrap()).unwrap();
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    let code = r#"
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(sys.argv[1]).parent))
s=importlib.util.spec_from_file_location('author',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=Path(sys.argv[2]);workspace=root/'producer-workspace';workspace.mkdir()
args=SimpleNamespace(guidance_knowledge=root,guidance_selection=root/'selection.json',flywheel_tool=Path(sys.argv[3]))
rows=[{'repositoryId':'arbitrary-author-source','revision':'a'*40}]
packet=m.bind_guidance(args,rows,workspace)
assert packet['guidance'][0]['skill']['body']
assert packet['agentConsumptionVerified'] is False
assert (workspace/'guidance-knowledge'/'maintainer_skills.jsonl').read_bytes()==(root/'maintainer_skills.jsonl').read_bytes()
try:m.bind_guidance(args,[{'repositoryId':'unrelated','revision':'a'*40}],workspace)
except m.AuthoringError:pass
else:raise AssertionError('unrelated authoring source accepted')
args.flywheel_tool=None
try:m.bind_guidance(args,rows,workspace)
except m.AuthoringError:pass
else:raise AssertionError('incomplete authority inputs accepted')
print('real Rust producer binding and source rejection passed; no model execution')
"#;
    let result = Command::new("python3")
        .arg("-c")
        .arg(code)
        .arg(root.join("scripts/run-multi-repo-calibration-authoring.py"))
        .arg(&f.root)
        .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn guided_authoring_pipeline_rebinds_retained_cut_and_rejects_tampering() {
    let f = Fixture::new("contracts");
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    let code = r#"
import importlib.util,json,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
repo=Path(sys.argv[1]);root=Path(sys.argv[2]);tool=Path(sys.argv[3])
sys.path.insert(0,str(repo/'scripts'))
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
test=module('fixtures',repo/'tests/test_multi_repo_calibration_authoring.py')
fixture=root/'multi';fixture.mkdir()
selection,difficulty,manifest,facts=test.MultiRepoCalibrationAuthoringTests().fixture(fixture)
revision=next(r['revision'] for r in json.load(open(manifest))['repositories'] if r['id']=='contracts')
cut=json.load(open(root/'maintainer-knowledge-cut.json'))
for name,file in [('maintainerSkills','maintainer_skills.jsonl'),('programFacts','program_facts.jsonl')]:
 row=json.loads((root/file).read_text());row['sourceRevision']=revision
 raw=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode();(root/file).write_bytes(raw)
 cut['tables'][name]['sha256']=hashlib.sha256(raw).hexdigest()
cut['repositories'][0]['revision']=revision
cutbytes=json.dumps(cut,sort_keys=True,separators=(',',':')).encode();(root/'maintainer-knowledge-cut.json').write_bytes(cutbytes)
skill=json.loads((root/'maintainer_skills.jsonl').read_text())
request={'schema':'agentlab.maintainer_guidance_selection.v1','automaticPromotion':False,
 'knowledgeCutSha256':hashlib.sha256(cutbytes).hexdigest(),'knowledgeRevision':'f'*40,'stage':'calibration',
 'sources':[{'repositoryId':'contracts','sourceRevision':revision}],
 'skills':[{'id':'reviewed-method','objectId':'lesson-mechanism','rowSha256':hashlib.sha256(json.dumps(skill,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'applicabilityReason':'Explicit test applicability; not real cross-repository acceptance.'}]}
(root/'guidance-selection.json').write_text(json.dumps(request))
m=module('author',repo/'scripts/run-multi-repo-calibration-authoring.py')
args=SimpleNamespace(selection=selection,difficulty=difficulty,manifest=manifest,facts=facts,
 participant=repo/'examples/multi-repo-case/mock-calibration-author.py',participant_id='mock-guided-control',
 method_revision='d'*40,output=root/'guided-output',guidance_knowledge=root,
 guidance_selection=root/'guidance-selection.json',flywheel_tool=tool,
 localization=None,localization_proposal=None,localization_review=None,semantic_packet=None,semantic_decision=None,semantic_gate=None)
receipt=m.run(args);assert receipt['status']=='review-required'
assert m.validate_output(args.output,tool)==receipt
try:m.validate_output(args.output)
except m.AuthoringError:pass
else:raise AssertionError('guided verification accepted without Rust rebinding')
(args.output/'workspace/guidance-knowledge/program_facts.jsonl').write_text('{}\n')
try:m.validate_output(args.output,tool)
except m.AuthoringError:pass
else:raise AssertionError('retained fact tampering accepted')
print('full guided mock pipeline and independent rejection passed; no real model or generalization claim')
"#;
    let result = Command::new("python3")
        .arg("-c")
        .arg(code)
        .arg(&root)
        .arg(&f.root)
        .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
