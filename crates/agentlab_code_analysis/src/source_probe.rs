//! Analyze exact observed Workspace bytes without committing or executing them.
use agentlab_code_analysis::{analyze, digest, GRAMMAR, GRAMMAR_DIGEST};
use serde_json::json;
use std::{env, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = env::args()
        .nth(1)
        .ok_or("Usage: agentlab-source-probe <observed-source-file>")?;
    let bytes = fs::read(&path)?;
    let sha = digest(&bytes);
    let cut = format!("sha256:{sha}");
    let analysis = analyze(&path, &bytes, &cut)?;
    println!(
        "{}",
        json!({"schema":"agentlab.observed_source_analysis.v1",
        "sourceCut":cut,"byteLength":bytes.len(),"grammar":GRAMMAR,
        "grammarDigest":GRAMMAR_DIGEST,"syntaxHasErrors":analysis.has_errors,
        "authority":"supervisor-observed-file-bytes","rows":analysis.rows})
    );
    Ok(())
}
