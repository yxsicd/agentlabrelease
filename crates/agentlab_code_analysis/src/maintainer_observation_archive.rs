//! Bounded deterministic preservation of the reconstructed export, not Agent homes.
use super::{digest, file, need, Tables};
use flate2::{bufread::GzDecoder, write::GzEncoder, Compression};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    path::{Component, Path},
};
const BUDGET: usize = 32 * 1024 * 1024;
const CHUNK: usize = 24 * 1024;
fn relative(name: &str) -> bool {
    !name.is_empty()
        && !name.contains('\\')
        && !name.contains(':')
        && name
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
        && Path::new(name)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8] = b"0123456789abcdef";
    bytes
        .iter()
        .flat_map(|b| {
            [
                DIGITS[(b >> 4) as usize] as char,
                DIGITS[(b & 15) as usize] as char,
            ]
        })
        .collect()
}
fn unhex(s: &str, limit: usize) -> Result<Vec<u8>, String> {
    need(
        s.len() <= limit * 2 && s.len() % 2 == 0,
        "archive hex budget or length",
    )?;
    s.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |b| match b {
                b'0'..=b'9' => Ok(b - b'0'),
                b'a'..=b'f' => Ok(b - b'a' + 10),
                _ => Err("archive hex invalid".to_owned()),
            };
            Ok(digit(pair[0])? * 16 + digit(pair[1])?)
        })
        .collect()
}
pub fn definition() -> Value {
    json!({"key_field":"id","required_fields":["id","archiveId","ordinal","hex","sha256","byteCount"],
        "description":"Immutable compressed export evidence chunks; not business observations",
        "fields":{"id":{"type":"string","required":true},"archiveId":{"type":"string","required":true},
            "ordinal":{"type":"integer","required":true},"hex":{"type":"string","required":true},
            "sha256":{"type":"string","required":true},"byteCount":{"type":"integer","required":true}},
        "indexes":[{"name":"by_archive","field":"archiveId"}]})
}
pub fn prepare(root: &Path, tables: &Tables) -> Result<(BTreeMap<String, Value>, Value), String> {
    let mut files = BTreeMap::new();
    let mut total = 0;
    if let Some(rows) = tables.get("evidence_files") {
        for row in rows.values() {
            let name = row["path"].as_str().ok_or("archive file path absent")?;
            need(relative(name), "archive input path unsafe")?;
            let bytes = file(root, name)?;
            total += bytes.len();
            need(
                total <= BUDGET && files.len() < 1000,
                "archive aggregate budget",
            )?;
            need(
                row["sha256"] == digest(&bytes) && row["bytes"] == bytes.len(),
                "archive evidence differs",
            )?;
            need(
                files.insert(name.to_owned(), bytes).is_none(),
                "archive file path duplicate",
            )?;
        }
    }
    // The original typed manifest and analytical JSONL bytes are also required
    // for a standalone recovered export. Never scan the surrounding directory.
    for name in tables
        .keys()
        .map(|n| format!("{n}.jsonl"))
        .chain(["export.json".into()])
    {
        need(relative(&name), "archive table path unsafe")?;
        let bytes = file(root, &name)?;
        total += bytes.len();
        need(
            total <= BUDGET && files.len() < 1000,
            "archive aggregate budget",
        )?;
        need(
            files.insert(name.clone(), bytes).is_none(),
            "archive file collision",
        )?;
    }
    need(
        !files.is_empty()
            && files.len() <= 1000
            && files.values().map(Vec::len).sum::<usize>() <= BUDGET,
        "archive aggregate budget",
    )?;
    let records: Vec<Value> = files.iter().map(|(name,bytes)| json!({"path":name,"bytes":bytes.len(),"sha256":digest(bytes),"hex":hex(bytes)})).collect();
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    encoder
        .write_all(&serde_json::to_vec(&records).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let packed = encoder.finish().map_err(|e| e.to_string())?;
    need(
        packed.len() <= BUDGET && packed.len().div_ceil(CHUNK) <= 1000,
        "archive compressed budget",
    )?;
    let archive_id = digest(&packed);
    let rows = packed.chunks(CHUNK).enumerate().map(|(i,bytes)| {
        let id = format!("{archive_id}-{i:04}");
        (id.clone(), json!({"id":id,"archiveId":archive_id,"ordinal":i,"hex":hex(bytes),"sha256":digest(bytes),"byteCount":bytes.len()}))
    }).collect();
    let binding = json!({"schema":"agentlab.observation_raw_archive.v1","archiveId":archive_id,"encoding":"gzip-json-hex-v1",
        "packedBytes":packed.len(),"chunkCount":packed.len().div_ceil(CHUNK),"files":files.iter().map(|(name,bytes)|json!({"path":name,"bytes":bytes.len(),"sha256":digest(bytes)})).collect::<Vec<_>>()});
    Ok((rows, binding))
}
pub fn reconstruct(
    binding: &Value,
    rows: &BTreeMap<String, Value>,
) -> Result<BTreeMap<String, Vec<u8>>, String> {
    need(
        binding["schema"] == "agentlab.observation_raw_archive.v1"
            && binding["encoding"] == "gzip-json-hex-v1",
        "archive binding invalid",
    )?;
    let id = binding["archiveId"]
        .as_str()
        .ok_or("archive identity absent")?;
    let count = binding["chunkCount"]
        .as_u64()
        .filter(|n| *n > 0 && *n <= 1000)
        .ok_or("archive chunk count invalid")?;
    let selected: Vec<_> = rows.values().filter(|r| r["archiveId"] == id).collect();
    need(
        selected.len() == count as usize,
        "archive chunk inventory differs",
    )?;
    let mut packed = Vec::new();
    for i in 0..count {
        let key = format!("{id}-{i:04}");
        let row = rows.get(&key).ok_or("archive chunk missing")?;
        need(
            row["id"] == key && row["archiveId"] == id && row["ordinal"] == i,
            "archive chunk identity differs",
        )?;
        let bytes = unhex(
            row["hex"].as_str().ok_or("archive chunk text absent")?,
            CHUNK,
        )?;
        need(
            !bytes.is_empty()
                && (i + 1 == count || bytes.len() == CHUNK)
                && row["byteCount"] == bytes.len()
                && row["sha256"] == digest(&bytes),
            "archive chunk bytes differ",
        )?;
        packed.extend(bytes);
        need(packed.len() <= BUDGET, "archive compressed budget")?;
    }
    need(
        binding["packedBytes"] == packed.len() && digest(&packed) == id,
        "archive packed identity differs",
    )?;
    let mut decoder = GzDecoder::new(packed.as_slice());
    let mut raw = Vec::new();
    decoder
        .by_ref()
        .take((BUDGET * 2 + 1024 * 1024 + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|e| e.to_string())?;
    need(
        raw.len() <= BUDGET * 2 + 1024 * 1024 && decoder.into_inner().is_empty(),
        "archive expansion budget or trailing bytes",
    )?;
    let records: Vec<Value> = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    need(
        !records.is_empty() && records.len() <= 1000,
        "archive member budget",
    )?;
    let mut files = BTreeMap::new();
    let mut total = 0;
    for record in records {
        let name = record["path"]
            .as_str()
            .ok_or("archive member path absent")?;
        need(relative(name), "archive member path unsafe")?;
        let bytes = unhex(
            record["hex"].as_str().ok_or("archive member hex absent")?,
            BUDGET,
        )?;
        total += bytes.len();
        need(total <= BUDGET, "archive expanded file budget")?;
        need(
            record["bytes"] == bytes.len() && record["sha256"] == digest(&bytes),
            "archive member bytes differ",
        )?;
        need(
            files.insert(name.to_owned(), bytes).is_none(),
            "archive duplicate member",
        )?;
    }
    let inventory = json!(files
        .iter()
        .map(|(name, bytes)| json!({"path":name,"bytes":bytes.len(),"sha256":digest(bytes)}))
        .collect::<Vec<_>>());
    need(
        binding["files"] == inventory,
        "archive member inventory differs",
    )?;
    Ok(files)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet(records: Value, trailing: bool) -> (Value, BTreeMap<String, Value>) {
        let mut gz = GzEncoder::new(Vec::new(), Compression::default());
        gz.write_all(&serde_json::to_vec(&records).unwrap())
            .unwrap();
        let mut bytes = gz.finish().unwrap();
        if trailing {
            bytes.push(0);
        }
        let id = digest(&bytes);
        let key = format!("{id}-0000");
        let rows = BTreeMap::from([(
            key.clone(),
            json!({"id":key,"archiveId":id,"ordinal":0,"hex":hex(&bytes),"sha256":digest(&bytes),"byteCount":bytes.len()}),
        )]);
        (
            json!({"schema":"agentlab.observation_raw_archive.v1","encoding":"gzip-json-hex-v1","archiveId":id,"packedBytes":bytes.len(),"chunkCount":1,"files":[]}),
            rows,
        )
    }
    #[test]
    fn rehashed_unsafe_duplicate_members_and_trailing_gzip_are_rejected() {
        for path in [
            "../escape",
            "/absolute",
            "a/../b",
            "a//b",
            "a/./b",
            "C:/escape",
            "a\\b",
        ] {
            let (binding, rows) = packet(
                json!([{"path":path,"bytes":1,"sha256":digest(b"x"),"hex":"78"}]),
                false,
            );
            assert!(reconstruct(&binding, &rows)
                .unwrap_err()
                .contains("path unsafe"));
        }
        let member = json!({"path":"safe","bytes":1,"sha256":digest(b"x"),"hex":"78"});
        let (binding, rows) = packet(json!([member.clone(), member.clone()]), false);
        assert!(reconstruct(&binding, &rows)
            .unwrap_err()
            .contains("duplicate"));
        let (binding, rows) = packet(json!([member]), true);
        assert!(reconstruct(&binding, &rows)
            .unwrap_err()
            .contains("trailing"));
    }
}
