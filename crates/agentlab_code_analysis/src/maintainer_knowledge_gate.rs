use agentlab_code_analysis::knowledge_gate::{validate_gate, GateStage};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
};

fn value(args: &[String], name: &str) -> Result<String, String> {
    let index = args
        .iter()
        .position(|arg| arg == name)
        .ok_or_else(|| format!("missing {name}"))?;
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("missing value for {name}"))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let stage = GateStage::parse(&value(&args, "--stage")?)?;
    let source_spec = PathBuf::from(value(&args, "--source-spec")?);
    let difficulty = PathBuf::from(value(&args, "--difficulty")?);
    let knowledge_cut = PathBuf::from(value(&args, "--knowledge-cut")?);
    let binding = PathBuf::from(value(&args, "--binding")?);
    let candidate_id = value(&args, "--candidate-id")?;
    let output = PathBuf::from(value(&args, "--output")?);
    let receipt = validate_gate(
        stage,
        &source_spec,
        &difficulty,
        &knowledge_cut,
        &binding,
        &candidate_id,
    )?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output)
        .map_err(|error| format!("refusing to overwrite {}: {error}", output.display()))?;
    file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
    file.write_all(b"\n")?;
    println!("{}", serde_json::to_string(&receipt)?);
    Ok(())
}
