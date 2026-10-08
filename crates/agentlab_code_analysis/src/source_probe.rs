//! Analyze exact observed Workspace bytes without committing or executing them.
use agentlab_code_analysis::{
    analyze, digest, source_material::MaterialRequest, GRAMMAR, GRAMMAR_DIGEST,
};
use serde_json::json;
use std::{env, fs, io::Read};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args
        .first()
        .is_some_and(|arg| arg == "--validate-material-request")
    {
        if args.len() != 2 {
            return Err(
                "Usage: agentlab-source-probe --validate-material-request <request.json>".into(),
            );
        }
        // Avoid echoing parser diagnostics that could contain credential input.
        if !fs::symlink_metadata(&args[1])
            .map_err(|_| "material request cannot be read")?
            .is_file()
        {
            return Err("material request must be a regular file".into());
        }
        let mut options = fs::OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_NONBLOCK | libc::O_NOFOLLOW);
        }
        let file = options
            .open(&args[1])
            .map_err(|_| "material request cannot be read")?;
        if !file
            .metadata()
            .map_err(|_| "material request cannot be read")?
            .is_file()
        {
            return Err("material request must be a regular file".into());
        }
        let mut bytes = Vec::new();
        file.take(32 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "material request cannot be read")?;
        if bytes.len() > 32 * 1024 {
            return Err("material request byte limit exceeded".into());
        }
        let request: MaterialRequest =
            serde_json::from_slice(&bytes).map_err(|_| "material request decode rejected")?;
        request.validate()?;
        println!(
            "{}",
            json!({"schema":"agentlab.source_material_contract_validation.v1",
            "contractValid":true,"acquisitionCompleted":false,"sourceBytesVerified":false,
            "extractionCompleted":false,"sessionImported":false,"coverage":"request-contract-only"})
        );
        return Ok(());
    }
    if args.len() != 1 {
        return Err("Usage: agentlab-source-probe <observed-source-file> | --validate-material-request <request.json>".into());
    }
    let path = &args[0];
    let bytes = fs::read(path)?;
    let sha = digest(&bytes);
    let cut = format!("sha256:{sha}");
    let analysis = analyze(path, &bytes, &cut)?;
    println!(
        "{}",
        json!({"schema":"agentlab.observed_source_analysis.v1",
        "sourceCut":cut,"byteLength":bytes.len(),"grammar":GRAMMAR,
        "grammarDigest":GRAMMAR_DIGEST,"syntaxHasErrors":analysis.has_errors,
        "authority":"supervisor-observed-file-bytes","rows":analysis.rows})
    );
    Ok(())
}
