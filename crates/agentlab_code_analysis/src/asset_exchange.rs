//! Stable typed analytical exchange shared by normalization and experience workflows.
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::Path;
pub type Tables = BTreeMap<String, BTreeMap<String, Value>>;
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn rows(path: &Path) -> Vec<Value> {
    BufReader::new(File::open(path).unwrap())
        .split(b'\n')
        .filter_map(|l| {
            let l = l.unwrap();
            if l.iter().all(u8::is_ascii_whitespace) {
                None
            } else {
                Some(serde_json::from_slice(&l).unwrap())
            }
        })
        .collect()
}
pub fn put(tables: &mut Tables, table: &str, row: Value) {
    let id = row["id"].as_str().unwrap().to_owned();
    let old = tables
        .entry(table.into())
        .or_default()
        .insert(id, row.clone());
    if let Some(old) = old {
        assert_eq!(old, row, "Conflicting stable identity in {table}");
    }
}
pub fn export(path: &Path, class: &str, tables: &Tables) -> Value {
    fs::create_dir_all(path).unwrap();
    let mut metas = Map::new();
    for (name, rows) in tables {
        let mut raw = Vec::new();
        let mut fields = Map::new();
        fields.insert("id".into(), json!({"type":"string","required":true}));
        fields.insert(
            "assetClass".into(),
            json!({"type":"string","required":false}),
        );
        // Owned nullable/empty-entity columns cannot depend on this run's values.
        let contracts: &[(&str, &str)] = match name.as_str() {
            "context_changes" => &[
                ("beforeMessageId", "string"),
                ("afterMessageId", "string"),
                ("kind", "string"),
                ("ordinal", "integer"),
            ],
            "context_versions" => &[
                ("attemptId", "string"),
                ("direction", "string"),
                ("sequence", "integer"),
                ("messageIds", "array"),
            ],
            "message_contents" => &[("role", "string"), ("message", "object")],
            "tool_calls" => &[
                ("isError", "boolean"),
                ("phaseId", "string"),
                ("arguments", "object"),
                ("result", "object"),
            ],
            "checks" => &[
                ("phaseId", "string"),
                ("check", "string"),
                ("passed", "boolean"),
            ],
            "assessments" => &[
                ("phaseId", "string"),
                ("buildPassed", "boolean"),
                ("behaviorPassed", "boolean"),
                ("sourceCut", "string"),
            ],
            "lesson_evidence" => &[
                ("variant", "string"),
                ("check", "string"),
                ("observedPass", "boolean"),
                ("validationId", "string"),
                ("receipt", "object"),
                ("sourceDigest", "string"),
                ("oracleDigest", "string"),
            ],
            "lesson_validations" => &[
                ("variant", "string"),
                ("expectedPass", "boolean"),
                ("observedPass", "boolean"),
                ("receipt", "object"),
            ],
            "attempts" => &[("parentAttemptId", "string"), ("forkScope", "string")],
            "llm_requests" => &[
                ("streamError", "object"),
                ("semanticComplete", "boolean"),
                ("phaseId", "string"),
                ("status", "integer"),
                ("model", "string"),
            ],
            _ => &[],
        };
        for (key, ty) in contracts {
            fields.insert((*key).into(), json!({"type":ty,"required":false}));
        }
        for row in rows.values() {
            serde_json::to_writer(&mut raw, row).unwrap();
            raw.push(b'\n');
            for (key, v) in row.as_object().unwrap() {
                let ty = match v {
                    Value::Null => continue,
                    Value::Bool(_) => "boolean",
                    Value::Number(n) if n.is_i64() || n.is_u64() => "integer",
                    Value::Number(_) => "number",
                    Value::Array(_) => "array",
                    Value::String(_) if key == "body" => "markdown",
                    Value::Object(_) => "object",
                    _ => "string",
                };
                if let Some(old) = fields.get(key) {
                    assert_eq!(old["type"], ty, "Type conflict {name}.{key}");
                }
                fields.insert(key.clone(), json!({"type":ty,"required":key=="id"}));
            }
        }
        fs::write(path.join(format!("{name}.jsonl")), &raw).unwrap();
        let indexes: Vec<Value> = [
            "assetClass",
            "runId",
            "kind",
            "attemptId",
            "phaseId",
            "requestId",
            "contextVersionId",
            "logicalMessageId",
            "toolCallId",
            "fileId",
            "sourceAnalysisId",
            "sourceRevision",
            "status",
            "role",
            "ordinal",
            "lessonId",
            "scope",
            "targetId",
            "variant",
            "check",
            "validationId",
            "observedPass",
        ]
        .iter()
        .filter(|k| {
            fields.get(**k).is_some_and(|f| {
                matches!(f["type"].as_str(), Some("string" | "integer" | "boolean"))
            })
        })
        .map(|k| json!({"name":format!("by_{k}"),"field":k}))
        .collect();
        metas.insert(name.clone(),json!({"rowCount":rows.len(),"sha256":hash(&raw),"definition":{"key_field":"id","fields":fields,"required_fields":["id"],"indexes":indexes,"description":format!("AgentLab {class} analytical {name}")}}));
    }
    let receipt = json!({"schema":"agentlab.asset_exchange.v1","assetClass":class,"tables":metas});
    fs::write(
        path.join("export.json"),
        serde_json::to_vec_pretty(&receipt).unwrap(),
    )
    .unwrap();
    receipt
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn null_only_references_and_empty_checks_keep_owned_types() {
        let path = std::env::temp_dir().join(format!(
            "al-null-schema-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut tables = Tables::new();
        put(
            &mut tables,
            "context_changes",
            json!({"id":"append","assetClass":"evaluation-instance","beforeMessageId":null,"afterMessageId":"message"}),
        );
        tables.entry("checks".into()).or_default();
        let receipt = export(&path, "evaluation-instance", &tables);
        assert_eq!(
            receipt["tables"]["context_changes"]["definition"]["fields"]["beforeMessageId"]["type"],
            "string"
        );
        assert_eq!(
            receipt["tables"]["checks"]["definition"]["fields"]["passed"]["type"],
            "boolean"
        );
        assert!(rows(&path.join("context_changes.jsonl"))[0]["beforeMessageId"].is_null());
        fs::remove_dir_all(path).unwrap();
    }
}
