//! Evidence-linked experience construction and explicit reusable promotion.
mod asset_exchange;
use asset_exchange::*;
use serde_json::{json, Value};
use std::{fs, path::Path};

fn load(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}
fn contract(scenario: &str) -> Value {
    let (id, scope, phenomenon, cause, change, fact, skill, body, expected, qualification) = match scenario {
        "loading" => ("loading-reappearance-cancels-old-timer", "isolated-loading-lifecycle", "Repeated appearance can leave an old timer and stale visibility", "Scheduling a new timer without cancelling the previous one retains pending work", "Cancel the previous timer and reset visibility before scheduling on appearance", "lesson-loading-lifecycle", "skill-loading-lifecycle-method", "Test repeated appearance, cancellation, visibility reset and breakpoint delay with an independently controlled scheduler. Require the reference to pass and an omitted-cancellation variant to fail. Cancel old pending work before replacing its handle. This evidence covers an isolated lifecycle seam; qualify HAP and UI separately.", json!({"baseline":false,"reference":true,"wrong-cancel":false}), "isolated timer/breakpoint scheduler; not HAP or UI"),
        "debounce" => ("independent-click-accepted-window", "actual-click-clock-seam", "Independent click handlers interfere and suppressed clicks can postpone acceptance", "A shared timestamp mixes handlers and updating it on suppression extends the window", "Own the accepted-click timestamp per closure and update it only after acceptance", "lesson-independent-click-window", "skill-independent-click-window-method", "Execute actual utility and component click bodies with controlled time. Test first call at zero, independent handlers, exact/default wait, unchanged accepted-click windows and actual event payload forwarding. Require boundary and window-extension negatives to fail. Qualify full builds and UI separately.", json!({"baseline":false,"reference":true,"wrong-boundary":false,"wrong-window":false}), "actual utility/click methods with modeled Date/event sink; not UI"),
        "image-url" => ("shared-image-url-resource-routing", "actual-image-url-resource-seam", "Malformed HTTP prefixes can be misclassified as network image resources", "Protocol-prefix classification ignores valid authorities and shared resource dispatch", "Validate HTTP/S URL authorities and preserve shared predicate resource routing", "lesson-shared-image-url-routing", "skill-shared-image-url-routing-method", "Execute actual URL predicate and ImageUtil resource method against independently labeled fixtures. Preserve query/fragment network strings and local/empty routing. Require protocol and stale-resource-dispatch negatives to fail. Node URL models the platform seam; qualify Harmony parser and UI separately.", json!({"baseline":false,"reference":true,"wrong-protocol":false,"wrong-dispatch":false}), "actual predicate/resource method with modeled platform parser/resources; not platform parser or UI"),
        _ => panic!("No owned lesson contract for this scenario"),
    };
    json!({"id":id,"scope":scope,"phenomenon":phenomenon,"cause":cause,"change":change,"factId":fact,"skillId":skill,"body":body,"expected":expected,"qualification":qualification})
}
fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.get(1).map(String::as_str) == Some("contract") {
        println!("{}", contract(&a[2]));
        return;
    }
    assert!(a.len() >= 6, "observe INSTANCE ANALYSIS CALIBRATION OUTPUT | promote EXPERIENCE KNOWLEDGE OUTPUT LESSON_ID");
    let mut t = Tables::new();
    if a[1] == "calibrate" {
        let source = Path::new(&a[2]);
        let provenance = load(Path::new(&a[3]));
        let oracle = Path::new(&a[4]);
        let output = Path::new(&a[5]);
        fs::create_dir(output).unwrap();
        let source_bytes = fs::read(source).unwrap();
        assert_eq!(hash(&source_bytes), provenance["sha256"]);
        fs::write(output.join("source.ets"), source_bytes).unwrap();
        let mut variants = serde_json::Map::new();
        for variant in ["baseline", "reference", "wrong-cancel"] {
            let reply = std::process::Command::new("node")
                .args([
                    oracle.as_os_str(),
                    source.as_os_str(),
                    std::ffi::OsStr::new(variant),
                ])
                .output()
                .unwrap();
            fs::write(output.join(format!("{variant}.stdout.json")), &reply.stdout).unwrap();
            fs::write(output.join(format!("{variant}.stderr.log")), &reply.stderr).unwrap();
            assert!(
                reply.status.success(),
                "Preserved oracle infrastructure failure"
            );
            variants.insert(
                variant.into(),
                serde_json::from_slice(&reply.stdout).unwrap(),
            );
        }
        let receipt = json!({"sourceRevision":provenance["sourceRevision"],"sourcePath":provenance["path"],"sourceDigest":provenance["sha256"],"oracleDigest":hash(&fs::read(oracle).unwrap()),"variants":variants,"scope":"isolated-loading-lifecycle","lesson":contract("loading"),"harmonyBuildQualified":false,"uiQualified":false});
        fs::write(
            output.join("calibration.json"),
            serde_json::to_vec_pretty(&receipt).unwrap(),
        )
        .unwrap();
        assert!(
            receipt["variants"]["baseline"]["pass"] == false
                && receipt["variants"]["reference"]["pass"] == true
                && receipt["variants"]["wrong-cancel"]["pass"] == false,
            "Preserved calibration rejection"
        );
        println!("{}", receipt);
    } else if a[1] == "observe" {
        let instance = Path::new(&a[2]);
        let analysis = load(Path::new(&a[3]));
        let calibration = load(Path::new(&a[4]));
        let analysis_id = hash(&serde_json::to_vec(&analysis).unwrap());
        put(
            &mut t,
            "analysis_records",
            json!({"id":analysis_id,"assetClass":"evaluation-instance","kind":"tool-error-query","inputRevision":analysis["request"]["bindings"][0]["revision"],"request":analysis["request"],"result":analysis["result"]}),
        );
        t.entry("experiment_lessons".into()).or_default();
        t.entry("lesson_validations".into()).or_default();
        t.entry("lesson_evidence".into()).or_default();
        if analysis["outcomeRequest"].is_object() {
            let outcome_id = hash(&serde_json::to_vec(&analysis["outcomeRequest"]).unwrap());
            put(
                &mut t,
                "analysis_records",
                json!({"id":outcome_id,"assetClass":"evaluation-instance","kind":"failed-check-query","inputRevision":analysis["outcomeRequest"]["bindings"][0]["revision"],"request":analysis["outcomeRequest"],"result":analysis["outcomeResult"]}),
            );
            for check in rows(&instance.join("checks.jsonl")) {
                if check["passed"] != false {
                    continue;
                }
                let id = format!("failed-check-{}", check["id"].as_str().unwrap());
                let evidence = format!("{id}-observation");
                put(
                    &mut t,
                    "experiment_lessons",
                    json!({"id":id,"assetClass":"evaluation-instance","kind":"assessed-check-failure","status":"observed","runId":check["runId"],"phaseId":check["phaseId"],"checkId":check["id"],"phenomenon":check["check"],"scope":"one-submitted-code-check","attribution":"assessed-source-outcome","analysisId":outcome_id,"evidenceIds":[evidence],"validationIds":[],"targetIds":[]}),
                );
                put(
                    &mut t,
                    "lesson_evidence",
                    json!({"id":evidence,"assetClass":"evaluation-instance","lessonId":id,"kind":"independent-check-failure","authority":"operator-owned-oracle","sourceTable":"checks","sourceRowId":check["id"],"inputRevision":analysis["outcomeRequest"]["bindings"][0]["revision"],"record":check}),
                );
            }
        }
        for call in rows(&instance.join("tool_calls.jsonl")) {
            if call["isError"] != true {
                continue;
            }
            let id = format!("tool-error-{}", call["id"].as_str().unwrap());
            let evidence = format!("{id}-observation");
            put(
                &mut t,
                "experiment_lessons",
                json!({"id":id,"assetClass":"evaluation-instance","kind":"tool-error-observation","runId":call["runId"],"phaseId":call["phaseId"],"status":"observed","scope":"one-tool-execution","phenomenon":"Adapter reported a tool error; cause and corrective action are not inferred","attribution":"unknown","toolCallId":call["id"],"analysisId":analysis_id,"evidenceIds":[evidence],"validationIds":[],"targetIds":[]}),
            );
            put(
                &mut t,
                "lesson_evidence",
                json!({"id":evidence,"assetClass":"evaluation-instance","lessonId":id,"kind":"adapter-tool-error","authority":call["authority"],"sourceTable":"tool_calls","sourceRowId":call["id"],"inputRevision":analysis["request"]["bindings"][0]["revision"],"record":call}),
            );
        }
        let lesson = &calibration["lesson"];
        let id = lesson["id"]
            .as_str()
            .expect("Owned calibration lesson contract");
        let evidence_id = format!("{id}-calibration");
        let analysis_id = format!("{id}-variant-comparison");
        let validation_id = format!("{id}-variants");
        let passed = lesson["expected"]
            .as_object()
            .unwrap()
            .iter()
            .all(|(name, expected)| {
                calibration["variants"][name]["pass"] == *expected
                    && calibration["variants"][name]["error"].is_null()
            });
        put(
            &mut t,
            "analysis_records",
            json!({"id":analysis_id,"assetClass":"evaluation-instance","kind":"calibration-comparison","code":"Every declared variant pass equals its frozen expected value; no oracle infrastructure error","expected":lesson["expected"],"sourceRevision":calibration["sourceRevision"],"sourceDigest":calibration["sourceDigest"],"oracleDigest":calibration["oracleDigest"],"result":{"passed":passed},"evidenceIds":[evidence_id]}),
        );
        put(
            &mut t,
            "experiment_lessons",
            json!({"id":id,"assetClass":"evaluation-instance","kind":"calibrated-method-lesson","status":if passed {"verified"} else {"rejected"},"scope":lesson["scope"],"phenomenon":lesson["phenomenon"],"attribution":"independent-variant-comparison","cause":lesson["cause"],"change":lesson["change"],"analysisId":analysis_id,"sourceRevision":calibration["sourceRevision"],"evidenceIds":[evidence_id],"validationIds":[validation_id],"targetIds":[lesson["factId"],lesson["skillId"]],"promotionContract":lesson}),
        );
        put(
            &mut t,
            "lesson_evidence",
            json!({"id":evidence_id,"assetClass":"evaluation-instance","lessonId":id,"kind":"executed-calibration","authority":"operator-owned-oracle","record":calibration}),
        );
        put(
            &mut t,
            "lesson_validations",
            json!({"id":validation_id,"assetClass":"evaluation-instance","lessonId":id,"kind":"positive-negative-calibration","passed":passed,"scope":lesson["scope"],"evidenceId":evidence_id,"expected":lesson["expected"],"oracleDigest":calibration["oracleDigest"],"sourceDigest":calibration["sourceDigest"],"harmonyBuildQualified":false,"uiQualified":false}),
        );
        // Bounded calibration entities remain directly queryable; raw receipts
        // keep complete submitted bodies/AST outside these analytical rows.
        for (variant, expected) in lesson["expected"].as_object().unwrap() {
            let observed = &calibration["variants"][variant];
            let variant_id = format!("{id}-variant-{variant}");
            put(
                &mut t,
                "lesson_validations",
                json!({"id":variant_id,"assetClass":"evaluation-instance","lessonId":id,"kind":"variant-verdict","variant":variant,"expectedPass":expected,"observedPass":observed["pass"],"passed":observed["pass"]==*expected&&observed["error"].is_null(),"scope":lesson["scope"],"evidenceId":evidence_id,"receipt":observed["receipt"]}),
            );
            if let Some(checks) = observed["checks"].as_object() {
                for (check, observed_pass) in checks {
                    put(
                        &mut t,
                        "lesson_evidence",
                        json!({"id":format!("{variant_id}-check-{}",hash(check.as_bytes())),"assetClass":"evaluation-instance","lessonId":id,"kind":"calibration-check-observation","authority":"operator-owned-oracle","variant":variant,"check":check,"observedPass":observed_pass,"validationId":variant_id,"receipt":observed["receipt"],"sourceDigest":calibration["sourceDigest"],"oracleDigest":calibration["oracleDigest"]}),
                    );
                }
            }
        }
        assert!(!Path::new(&a[5]).exists());
        println!("{}", export(Path::new(&a[5]), "evaluation-instance", &t));
    } else {
        assert_eq!(a[1], "promote");
        let source = Path::new(&a[2]);
        let lesson = rows(&source.join("experiment_lessons.jsonl"))
            .into_iter()
            .find(|r| r["id"] == a[5])
            .expect("Explicit lesson must exist");
        assert_eq!(
            lesson["status"], "verified",
            "Observation alone cannot become reusable guidance"
        );
        let validations = rows(&source.join("lesson_validations.jsonl"));
        assert!(lesson["validationIds"]
            .as_array()
            .unwrap()
            .iter()
            .all(|id| validations
                .iter()
                .any(|v| v["id"] == *id && v["passed"] == true)));
        for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
            t.entry(name.into()).or_default();
            for row in rows(&Path::new(&a[3]).join(format!("{name}.jsonl"))) {
                put(&mut t, name, row);
            }
        }
        let provenance = hash(&fs::read(source.join("experiment_lessons.jsonl")).unwrap());
        let source_export = load(&source.join("export.json"));
        let lineage = json!({"repository":source_export["repository"],"revision":source_export["revision"],"tablePrefix":source_export["tablePrefix"],"lessonId":lesson["id"],"lessonFileDigest":provenance});
        let method_digest = hash(include_bytes!(
            "../../../skills/agentlab-experiment-learning/SKILL.md"
        ));
        let method_revision = std::env::var("GITHUB_SHA").ok();
        let promotion = &lesson["promotionContract"];
        let fact = json!({"id":promotion["factId"],"assetClass":"reusable-knowledge","kind":"verified-lesson","scope":lesson["scope"],"phenomenon":lesson["phenomenon"],"cause":lesson["cause"],"change":lesson["change"],"sourceRevision":lesson["sourceRevision"],"sourceLessonId":lesson["id"],"sourceLessonExportDigest":provenance,"lessonSource":lineage,"methodSkillId":"agentlab-experiment-learning","methodDigest":method_digest,"methodRevision":method_revision,"validationIds":lesson["validationIds"],"qualification":promotion["qualification"]});
        let skill = json!({"id":promotion["skillId"],"assetClass":"reusable-knowledge","skillLayer":"method","role":"maintenance","stage":"calibration","objectId":lesson["id"],"title":lesson["phenomenon"],"factIds":[promotion["factId"]],"sourceLessonId":lesson["id"],"sourceLessonExportDigest":provenance,"lessonSource":lineage,"methodSkillId":"agentlab-experiment-learning","methodDigest":method_digest,"methodRevision":method_revision,"body":promotion["body"]});
        t.get_mut("program_facts")
            .unwrap()
            .insert(fact["id"].as_str().unwrap().into(), fact);
        t.get_mut("maintainer_skills")
            .unwrap()
            .insert(skill["id"].as_str().unwrap().into(), skill);
        assert!(!Path::new(&a[4]).exists());
        println!("{}", export(Path::new(&a[4]), "reusable-knowledge", &t));
    }
}
