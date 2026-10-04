//! Explicit, digest-pinned compiler analysis; no submitted source execution.
use crate::{digest, maintainer_source_recipe_author as author};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    io::{Read, Write},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const SCRIPT: &str = include_str!("source_compiler_imports.cjs");
const OUTPUT_LIMIT: usize = 512 * 1024;

fn bounded_read(reader: impl Read, limit: usize) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    reader
        .take((limit + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > limit {
        return Err("compiler analysis capture exceeds budget".into());
    }
    Ok(bytes)
}

fn run(program: &str, compiler: &str, input: Vec<u8>) -> Result<Vec<u8>, String> {
    let mut child = Command::new(program)
        .args(["-e", SCRIPT, compiler])
        .env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let mut stdin = child.stdin.take().ok_or("compiler stdin absent")?;
    let stdout = child.stdout.take().ok_or("compiler stdout absent")?;
    let stderr = child.stderr.take().ok_or("compiler stderr absent")?;
    let writer = thread::spawn(move || stdin.write_all(&input).map_err(|e| e.to_string()));
    let out = thread::spawn(move || bounded_read(stdout, OUTPUT_LIMIT));
    let err = thread::spawn(move || bounded_read(stderr, 8192));
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) if start.elapsed() < Duration::from_secs(30) => {
                thread::sleep(Duration::from_millis(10))
            }
            result => {
                let _ = child.kill();
                let _ = child.wait();
                break Err(match result {
                    Err(error) => error.to_string(),
                    _ => "compiler analysis deadline exceeded; no source execution".into(),
                });
            }
        }
    };
    let written = writer.join().map_err(|_| "compiler writer panicked")?;
    let output = out.join().map_err(|_| "compiler stdout capture panicked")?;
    let errors = err.join().map_err(|_| "compiler stderr capture panicked")?;
    let status = status?;
    written?;
    let output = output?;
    let errors = errors?;
    if !status.success() {
        return Err(format!(
            "compiler analysis failed: {}",
            String::from_utf8_lossy(&errors)
        ));
    }
    if !errors.is_empty() {
        return Err("compiler analysis unexpected stderr".into());
    }
    Ok(output)
}

fn input_files(request: &Value) -> Result<Vec<Value>, String> {
    let mut result = Vec::new();
    let mut seen = BTreeSet::new();
    let owned = request["sourceFiles"]
        .as_array()
        .ok_or("compiler owned inventory absent")?;
    let context = request["readOnlySourceContext"]["packet"]["selectedFiles"].as_array();
    for (file, key) in owned
        .iter()
        .map(|f| (f, "content"))
        .chain(context.into_iter().flatten().map(|f| (f, "contentUtf8")))
    {
        let path = file["path"].as_str().ok_or("compiler source path absent")?;
        if !seen.insert(path) {
            return Err("compiler source path ambiguity".into());
        }
        let Some(content) = file[key].as_str() else {
            continue;
        };
        if ![".ts", ".ets", ".tsx", ".js", ".jsx"]
            .iter()
            .any(|suffix| path.ends_with(suffix))
        {
            continue;
        }
        if file["sha256"] != digest(content.as_bytes()) {
            return Err("compiler source digest differs".into());
        }
        result.push(json!({"path":path,"content":content,"sha256":file["sha256"]}));
    }
    if result.len() > 80 {
        return Err("compiler analysis source inventory budget".into());
    }
    Ok(result)
}

/// Optional policy-owned adapter. Existing requests without it remain byte-identical.
pub(crate) fn attach(request: &mut Value) -> Result<(), String> {
    let policy = &request["policy"];
    let Some(adapter) = policy.get("compilerAnalysisAdapter") else {
        return Ok(());
    };
    if adapter != "typescript-transpile-v1" {
        return Err("unknown compiler analysis adapter".into());
    }
    author::policy_gate(policy)?;
    let dependencies = policy["methodDependencies"]
        .as_array()
        .ok_or("compiler dependencies absent")?;
    if dependencies.len() != 1 {
        return Err("compiler adapter requires exactly one explicit dependency".into());
    }
    let files = input_files(request)?;
    let input = json!({"files":files});
    let input_bytes = serde_json::to_vec(&input).map_err(|e| e.to_string())?;
    if input_bytes.len() > 512 * 1024 {
        return Err("compiler analysis input exceeds budget".into());
    }
    let bytes = run(
        policy["program"]
            .as_str()
            .ok_or("compiler program absent")?,
        dependencies[0]["path"]
            .as_str()
            .ok_or("compiler dependency path absent")?,
        input_bytes.clone(),
    )?;
    author::policy_gate(policy)?;
    let output: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    let analyzed = output["files"]
        .as_array()
        .ok_or("compiler analysis result inventory absent")?;
    if analyzed.len() != files.len()
        || !analyzed
            .iter()
            .zip(&files)
            .all(|(row, file)| row["path"] == file["path"] && row["sourceSha256"] == file["sha256"])
    {
        return Err("compiler analysis result source binding differs".into());
    }
    request["sourceCompilerEvidence"] = json!({
        "schema":"agentlab.source_compiler_import_evidence.v1","adapter":adapter,
        "source":request["source"],"inputManifestSha256":digest(&input_bytes),
        "programSha256":policy["programSha256"],"compilerSha256":dependencies[0]["sha256"],
        "compilerVersion":output["compilerVersion"],"analyzerScriptSha256":digest(SCRIPT.as_bytes()),
        "runtimeHelperSha256":digest(include_bytes!("source_design_runtime.cjs")),
        "compilerOptions":{"module":"CommonJS","target":"ES2020","reportDiagnostics":true,"fileNameMapping":".ets suffix to .ts"},
        "files":analyzed,"analyzedFileCount":files.len(),
        "emittedImportIdentification":"AST static require call candidates; shadowing and dynamic require unresolved",
        "inventoryScope":"loaded supported script-language source bodies only; not complete repository",
        "sourceExecuted":false,"typeCheckingPerformed":false,"runtimeResolutionVerified":false,
        "platformRuntimeQualified":false,"oracleAdmitted":false,"authorityWritePerformed":false
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires explicitly supplied Node and locked TypeScript; exercised separately in CI"]
    fn real_pinned_compiler_erases_types_preserves_value_calls_and_never_executes_source() {
        let program = std::fs::canonicalize(
            std::env::var("AGENTLAB_TEST_NODE").expect("explicit Node required"),
        )
        .unwrap();
        let compiler = std::fs::canonicalize(
            std::env::var("AGENTLAB_TEST_TYPESCRIPT").expect("explicit compiler required"),
        )
        .unwrap();
        let compiler_sha = digest(&std::fs::read(&compiler).unwrap());
        assert_eq!(
            compiler_sha,
            "3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675"
        );
        let policy = json!({"schema":"agentlab.source_recipe_author_policy.v1","automaticPromotion":false,
            "program":program,"programSha256":crate::maintainer_operation_exec::executable_sha(&program).unwrap(),
            "methodDependencies":[{"path":compiler,"sha256":compiler_sha}],
            "compilerAnalysisAdapter":"typescript-transpile-v1"});
        for path in ["unrelated/project/unit.ets", "other-library/nested/unit.ts"] {
            let content = "import type {Missing} from './type-only'; import {Value} from './value-module'; export class Unit implements Missing { value = Value; } throw new Error('must never execute source');";
            let broken = "export const broken = ;";
            let declarations = "declare const environmentName: string;";
            let mut request = json!({"policy":policy,"source":{"revision":"a".repeat(40)},
            "sourceFiles":[{"path":path,"content":content,"sha256":digest(content.as_bytes())}],
            "readOnlySourceContext":{"packet":{"selectedFiles":[
                {"path":"shared/broken.ts","contentUtf8":broken,"sha256":digest(broken.as_bytes())},
                {"path":"types/environment.d.ts","contentUtf8":declarations,"sha256":digest(declarations.as_bytes())}
            ]}}});
            attach(&mut request).unwrap();
            let evidence = request["sourceCompilerEvidence"].clone();
            assert_eq!(evidence["compilerVersion"], "5.9.3");
            assert_eq!(evidence["files"][0]["status"], "transpiled");
            assert_eq!(
                evidence["files"][0]["emittedRequireSpecifiers"],
                json!(["./value-module"])
            );
            assert_eq!(evidence["files"][1]["status"], "transpile-errors");
            assert_eq!(evidence["files"][2]["status"], "compiler-error");
            assert_eq!(evidence["files"][2]["emittedJavaScriptSha256"], Value::Null);
            for key in [
                "sourceExecuted",
                "typeCheckingPerformed",
                "runtimeResolutionVerified",
                "platformRuntimeQualified",
                "oracleAdmitted",
                "authorityWritePerformed",
            ] {
                assert_eq!(evidence[key], false);
            }
            attach(&mut request).unwrap();
            assert_eq!(request["sourceCompilerEvidence"], evidence);
            let mut changed = request.clone();
            changed["policy"]["methodDependencies"][0]["sha256"] = json!("b".repeat(64));
            assert!(attach(&mut changed).is_err());
            let mut changed = request.clone();
            changed["policy"]["programSha256"] = json!("b".repeat(64));
            assert!(attach(&mut changed).is_err());
        }
    }
    #[test]
    fn optional_adapter_and_source_inventory_do_not_infer_execution() {
        let mut request = json!({"policy":{}});
        let original = request.clone();
        attach(&mut request).unwrap();
        assert_eq!(request, original);
        request["policy"]["compilerAnalysisAdapter"] = json!("guess-compiler");
        assert!(attach(&mut request).is_err());
        let file = json!({"path":"unrelated/unit.ts","content":"throw new Error('must not execute');","sha256":digest(b"throw new Error('must not execute');")});
        let mut request =
            json!({"sourceFiles":[file],"readOnlySourceContext":{"packet":{"selectedFiles":[]}}});
        assert_eq!(input_files(&request).unwrap().len(), 1);
        request["sourceFiles"][0]["sha256"] = json!("changed");
        assert!(input_files(&request).is_err());
        request["sourceFiles"][0]["sha256"] =
            json!(digest(b"throw new Error('must not execute');"));
        request["readOnlySourceContext"]["packet"]["selectedFiles"] =
            json!([{"path":"unrelated/unit.ts","contentUtf8":""}]);
        assert!(input_files(&request).is_err());
    }
}
