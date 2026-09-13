use agentlab_code_analysis::{analyze, digest};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    io::{BufWriter, Write},
    path::PathBuf,
    process::Command,
};
fn git(root: &PathBuf, args: &[&str]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).into_owned().into());
    }
    Ok(out.stdout)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err("Usage: agentlab-code-analysis <source-git-repo> <output-directory>".into());
    }
    let root = PathBuf::from(&args[0]);
    let out = PathBuf::from(&args[1]);
    fs::create_dir_all(&out)?;
    let revision = String::from_utf8(git(&root, &["rev-parse", "HEAD"])?)?
        .trim()
        .to_owned();
    let names = git(&root, &["ls-files", "-z"])?;
    let mut rows: Vec<Value> = Vec::new();
    let mut files = 0;
    let mut errors = 0;
    let mut errored_paths = Vec::new();
    for raw in names.split(|b| *b == 0).filter(|s| !s.is_empty()) {
        let path = std::str::from_utf8(raw)?;
        if !(path.ends_with(".ets") || path.ends_with(".ts")) {
            continue;
        }
        // Analyze exact committed bytes, independent of a dirty source Workspace.
        let bytes = git(&root, &["show", &format!("{revision}:{path}")])?;
        let analysis = analyze(path, &bytes, &revision)?;
        files += 1;
        if analysis.has_errors {
            errors += 1;
            errored_paths.push(path.to_owned());
        }
        rows.extend(analysis.rows);
    }
    rows.sort_by_key(|r| r["id"].as_str().unwrap().to_owned());
    let mut kinds: BTreeMap<String, usize> = BTreeMap::new();
    let mut bytes = Vec::new();
    for row in &rows {
        *kinds
            .entry(row["kind"].as_str().unwrap().to_owned())
            .or_default() += 1;
        serde_json::to_writer(&mut bytes, row)?;
        bytes.push(b'\n');
    }
    let mut output = BufWriter::new(fs::File::create(out.join("program_facts.jsonl"))?);
    output.write_all(&bytes)?;
    output.flush()?;
    let receipt = json!({"schema":"agentlab.ast_analysis.v1","sourceRevision":revision,
        "analyzer":"agentlab-code-analysis@0.1.0","parser":"tree-sitter@0.27.0","grammar":"tree-sitter-arkts@0.2.0",
        "files":files,"filesWithSyntaxErrors":errors,"erroredPaths":errored_paths,"rows":rows.len(),"kinds":kinds,
        "sha256":digest(&bytes),"coverage":"CST-derived syntax facts; no type, call-target or dataflow resolution","syntaxClean":errors==0,"fullArkTSQualified":false});
    fs::write(
        out.join("analysis.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )?;
    println!("{}", receipt);
    Ok(())
}
