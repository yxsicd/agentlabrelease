use agentlab_code_analysis::maintainer_skill_flywheel::assess;
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

fn optional(args: &[String], name: &str) -> Option<String> {
    let index = args.iter().position(|arg| arg == name)?;
    args.get(index + 1).cloned()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let scopes = PathBuf::from(value(&args, "--scope-skills")?);
    let facts = optional(&args, "--program-facts").map(PathBuf::from);
    let round_index = value(&args, "--round-index")?.parse::<u64>()?;
    let parent = optional(&args, "--parent-assessment-sha256");
    let output = PathBuf::from(value(&args, "--output")?);
    let assessment = assess(&scopes, facts.as_deref(), round_index, parent.as_deref())?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output)
        .map_err(|error| format!("refusing to overwrite {}: {error}", output.display()))?;
    file.write_all(&serde_json::to_vec_pretty(&assessment)?)?;
    file.write_all(b"\n")?;
    println!("{}", serde_json::to_string(&assessment["totals"])?);
    Ok(())
}
