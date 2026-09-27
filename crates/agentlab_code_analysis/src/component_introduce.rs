use agentlab_code_analysis::digest;
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

const RELEASE_PREFIX: &str = "https://github.com/yxsicd/agentlabrelease/releases/download/";
const FROZEN_PUBLICATION_FIELDS: &[&str] = &[
    "qualifiedReleaseTag",
    "compositionIdentity",
    "environmentLockUrl",
    "qualificationUrl",
    "previousPublicationUrl",
    "previousPublicationSha256",
    "activationPolicy",
    "sourceChannelOrCandidate",
    "sourcePublicationSha256",
    "qualification",
];

fn object<'a>(value: &'a Value, label: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{label} must be an object"))
}

fn object_mut<'a>(value: &'a mut Value, label: &str) -> Result<&'a mut Map<String, Value>, String> {
    value
        .as_object_mut()
        .ok_or_else(|| format!("{label} must be an object"))
}

fn field<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a Value, String> {
    object(value, label)?
        .get(key)
        .ok_or_else(|| format!("{label}.{key} is required"))
}

fn text<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    field(value, key, label)?
        .as_str()
        .ok_or_else(|| format!("{label}.{key} must be a string"))
}

fn array<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a Vec<Value>, String> {
    field(value, key, label)?
        .as_array()
        .ok_or_else(|| format!("{label}.{key} must be an array"))
}

fn array_mut<'a>(
    value: &'a mut Value,
    key: &str,
    label: &str,
) -> Result<&'a mut Vec<Value>, String> {
    object_mut(value, label)?
        .get_mut(key)
        .and_then(Value::as_array_mut)
        .ok_or_else(|| format!("{label}.{key} must be an array"))
}

fn is_lower_hex(value: &str, width: usize) -> bool {
    value.len() == width
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn json_bytes(value: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn read_json(path: &Path, label: &str) -> Result<(Vec<u8>, Value), String> {
    let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
    let value =
        serde_json::from_slice(&bytes).map_err(|error| format!("cannot parse {label}: {error}"))?;
    Ok((bytes, value))
}

fn release_base(url: &str) -> Result<String, String> {
    if url.contains('?') || url.contains('#') || !url.starts_with(RELEASE_PREFIX) {
        return Err("component update URL must be a canonical GitHub Release URL".into());
    }
    let tail = &url[RELEASE_PREFIX.len()..];
    let parts: Vec<&str> = tail.split('/').collect();
    if parts.len() != 2 || parts.iter().any(|part| part.is_empty()) {
        return Err("component update URL must contain one immutable tag and filename".into());
    }
    if matches!(parts[0], "aldev" | "almain" | "alprod") {
        return Err("component update URL must not use a mutable channel tag".into());
    }
    Ok(format!("{}{}/", RELEASE_PREFIX, parts[0]))
}

fn resolve_asset_url(base: &str, url: &str) -> Result<String, String> {
    let resolved = if let Some(name) = url.strip_prefix("./") {
        if name.is_empty() || name.contains('/') || name == "." || name == ".." {
            return Err("relative component asset URL must name one sibling file".into());
        }
        format!("{base}{name}")
    } else {
        url.to_owned()
    };
    if !resolved.starts_with(base)
        || resolved[base.len()..].is_empty()
        || resolved[base.len()..].contains('/')
        || resolved.contains('?')
        || resolved.contains('#')
    {
        return Err("component assets must remain in the descriptor's immutable release".into());
    }
    Ok(resolved)
}

fn resolve_update_assets(update: &mut Value, origin: &str) -> Result<(), String> {
    let base = release_base(origin)?;
    let value = object_mut(
        object_mut(update, "component update")?
            .get_mut("value")
            .ok_or_else(|| "component update.value is required".to_owned())?,
        "component update.value",
    )?;
    for key in ["artifact", "descriptor"] {
        let current = value
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("component update.value.{key} must be a string"))?;
        value.insert(
            key.to_owned(),
            Value::String(resolve_asset_url(&base, current)?),
        );
    }
    for asset in array_mut(update, "assets", "component update")? {
        let row = object_mut(asset, "component update asset")?;
        let current = row
            .get("url")
            .and_then(Value::as_str)
            .ok_or_else(|| "component update asset.url must be a string".to_owned())?;
        row.insert(
            "url".into(),
            Value::String(resolve_asset_url(&base, current)?),
        );
    }
    Ok(())
}

fn parse_binding<'a>(node: &'a Value, label: &str) -> Result<(&'a str, &'a str), String> {
    let binding = field(node, "binding", label)?;
    Ok((
        text(binding, "kind", &format!("{label}.binding"))?,
        text(binding, "slot", &format!("{label}.binding"))?,
    ))
}

fn resolved_contracts(nodes: &[Value]) -> Result<Value, String> {
    let mut providers: BTreeMap<String, BTreeMap<String, u64>> = BTreeMap::new();
    for (index, node) in nodes.iter().enumerate() {
        let label = format!("component graph node {index}");
        let platform = text(node, "platform", &label)?;
        let provided = object(
            field(node, "provides", &label)?,
            &format!("{label}.provides"),
        )?;
        for (contract, generation) in provided {
            let generation = generation
                .as_u64()
                .filter(|generation| *generation > 0)
                .ok_or_else(|| format!("{label} provides invalid contract generation"))?;
            if providers
                .entry(platform.to_owned())
                .or_default()
                .insert(contract.clone(), generation)
                .is_some()
            {
                return Err(format!("duplicate contract provider: {contract}"));
            }
        }
    }
    for (index, node) in nodes.iter().enumerate() {
        let label = format!("component graph node {index}");
        let platform = text(node, "platform", &label)?;
        let required = object(
            field(node, "requires", &label)?,
            &format!("{label}.requires"),
        )?;
        for (contract, bounds) in required {
            let bounds = object(bounds, &format!("{label}.requires.{contract}"))?;
            let minimum = bounds
                .get("min")
                .and_then(Value::as_u64)
                .ok_or_else(|| format!("{label} contract minimum is invalid"))?;
            let maximum = bounds
                .get("maxExclusive")
                .and_then(Value::as_u64)
                .ok_or_else(|| format!("{label} contract maximum is invalid"))?;
            let generation = providers
                .get(platform)
                .and_then(|items| items.get(contract))
                .copied()
                .ok_or_else(|| format!("unsatisfied contract: {contract}"))?;
            if !(minimum <= generation && generation < maximum) {
                return Err(format!("unsatisfied contract: {contract}"));
            }
        }
    }
    serde_json::to_value(providers).map_err(|error| error.to_string())
}

fn validate_asset<'a>(asset: &'a Value, label: &str) -> Result<(&'a str, u64, &'a str), String> {
    let url = text(asset, "url", label)?;
    let bytes = field(asset, "bytes", label)?
        .as_u64()
        .filter(|bytes| *bytes > 0)
        .ok_or_else(|| format!("{label}.bytes must be positive"))?;
    let sha256 = text(asset, "sha256", label)?;
    if !is_lower_hex(sha256, 64) {
        return Err(format!("{label}.sha256 must be exact lowercase 64-hex"));
    }
    Ok((url, bytes, sha256))
}

fn validate_base(publication: &Value, lock: &Value, lock_bytes: &[u8]) -> Result<(), String> {
    if !matches!(
        text(publication, "schema", "base publication")?,
        "agentlab.reference_publication.v1" | "agentlab.reference_publication.v3"
    ) {
        return Err("base publication schema is unsupported".into());
    }
    if text(lock, "schema", "base lock")? != "agentlab.environment_lock.v3" {
        return Err("base lock schema is unsupported".into());
    }
    if text(publication, "environmentLockSha256", "base publication")? != digest(lock_bytes) {
        return Err("base publication lock digest differs".into());
    }
    if text(publication, "sourceRevision", "base publication")?
        != text(lock, "sourceRevision", "base lock")?
    {
        return Err("base source revision differs".into());
    }
    let graph = field(lock, "componentGraph", "base lock")?;
    if text(graph, "schema", "base lock.componentGraph")? != "agentlab.component_graph.v1" {
        return Err("base component graph schema is unsupported".into());
    }
    let resolved = resolved_contracts(array(graph, "nodes", "base lock.componentGraph")?)?;
    if field(graph, "resolvedContracts", "base lock.componentGraph")? != &resolved {
        return Err("base resolved contracts differ".into());
    }
    let mut assets = BTreeMap::new();
    for (index, asset) in array(publication, "assets", "base publication")?
        .iter()
        .enumerate()
    {
        let (url, _, sha256) = validate_asset(asset, &format!("base publication asset {index}"))?;
        if assets.insert(url, sha256).is_some() {
            return Err("base publication contains duplicate asset URL".into());
        }
    }
    for collection in ["images", "components"] {
        for row in array(lock, collection, "base lock")? {
            let label = format!("base lock {collection} row");
            let artifact = text(row, "artifact", &label)?;
            let descriptor = text(row, "descriptor", &label)?;
            let archive_sha256 = text(row, "archiveSha256", &label)?;
            if assets.get(artifact).copied() != Some(archive_sha256) {
                return Err(format!("{label} archive asset identity differs"));
            }
            if !assets.contains_key(descriptor) {
                return Err(format!("{label} descriptor asset is missing"));
            }
        }
    }
    Ok(())
}

fn introduce(
    mut publication: Value,
    mut lock: Value,
    update_bytes: &[u8],
    mut update: Value,
    update_url: &str,
    tag: &str,
) -> Result<(Value, Value, Vec<u8>, Value), String> {
    let base_publication_sha256 =
        digest(&serde_json::to_vec(&publication).map_err(|error| error.to_string())?);
    if !tag.starts_with("candidate-") || tag.len() <= "candidate-".len() {
        return Err("new tag must be a candidate".into());
    }
    if text(&update, "schema", "component update")? != "agentlab.component_update.v1" {
        return Err("component update schema is unsupported".into());
    }
    let component = text(&update, "component", "component update")?.to_owned();
    let slot = component
        .strip_prefix("pack:")
        .filter(|slot| !slot.is_empty())
        .ok_or_else(|| "only a new pack slot can be introduced".to_owned())?
        .to_owned();
    let update_revision = text(&update, "sourceRevision", "component update")?.to_owned();
    if !is_lower_hex(&update_revision, 40) {
        return Err("component update source revision must be exact lowercase 40-hex".into());
    }
    resolve_update_assets(&mut update, update_url)?;
    let platform = text(&publication, "platform", "base publication")?.to_owned();
    let value = field(&update, "value", "component update")?.clone();
    if text(&value, "slot", "component update.value")? != slot
        || text(&value, "platform", "component update.value")? != platform
    {
        return Err("introduced component slot or platform differs".into());
    }
    if field(&value, "required", "component update.value")?.as_bool() != Some(false)
        || field(&value, "enabled", "component update.value")?.as_bool() != Some(true)
    {
        return Err("a newly introduced pack must be enabled and optional".into());
    }
    let version = text(&value, "version", "component update.value")?;
    if !(8..=40).contains(&version.len())
        || !update_revision.starts_with(version)
        || !is_lower_hex(version, version.len())
    {
        return Err("introduced component version must be a source revision prefix".into());
    }
    if text(&value, "packId", "component update.value")? != slot {
        return Err("introduced component pack id must match its slot".into());
    }
    let mount_target = text(&value, "mountTarget", "component update.value")?;
    if !mount_target.starts_with('/') || mount_target == "/" || mount_target.contains("..") {
        return Err("introduced component mount target is invalid".into());
    }
    let expected_update_url =
        format!("{RELEASE_PREFIX}{slot}-{version}-linux-x64/{slot}-{version}-linux-x64.json");
    if update_url != expected_update_url {
        return Err("component update URL is not source-derived from its slot and version".into());
    }
    if tag != format!("candidate-{slot}-{version}-linux-x64") {
        return Err("candidate tag is not source-derived from its slot and version".into());
    }
    let artifact = text(&value, "artifact", "component update.value")?.to_owned();
    let descriptor = text(&value, "descriptor", "component update.value")?.to_owned();
    let archive_sha256 = text(&value, "archiveSha256", "component update.value")?.to_owned();
    if !is_lower_hex(&archive_sha256, 64) {
        return Err("introduced component archive digest is invalid".into());
    }
    let graph_node = field(&update, "graphNode", "component update")?.clone();
    let (binding_kind, binding_slot) = parse_binding(&graph_node, "component update.graphNode")?;
    if binding_kind != "pack-slot"
        || binding_slot != slot
        || text(&graph_node, "platform", "component update.graphNode")? != platform
        || text(&graph_node, "version", "component update.graphNode")? != version
        || text(&graph_node, "upgradePolicy", "component update.graphNode")? != "independent"
    {
        return Err("introduced component graph binding differs".into());
    }
    let mut introduced_assets = Vec::new();
    let mut introduced_urls = BTreeSet::new();
    let mut artifact_digest = None;
    for (index, asset) in array(&update, "assets", "component update")?
        .iter()
        .enumerate()
    {
        let (url, _, sha256) = validate_asset(asset, &format!("component update asset {index}"))?;
        if !introduced_urls.insert(url.to_owned()) {
            return Err("component update contains duplicate asset URL".into());
        }
        if url == artifact {
            artifact_digest = Some(sha256.to_owned());
        }
        introduced_assets.push(asset.clone());
    }
    if !introduced_urls.contains(&artifact) || !introduced_urls.contains(&descriptor) {
        return Err("component update assets must include artifact and descriptor".into());
    }
    if artifact_digest.as_deref() != Some(archive_sha256.as_str()) {
        return Err("component archive digest differs from declared asset".into());
    }

    let components = array_mut(&mut lock, "components", "base lock")?;
    if components.iter().any(|row| {
        text(row, "slot", "base component").ok() == Some(slot.as_str())
            && text(row, "platform", "base component").ok() == Some(platform.as_str())
    }) {
        return Err("component slot already exists; use independent upgrade".into());
    }
    components.push(value.clone());
    let graph = object_mut(
        object_mut(&mut lock, "base lock")?
            .get_mut("componentGraph")
            .ok_or_else(|| "base lock.componentGraph is required".to_owned())?,
        "base lock.componentGraph",
    )?;
    let new_id = text(&graph_node, "id", "component update.graphNode")?;
    let resolved = {
        let nodes = graph
            .get_mut("nodes")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| "base lock.componentGraph.nodes must be an array".to_owned())?;
        for node in nodes.iter() {
            if text(node, "id", "base graph node").ok() == Some(new_id) {
                return Err("component graph node id already exists".into());
            }
            if let Ok((kind, existing_slot)) = parse_binding(node, "base graph node") {
                if kind == "pack-slot" && existing_slot == slot {
                    return Err(
                        "component graph slot already exists; use independent upgrade".into(),
                    );
                }
            }
        }
        nodes.push(graph_node.clone());
        resolved_contracts(nodes)?
    };
    graph.insert("resolvedContracts".into(), resolved);

    let existing_assets = array_mut(&mut publication, "assets", "base publication")?;
    let mut urls = BTreeSet::new();
    for (index, asset) in existing_assets.iter().enumerate() {
        let (url, _, _) = validate_asset(asset, &format!("base publication asset {index}"))?;
        if !urls.insert(url.to_owned()) {
            return Err("base publication contains duplicate asset URL".into());
        }
    }
    for asset in introduced_assets {
        let url = text(&asset, "url", "introduced asset")?;
        if !urls.insert(url.to_owned()) {
            return Err("introduced component asset already exists in base publication".into());
        }
        existing_assets.push(asset);
    }

    let lock_bytes = json_bytes(&lock)?;
    let receipt = json!({
        "schema": "agentlab.component_introduction.v1",
        "component": component,
        "slot": slot,
        "basePublicationSha256": base_publication_sha256,
        "replacementDescriptorSha256": digest(update_bytes),
        "replacementDescriptorUrl": update_url,
        "sourceRevision": update_revision,
        "introducedValue": value,
        "introducedGraphNode": graph_node,
        "rebuildComponents": false,
        "automaticPromotion": false
    });
    {
        let publication_object = object_mut(&mut publication, "candidate publication")?;
        for field in FROZEN_PUBLICATION_FIELDS {
            publication_object.remove(*field);
        }
        publication_object.insert(
            "schema".into(),
            Value::String("agentlab.reference_publication.v1".into()),
        );
        publication_object.insert("status".into(), Value::String("candidate".into()));
        publication_object.insert("tag".into(), Value::String(tag.into()));
        publication_object.insert("activated".into(), Value::Bool(false));
        publication_object.insert("componentPayloadsUploaded".into(), Value::Bool(false));
        publication_object.insert(
            "gates".into(),
            json!({
                "clean_install": "not_run",
                "protocol_discovery": "not_run",
                "mock_copy_tree": "not_run",
                "tablegit_recovery": "not_run"
            }),
        );
        publication_object.insert(
            "environmentLockSha256".into(),
            Value::String(digest(&lock_bytes)),
        );
        publication_object.insert("componentIntroduction".into(), receipt.clone());
    }
    validate_base(&publication, &lock, &lock_bytes)?;
    Ok((publication, lock, lock_bytes, receipt))
}

fn value<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn parse_values(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut args = args;
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), argument).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    Ok(values)
}

fn write_new(path: &Path, value: &[u8], label: &str) -> Result<(), String> {
    if path.exists() {
        return Err(format!("refusing to overwrite {label}"));
    }
    fs::write(path, value).map_err(|error| format!("cannot write {label}: {error}"))
}

fn run() -> Result<(), String> {
    let values = parse_values(env::args().skip(1))?;
    let expected = [
        "--base-publication",
        "--base-lock",
        "--component-update",
        "--component-update-url",
        "--tag",
        "--output",
    ];
    if values.len() != expected.len() || values.keys().any(|key| !expected.contains(&key.as_str()))
    {
        return Err("arguments must contain exactly the documented six flags".into());
    }
    let base_publication = PathBuf::from(value(&values, "--base-publication")?);
    let base_lock = PathBuf::from(value(&values, "--base-lock")?);
    let update_path = PathBuf::from(value(&values, "--component-update")?);
    let update_url = value(&values, "--component-update-url")?;
    let tag = value(&values, "--tag")?;
    let output = PathBuf::from(value(&values, "--output")?);
    if output.exists() {
        return Err("refusing to overwrite output directory".into());
    }
    let (_, publication) = read_json(&base_publication, "base publication")?;
    let (lock_bytes, lock) = read_json(&base_lock, "base lock")?;
    validate_base(&publication, &lock, &lock_bytes)?;
    let (update_bytes, update) = read_json(&update_path, "component update")?;
    let (publication, _lock, lock_bytes, receipt) =
        introduce(publication, lock, &update_bytes, update, update_url, tag)?;
    fs::create_dir_all(&output).map_err(|error| format!("cannot create output: {error}"))?;
    let result: Result<(), String> = (|| {
        write_new(
            &output.join("environment-lock.json"),
            &lock_bytes,
            "candidate lock",
        )?;
        write_new(
            &output.join("publication.json"),
            &json_bytes(&publication)?,
            "candidate publication",
        )?;
        write_new(
            &output.join("component-introduction.json"),
            &json_bytes(&receipt)?,
            "component introduction receipt",
        )?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&output);
    }
    result?;
    println!(
        "{}",
        serde_json::to_string(&receipt).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("component introduction invalid: {error}");
        std::process::exit(1);
    }
}
