//! Source-bound standard-test task selection; no builds or authority promotion.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};

fn relative(root: &Path, path: &str) -> Result<PathBuf, String> {
    let path = Path::new(path);
    if path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_) | Component::CurDir))
    {
        return Err("module path must stay within project".into());
    }
    let mut joined = root.to_path_buf();
    for part in path.components() {
        if let Component::Normal(name) = part {
            joined.push(name);
            if fs::symlink_metadata(&joined)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
            {
                return Err("module path contains symlink".into());
            }
        }
    }
    Ok(joined)
}

fn read(root: &Path, path: &Path, evidence: &mut Vec<Value>) -> Result<Value, String> {
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > 65536 {
        return Err("build configuration must be a bounded regular file".into());
    }
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    let value = json5::from_str(std::str::from_utf8(&bytes).map_err(|e| e.to_string())?)
        .map_err(|e| format!("invalid build JSON5: {e}"))?;
    evidence.push(json!({"path":path.strip_prefix(root).map_err(|e|e.to_string())?.to_str().ok_or("non-UTF8 configuration path")?,
        "sha256":format!("{:x}",Sha256::digest(&bytes)),"byteLength":bytes.len()}));
    Ok(value)
}

fn module(
    root: &Path,
    profile: &Value,
    name: &str,
    evidence: &mut Vec<Value>,
) -> Result<(String, String, Value), String> {
    let rows = profile["modules"]
        .as_array()
        .ok_or("project modules missing")?;
    let found = rows
        .iter()
        .filter(|row| row["name"] == name)
        .collect::<Vec<_>>();
    if found.len() != 1 {
        return Err("build module must have one project registration".into());
    }
    let dir = relative(
        root,
        found[0]["srcPath"]
            .as_str()
            .ok_or("module srcPath missing")?,
    )?;
    let main = read(
        root,
        &relative(
            root,
            &format!(
                "{}/src/main/module.json5",
                dir.strip_prefix(root).unwrap().display()
            ),
        )?,
        evidence,
    )?;
    let config = read(root, &dir.join("build-profile.json5"), evidence)?;
    let kind = main["module"]["type"]
        .as_str()
        .ok_or("module output type missing")?;
    let kind = match kind {
        "entry" | "feature" => "hap",
        "har" => "har",
        "shared" => "hsp",
        _ => return Err("unsupported module output type".into()),
    };
    Ok((
        dir.strip_prefix(root)
            .unwrap()
            .to_str()
            .ok_or("non-UTF8 module path")?
            .into(),
        kind.into(),
        config,
    ))
}

pub fn prepare(
    root: &Path,
    build_module: &str,
    host_module: &str,
    product: &str,
    mode: &str,
) -> Result<Value, String> {
    for token in [build_module, host_module, product, mode] {
        if token.is_empty()
            || token.len() > 200
            || !token
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        {
            return Err("invalid build token".into());
        }
    }
    let root = root.canonicalize().map_err(|e| e.to_string())?;
    let mut evidence = vec![];
    let profile = read(&root, &root.join("build-profile.json5"), &mut evidence)?;
    if !profile["app"]["products"]
        .as_array()
        .is_some_and(|rows| rows.iter().any(|r| r["name"] == product))
    {
        return Err("product is not declared".into());
    }
    if !profile["app"]["buildModeSet"]
        .as_array()
        .is_some_and(|rows| rows.iter().any(|r| r["name"] == mode))
    {
        return Err("build mode is not declared".into());
    }
    let (module_path, kind, config) = module(&root, &profile, build_module, &mut evidence)?;
    if !config["targets"]
        .as_array()
        .is_some_and(|rows| rows.iter().any(|r| r["name"] == "ohosTest"))
    {
        return Err("selected module has no ohosTest target".into());
    }
    let (host_path, host_kind, host_config) = module(&root, &profile, host_module, &mut evidence)?;
    if host_kind != "hap" {
        return Err("host module must produce HAP".into());
    }
    if !host_config["targets"]
        .as_array()
        .is_some_and(|rows| rows.iter().any(|r| r["name"] == "default"))
    {
        return Err("host module has no default target".into());
    }
    let task = if kind == "hap" {
        "assembleHap"
    } else {
        "genOnDeviceTestHap"
    };
    evidence.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    evidence.dedup();
    Ok(
        json!({"schema":"agentlab.harmony_standard_test_build_plan.v1",
        "module":build_module,"modulePath":module_path,"outputType":kind,
        "hostModule":host_module,"hostModulePath":host_path,"product":product,"buildMode":mode,
        "commands":[{"module":host_module,"target":"default","task":"assembleHap"},
            {"module":build_module,"target":"ohosTest","task":task}],
        "sourceBindings":evidence,"automaticPromotion":false,"runtimeQualified":false}),
    )
}
