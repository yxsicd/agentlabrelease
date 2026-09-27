use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    io::Write,
    path::{Path, PathBuf},
    process::Command,
};

const BINARIES: &[&str] = &[
    "agentlab-analysis-tools-pack",
    "agentlab-asset-model",
    "agentlab-cache-seed",
    "agentlab-code-analysis",
    "agentlab-experience",
    "agentlab-harmony-materialize",
    "agentlab-multi-repo-analysis",
    "agentlab-purchase-data-case-performance-plan",
    "agentlab-purchase-data-case-performance-qualification",
    "agentlab-purchase-data-integrated-review",
    "agentlab-purchase-data-integrated-review-packet",
    "agentlab-purchase-data-ohostest-candidate-qualification",
    "agentlab-purchase-data-ohostest-mutation-plan",
    "agentlab-purchase-data-ohostest-mutation-qualification",
    "agentlab-purchase-data-ohostest-performance-detector-qualification",
    "agentlab-purchase-data-ohostest-profile-qualification",
    "agentlab-purchase-data-ohostest-proposal",
    "agentlab-purchase-data-ohostest-reference-qualification",
    "agentlab-purchase-data-ohostest-review",
    "agentlab-purchase-data-ohostest-review-packet",
    "agentlab-purchase-data-runtime-oracle-bridge",
    "agentlab-purchase-data-runtime-plan",
    "agentlab-purchase-data-unseen-agent-cohort-contract",
    "agentlab-source-probe",
];

struct Binary {
    name: &'static str,
    bytes: Vec<u8>,
    sha256: String,
}

fn valid_revision(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_version(value: &str, revision: &str) -> bool {
    (8..=40).contains(&value.len())
        && revision.starts_with(value)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn load_binaries(root: &Path) -> Result<Vec<Binary>, String> {
    let mut binaries = Vec::new();
    for name in BINARIES {
        let path = root.join(name);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect binary {name}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("binary must be a regular file: {name}"));
        }
        let bytes =
            fs::read(&path).map_err(|error| format!("cannot read binary {name}: {error}"))?;
        if bytes.len() < 20
            || &bytes[..4] != b"\x7fELF"
            || bytes[4] != 2
            || bytes[5] != 1
            || u16::from_le_bytes([bytes[18], bytes[19]]) != 62
        {
            return Err(format!("binary is not Linux x86-64 ELF: {name}"));
        }
        binaries.push(Binary {
            name,
            sha256: digest(&bytes),
            bytes,
        });
    }
    Ok(binaries)
}

fn json_bytes(value: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn put_bytes(target: &mut [u8], value: &[u8], label: &str) -> Result<(), String> {
    if value.len() > target.len() {
        return Err(format!("tar {label} is too long"));
    }
    target[..value.len()].copy_from_slice(value);
    Ok(())
}

fn put_octal(target: &mut [u8], value: u64, label: &str) -> Result<(), String> {
    let width = target.len();
    let text = format!("{:0width$o}\0", value, width = width - 1);
    if text.len() != width {
        return Err(format!("tar {label} exceeds field width"));
    }
    target.copy_from_slice(text.as_bytes());
    Ok(())
}

fn write_member(
    writer: &mut impl Write,
    name: &str,
    bytes: &[u8],
    mode: u64,
    kind: u8,
) -> Result<(), String> {
    if !name.is_ascii() || name.is_empty() || name.len() > 100 {
        return Err(format!("tar member path is invalid: {name}"));
    }
    let mut header = [0u8; 512];
    put_bytes(&mut header[0..100], name.as_bytes(), "member name")?;
    put_octal(&mut header[100..108], mode, "mode")?;
    put_octal(&mut header[108..116], 0, "uid")?;
    put_octal(&mut header[116..124], 0, "gid")?;
    put_octal(&mut header[124..136], bytes.len() as u64, "size")?;
    put_octal(&mut header[136..148], 0, "mtime")?;
    header[148..156].fill(b' ');
    header[156] = kind;
    put_bytes(&mut header[257..263], b"ustar\0", "magic")?;
    put_bytes(&mut header[263..265], b"00", "version")?;
    let checksum: u64 = header.iter().map(|byte| u64::from(*byte)).sum();
    let checksum = format!("{checksum:06o}\0 ");
    header[148..156].copy_from_slice(checksum.as_bytes());
    writer
        .write_all(&header)
        .map_err(|error| format!("cannot write tar header: {error}"))?;
    writer
        .write_all(bytes)
        .map_err(|error| format!("cannot write tar member: {error}"))?;
    let padding = (512 - bytes.len() % 512) % 512;
    if padding != 0 {
        writer
            .write_all(&vec![0; padding])
            .map_err(|error| format!("cannot write tar padding: {error}"))?;
    }
    Ok(())
}

fn write_tar(path: &Path, manifest: &[u8], binaries: &[Binary]) -> Result<u64, String> {
    let mut file = fs::File::create(path).map_err(|error| format!("cannot create tar: {error}"))?;
    write_member(&mut file, "manifest.json", manifest, 0o644, b'0')?;
    write_member(&mut file, "payload/", &[], 0o755, b'5')?;
    write_member(&mut file, "payload/bin/", &[], 0o755, b'5')?;
    for binary in binaries {
        write_member(
            &mut file,
            &format!("payload/bin/{}", binary.name),
            &binary.bytes,
            0o755,
            b'0',
        )?;
    }
    file.write_all(&[0; 1024])
        .map_err(|error| format!("cannot finish tar: {error}"))?;
    file.sync_all()
        .map_err(|error| format!("cannot sync tar: {error}"))?;
    fs::metadata(path)
        .map(|metadata| metadata.len())
        .map_err(|error| format!("cannot inspect tar: {error}"))
}

fn write_new(path: &Path, bytes: &[u8], label: &str) -> Result<(), String> {
    if path.exists() {
        return Err(format!("refusing to overwrite {label}"));
    }
    fs::write(path, bytes).map_err(|error| format!("cannot write {label}: {error}"))
}

fn run_zstd(tar: &Path, archive: &Path) -> Result<(), String> {
    let status = Command::new("zstd")
        .args(["-q", "-19", "-T1", "-f"])
        .arg(tar)
        .arg("-o")
        .arg(archive)
        .status()
        .map_err(|error| format!("cannot execute zstd: {error}"))?;
    if !status.success() {
        return Err(format!("zstd failed with status {status}"));
    }
    Ok(())
}

fn value<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value(values, key)?))
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

fn package(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let binary_dir = path(values, "--binary-dir")?;
    let output = path(values, "--output")?;
    let revision = value(values, "--source-revision")?;
    let version = value(values, "--version")?;
    if !valid_revision(revision) {
        return Err("source revision must be exact 40-hex".into());
    }
    if !valid_version(version, revision) {
        return Err("version must be an 8-40 lowercase-hex source revision prefix".into());
    }
    if output.exists() {
        return Err("refusing to overwrite output directory".into());
    }
    let binaries = load_binaries(&binary_dir)?;
    fs::create_dir_all(&output).map_err(|error| format!("cannot create output: {error}"))?;
    let result = (|| {
        let inventory: Vec<Value> = binaries
            .iter()
            .map(|binary| {
                json!({
                    "name": binary.name,
                    "path": format!("payload/bin/{}", binary.name),
                    "bytes": binary.bytes.len(),
                    "sha256": binary.sha256
                })
            })
            .collect();
        let manifest = json!({
            "schema": "agentlab.analysis_tools_pack_manifest.v1",
            "sourceRevision": revision,
            "platform": "linux-x64",
            "buildProfile": "release-static-musl-v1",
            "binaryCount": binaries.len(),
            "binaries": inventory
        });
        let manifest_bytes = json_bytes(&manifest)?;
        let archive_name = format!("agentlab-pack-analysis-tools-{version}-linux-x64.tar.zst");
        let archive_path = output.join(&archive_name);
        let tar_path = output.join(format!(".{archive_name}.tar"));
        let logical_bytes = write_tar(&tar_path, &manifest_bytes, &binaries)?;
        run_zstd(&tar_path, &archive_path)?;
        fs::remove_file(&tar_path)
            .map_err(|error| format!("cannot remove temporary tar: {error}"))?;
        let archive_bytes = fs::read(&archive_path)
            .map_err(|error| format!("cannot read completed archive: {error}"))?;
        let archive_sha256 = digest(&archive_bytes);
        let descriptor_name = format!("{archive_name}.json");
        let descriptor = json!({
            "schema": "agentlab.capability_pack_descriptor.v1",
            "archive": {
                "filename": archive_name,
                "bytes": archive_bytes.len(),
                "logicalBytes": logical_bytes,
                "sha256": archive_sha256,
                "compression": {"format": "zstd", "level": 19, "threads": 1}
            },
            "pack": {
                "packId": "analysis-tools",
                "version": version,
                "platform": "linux-x64",
                "mountTarget": "/agentlab-analysis-tools",
                "optional": true
            }
        });
        let descriptor_bytes = json_bytes(&descriptor)?;
        write_new(
            &output.join(&descriptor_name),
            &descriptor_bytes,
            "pack descriptor",
        )?;
        let descriptor_sha256 = digest(&descriptor_bytes);
        let update_name = format!("analysis-tools-{version}-linux-x64.json");
        let update = json!({
            "schema": "agentlab.component_update.v1",
            "component": "pack:analysis-tools",
            "sourceRevision": revision,
            "value": {
                "archiveSha256": archive_sha256,
                "artifact": format!("./{archive_name}"),
                "descriptor": format!("./{descriptor_name}"),
                "enabled": true,
                "mountTarget": "/agentlab-analysis-tools",
                "packId": "analysis-tools",
                "platform": "linux-x64",
                "required": false,
                "slot": "analysis-tools",
                "version": version,
                "volume": format!("vol-agentlab-pack-analysis-tools-{version}-linux-x64-{}", &archive_sha256[..12])
            },
            "graphNode": {
                "binding": {"kind": "pack-slot", "slot": "analysis-tools"},
                "id": "component-analysis-tools",
                "platform": "linux-x64",
                "provides": {"agentlab.analysis-tools": 1},
                "requires": {},
                "upgradePolicy": "independent",
                "version": version
            },
            "assets": [
                {"url": format!("./{archive_name}"), "bytes": archive_bytes.len(), "sha256": archive_sha256},
                {"url": format!("./{descriptor_name}"), "bytes": descriptor_bytes.len(), "sha256": descriptor_sha256}
            ]
        });
        write_new(
            &output.join(&update_name),
            &json_bytes(&update)?,
            "component update",
        )?;
        write_new(
            &output.join("manifest.json"),
            &manifest_bytes,
            "pack manifest",
        )?;
        Ok(json!({
            "schema": "agentlab.analysis_tools_pack_receipt.v1",
            "status": "candidate-component-built-not-published",
            "sourceRevision": revision,
            "version": version,
            "binaryCount": binaries.len(),
            "archive": archive_name,
            "archiveSha256": archive_sha256,
            "descriptor": descriptor_name,
            "descriptorSha256": descriptor_sha256,
            "componentUpdate": update_name,
            "automaticPublication": false,
            "automaticPromotion": false
        }))
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&output);
    }
    result
}

fn run() -> Result<(), String> {
    let values = parse_values(env::args().skip(1))?;
    let receipt = package(&values)?;
    println!(
        "{}",
        serde_json::to_string(&receipt).map_err(|error| error.to_string())?
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("analysis-tools pack invalid: {error}");
        std::process::exit(1);
    }
}
