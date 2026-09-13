//! Prepare deterministic reusable candidate rows; development TableGit is authority.
use agentlab_code_analysis::{analyze, digest};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path, process::Command};
const PIN: &str = "7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6";
const PATHS: [&str; 4] = [
    "common/src/main/ets/storagemanager/PreferenceManager.ets",
    "common/src/main/ets/storagemanager/PreferenceCacheHelper.ets",
    "features/devpractices/src/main/ets/service/SampleService.ets",
    "features/devpractices/src/main/ets/model/SampleModel.ets",
];
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 4 {
        return Err(
            "Usage: agentlab-cache-seed SOURCE BASE_SNAPSHOT RELEASE_REPO FRESH_OUTPUT".into(),
        );
    }
    let output = Path::new(&args[3]);
    fs::create_dir(output)?;
    let id = "case-cache-durability-candidate-v1";
    let mut tables: BTreeMap<String, BTreeMap<String, Value>> = BTreeMap::new();
    for table in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        let raw = fs::read_to_string(Path::new(&args[1]).join(format!("{table}.jsonl")))?;
        let rows: BTreeMap<String, Value> = raw
            .lines()
            .map(|line| {
                let row: Value = serde_json::from_str(line).unwrap();
                (row["id"].as_str().unwrap().to_owned(), row)
            })
            .collect();
        tables.insert(table.into(), rows);
    }
    let mut fact_ids = vec![];
    for path in PATHS {
        let bytes = Command::new("git")
            .args(["-C", &args[0], "show", &format!("{PIN}:{path}")])
            .output()?;
        if !bytes.status.success() {
            return Err("Pinned source unavailable".into());
        }
        let result = analyze(path, &bytes.stdout, PIN)?;
        if result.has_errors {
            return Err("Candidate source syntax errors".into());
        }
        for mut row in result.rows {
            row["assetClass"] = json!("reusable-knowledge");
            let key = row["id"].as_str().unwrap().to_owned();
            fact_ids.push(key.clone());
            tables.get_mut("program_facts").unwrap().insert(key, row);
        }
    }
    fact_ids.sort();
    fact_ids.dedup();
    let stages = [
        ("goal", "agentlab-benchmark-goal", "Test persistence settlement across four modules. Compilation, behavior, budget and recovery are separate outcomes."),
        ("repository-analysis", "agentlab-codebase-analysis", "SampleModel owns fresh-network versus offline-cache policy; SampleService owns page cache keys; PreferenceCacheHelper owns record updates; PreferenceManager owns platform persistence. Preserve surrounding record entries."),
        ("program-analysis", "agentlab-program-analysis", "Trace getSamplePage -> setSamplePageToPreference -> setSubValue -> setValue/saveValue -> Preferences.flush using syntax spans. Calls are syntactic candidates, not compiler-resolved dataflow. Runtime oracle verifies the selected path."),
        ("seed-extraction", "agentlab-seed-extraction", "Derive a two-turn candidate from semantic guidance and pinned structural facts. First fix durable helper/service writes; then await model settlement without turning a failed cache write into stale offline fallback."),
        ("calibration", "agentlab-benchmark-calibration", "Execute submitted modules with network/Preferences seams. Baseline fails, reference passes; lost-flush and lost-model-await must fail. Do not inject reference source into subject runs."),
        ("evaluation", "agentlab-benchmark-operations", "Consume a newly frozen cut only after calibration and complete phone compilation. Preserve inference, tools, filesystem changes and supervisor controls. Candidate is not an active operational seed."),
    ];
    for (stage, method, body) in stages {
        let method_path = format!("skills/{method}/SKILL.md");
        let raw = fs::read(Path::new(&args[2]).join(&method_path))?;
        let revision = Command::new("git")
            .args([
                "-C",
                &args[2],
                "log",
                "-1",
                "--format=%H",
                "--",
                &method_path,
            ])
            .output()?;
        if !revision.status.success() {
            return Err("Method revision unavailable".into());
        }
        let key = format!("skill-{stage}-cache-durability-candidate-v1");
        let row = json!({"id":key,"assetClass":"reusable-knowledge","skillLayer":"instance","role":if stage=="evaluation" {"operations"} else {"maintenance"},"stage":stage,"objectId":id,"caseIds":[id],"sourceRevision":PIN,"methodSkillId":method,"methodRevision":String::from_utf8(revision.stdout)?.trim(),"methodDigest":digest(&raw),"status":"candidate","title":format!("Cache durability / {stage}"),"body":format!("# Cache durability\n\n{body}"),"factIds":fact_ids});
        tables
            .get_mut("maintainer_skills")
            .unwrap()
            .insert(key, row);
    }
    let oracle =
        fs::read(Path::new(&args[2]).join("examples/knowledge-seed/subject/cache-durability.cjs"))?;
    tables.get_mut("evaluation_cases").unwrap().insert(id.into(), json!({"id":id,"kind":"task","assetClass":"reusable-knowledge","status":"candidate","sourceRevision":PIN,"paths":PATHS,"title":"Durable page cache across persistence and model layers","demands":["Make PreferenceCacheHelper.setSubValue and SampleService.setSamplePageToPreference settle only after Preferences.flush. Preserve all existing record entries and cache keys; propagate put/flush/store failures. Keep valid ArkTS and unchanged build configuration.","Preserve durable-write behavior. SampleModel.getSamplePage must await cache write settlement. On cache write failure log it and return fresh network data; only network failure uses offline fallback. Keep valid ArkTS and unchanged build configuration."],"calibrationAdapter":"subject/cache-durability.cjs","oracleDigest":digest(&oracle),"calibrationContract":{"variantExpectations":{"baseline":false,"reference":true,"lost-flush":false,"lost-model-await":false}},"assessmentScope":"Four submitted modules with platform/network seams; page UI and formal SessionFS separate"}));
    let mut counts = BTreeMap::new();
    for (table, rows) in tables {
        let mut bytes = vec![];
        for row in rows.values() {
            serde_json::to_writer(&mut bytes, row)?;
            bytes.push(b'\n');
        }
        fs::write(output.join(format!("{table}.jsonl")), bytes)?;
        counts.insert(table, rows.len());
    }
    println!(
        "{}",
        json!({"schema":"agentlab.cache_seed_preparation.v1","sourceRevision":PIN,"candidateId":id,"candidateFacts":fact_ids.len(),"tables":counts,"frozen":false})
    );
    Ok(())
}
