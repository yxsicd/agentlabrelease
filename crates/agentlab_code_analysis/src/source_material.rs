//! Pure source-material contracts. No download, extraction, file read or execution.
//! Declared inventories are not byte-verified snapshots or Session admission.
use crate::digest;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use url::Url;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct MaterialRequest {
    pub schema: String,
    pub repository_id: String,
    pub source: Source,
    pub limits: Limits,
    pub source_root: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", deny_unknown_fields, rename_all = "kebab-case")]
pub enum Source {
    #[serde(rename_all = "camelCase")]
    GitHttp {
        url: String,
        requested_ref: Option<String>,
    },
    Archive {
        locator: ArchiveLocator,
        format: ArchiveFormat,
        sha256: String,
        bytes: u64,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", deny_unknown_fields, rename_all = "kebab-case")]
pub enum ArchiveLocator {
    Http {
        url: String,
    },
    #[serde(rename_all = "camelCase")]
    Artifact {
        artifact_id: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ArchiveFormat {
    #[serde(rename = "zip")]
    Zip,
    #[serde(rename = "tar")]
    Tar,
    #[serde(rename = "tar.gz")]
    TarGz,
    #[serde(rename = "tar.zst")]
    TarZst,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Limits {
    pub acquisition_bytes: u64,
    pub expanded_bytes: u64,
    pub file_bytes: u64,
    pub entries: usize,
    pub depth: usize,
    pub duration_seconds: u64,
}

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 160
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b))
}
fn relative(value: &str) -> bool {
    !value.is_empty()
        && value.chars().count() <= 4096
        && !value.chars().any(char::is_control)
        && !value.contains(['\\', ':'])
        && value
            .split('/')
            .all(|p| !p.is_empty() && !matches!(p, "." | "..") && !p.eq_ignore_ascii_case(".git"))
}
fn http_url(value: &str) -> Result<(), String> {
    // A locator is not a credential carrier or a network authorization grant.
    need(
        !value.chars().any(|c| c.is_whitespace() || c.is_control())
            && !value.contains('\\')
            && value.chars().count() <= 4096
            && (value.starts_with("http://") || value.starts_with("https://")),
        "unsafe HTTP locator",
    )?;
    let parsed = Url::parse(value).map_err(|_| "invalid HTTP locator")?;
    need(
        matches!(parsed.scheme(), "http" | "https")
            && parsed.host_str().is_some()
            && parsed.username().is_empty()
            && parsed.password().is_none()
            && parsed.query().is_none()
            && parsed.fragment().is_none(),
        "unsafe HTTP locator",
    )?;
    // The URL parser normalizes empty userinfo; do not silently admit it.
    let authority = value
        .split_once("://")
        .map(|(_, v)| v.split('/').next().unwrap_or(""))
        .unwrap_or("");
    need(
        !authority.is_empty() && !authority.contains('@'),
        "unsafe HTTP locator",
    )
}

impl Limits {
    pub fn validate(&self) -> Result<(), String> {
        const MAX: u64 = 16 * 1024 * 1024 * 1024;
        need(
            self.acquisition_bytes > 0
                && self.acquisition_bytes <= MAX
                && self.expanded_bytes > 0
                && self.expanded_bytes <= MAX
                && self.file_bytes > 0
                && self.file_bytes <= self.expanded_bytes
                && (1..=500_000).contains(&self.entries)
                && (1..=128).contains(&self.depth)
                && (1..=3600).contains(&self.duration_seconds),
            "invalid source material limits",
        )
    }
}
impl MaterialRequest {
    pub fn validate(&self) -> Result<(), String> {
        need(
            self.schema == "agentlab.source_material_request.v1",
            "source material schema differs",
        )?;
        need(id(&self.repository_id), "invalid repository identity")?;
        self.limits.validate()?;
        if let Some(root) = &self.source_root {
            need(relative(root), "unsafe source root")?;
        }
        match &self.source {
            Source::GitHttp { url, requested_ref } => {
                http_url(url)?;
                if let Some(reference) = requested_ref {
                    need(
                        !reference.is_empty()
                            && reference.chars().count() <= 1024
                            && !reference.starts_with('-')
                            && !reference.chars().any(char::is_control),
                        "invalid requested ref",
                    )?;
                }
            }
            Source::Archive {
                locator,
                sha256,
                bytes,
                ..
            } => {
                match locator {
                    ArchiveLocator::Http { url } => http_url(url)?,
                    ArchiveLocator::Artifact { artifact_id } => {
                        need(id(artifact_id), "invalid archive artifact identity")?
                    }
                }
                need(
                    hex(sha256, 64) && *bytes > 0 && *bytes <= self.limits.acquisition_bytes,
                    "archive identity or acquisition limit differs",
                )?;
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct FileDeclaration {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
    pub executable: bool,
}

/// Canonical declared regular-file identity, independent of transport/packaging.
/// Exact UTF-8 paths sorted bytewise; no mtimes, owners, archive wrappers or .git.
/// v1 intentionally rejects links/special files via this regular-only shape.
/// This result cannot establish actual file bytes, source authenticity or skills.
pub fn declared_content_id(files: &[FileDeclaration], limits: &Limits) -> Result<String, String> {
    limits.validate()?;
    need(
        !files.is_empty() && files.len() <= limits.entries,
        "source entry limit differs",
    )?;
    let mut seen = BTreeSet::new();
    let mut total = 0_u64;
    let mut sorted = files.to_vec();
    for file in &sorted {
        need(
            relative(&file.path) && file.path.split('/').count() <= limits.depth,
            "unsafe source entry path or depth",
        )?;
        need(seen.insert(file.path.clone()), "duplicate source entry")?;
        need(
            hex(&file.sha256, 64) && file.bytes <= limits.file_bytes,
            "invalid source file identity",
        )?;
        total = total
            .checked_add(file.bytes)
            .ok_or("source byte count overflow")?;
        need(
            total <= limits.expanded_bytes,
            "source expanded byte limit differs",
        )?;
    }
    // No regular file may also serve as another file's parent directory.
    for path in &seen {
        for (offset, _) in path.match_indices('/') {
            need(
                !seen.contains(&path[..offset]),
                "source file/directory conflict",
            )?;
        }
    }
    sorted.sort_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()));
    let canonical = serde_json::to_vec(&("agentlab.source_tree.regular.v1", sorted))
        .map_err(|_| "source inventory serialization failed")?;
    Ok(format!("sha256:{}", digest(&canonical)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};
    fn request() -> Value {
        json!({"schema":"agentlab.source_material_request.v1","repositoryId":"any-repository",
            "source":{"kind":"git-http","url":"https://example.org/team/repo.git","requestedRef":"main"},
            "limits":{"acquisitionBytes":1000,"expandedBytes":2000,"fileBytes":1000,"entries":20,"depth":8,"durationSeconds":30}})
    }
    fn validate(v: Value) -> Result<(), String> {
        serde_json::from_value::<MaterialRequest>(v)
            .map_err(|_| "request decode rejected".to_owned())?
            .validate()
    }
    fn limits() -> Limits {
        serde_json::from_value(request()["limits"].clone()).unwrap()
    }
    fn file(path: &str) -> FileDeclaration {
        FileDeclaration {
            path: path.into(),
            bytes: 8,
            sha256: digest(b"source\n\n"),
            executable: false,
        }
    }
    #[test]
    fn generic_http_and_https_git_without_a_host_allowlist() {
        for url in [
            "https://example.org/team/repo.git",
            "http://code.internal:8080/project",
            "https://[2001:db8::1]/repo",
        ] {
            let mut r = request();
            r["source"]["url"] = json!(url);
            assert!(validate(r).is_ok());
        }
        let mut r = request();
        r["source"].as_object_mut().unwrap().remove("requestedRef");
        assert!(validate(r).is_ok());
    }
    #[test]
    fn local_archive_artifact_and_http_archive_are_equal_request_kinds() {
        for locator in [
            json!({"kind":"artifact","artifactId":"upload-123"}),
            json!({"kind":"http","url":"https://example.org/repo.tar.gz"}),
        ] {
            for format in ["zip", "tar", "tar.gz", "tar.zst"] {
                let mut r = request();
                r["source"] = json!({"kind":"archive","locator":locator,"format":format,"sha256":digest(b"compressed"),"bytes":10});
                assert!(validate(r).is_ok());
            }
        }
    }
    #[test]
    fn rejects_credentials_query_fragment_and_non_http_sources() {
        for url in [
            "file:///private/repo",
            "ssh://example.org/repo",
            "https://user:secret@example.org/repo",
            "https://@example.org/repo",
            "https://example.org/repo?token=secret",
            "https://example.org/repo#main",
            "https://example.org/ repo",
            "http:/repo",
            "https:///example.org/repo",
            "https://example.org\\repo",
        ] {
            let mut r = request();
            r["source"]["url"] = json!(url);
            assert!(validate(r).is_err(), "{url}");
        }
    }
    #[test]
    fn unknown_fields_types_and_claimed_git_identity_are_not_coerced() {
        let mut r = request();
        r["source"]["token"] = json!("private");
        assert!(validate(r).is_err());
        let mut r = request();
        r["source"]["commit"] = json!("a".repeat(40));
        assert!(validate(r).is_err());
        let mut r = request();
        r["limits"]["entries"] = json!("20");
        assert!(validate(r).is_err());
        let mut r = request();
        r["unexpected"] = json!(false);
        assert!(validate(r).is_err());
    }
    #[test]
    fn archive_identity_and_budget_are_required() {
        let mut r = request();
        r["source"] = json!({"kind":"archive","locator":{"kind":"artifact","artifactId":"upload-1"},"format":"zip","sha256":digest(b"packed"),"bytes":1001});
        assert!(validate(r.clone()).is_err());
        r["source"]["bytes"] = json!(1000);
        assert!(validate(r.clone()).is_ok());
        r["source"]["sha256"] = json!("not-a-hash");
        assert!(validate(r).is_err());
    }
    #[test]
    fn root_and_ref_do_not_accept_shell_or_filesystem_selection() {
        for root in [
            "../outside",
            "/absolute",
            "C:\\repo",
            "repo/.git",
            "repo//src",
        ] {
            let mut r = request();
            r["sourceRoot"] = json!(root);
            assert!(validate(r).is_err());
        }
        let mut r = request();
        r["sourceRoot"] = json!("packages/app");
        assert!(validate(r).is_ok());
        let mut r = request();
        r["source"]["requestedRef"] = json!("--upload-pack=command");
        assert!(validate(r).is_err());
    }
    #[test]
    fn declared_tree_is_order_and_transport_independent() {
        assert_eq!(
            declared_content_id(&[file("a"), file("src/b")], &limits()).unwrap(),
            declared_content_id(&[file("src/b"), file("a")], &limits()).unwrap()
        );
    }
    #[test]
    fn regular_v1_content_key_has_a_fixed_cross_language_golden() {
        assert_eq!(
            declared_content_id(&[file("a"), file("src/b")], &limits()).unwrap(),
            "sha256:d64d6f668236b5369c7b385ac1394291756ec111f67d58b0891a3174f00aaa44"
        );
    }
    #[test]
    fn changed_bytes_mode_or_path_invalidate_the_content_binding() {
        let original = declared_content_id(&[file("a")], &limits()).unwrap();
        for changed in [
            FileDeclaration {
                sha256: digest(b"changed"),
                ..file("a")
            },
            FileDeclaration {
                executable: true,
                ..file("a")
            },
            file("renamed"),
        ] {
            assert_ne!(
                original,
                declared_content_id(&[changed], &limits()).unwrap()
            );
        }
    }
    #[test]
    fn rejects_ambiguous_or_unsafe_inventory() {
        for paths in [
            vec!["a", "a"],
            vec!["a", "a/b"],
            vec!["../out"],
            vec![".git/config"],
            vec!["C:/out"],
            vec!["a\\b"],
        ] {
            assert!(declared_content_id(
                &paths.into_iter().map(file).collect::<Vec<_>>(),
                &limits()
            )
            .is_err());
        }
        let mut row = serde_json::to_value(file("a")).unwrap();
        row["linkTarget"] = json!("../../out");
        assert!(serde_json::from_value::<FileDeclaration>(row).is_err());
    }
    #[test]
    fn aggregate_file_entry_depth_and_time_budgets_are_bounded() {
        for l in [
            Limits {
                expanded_bytes: 10,
                file_bytes: 10,
                ..limits()
            },
            Limits {
                entries: 1,
                ..limits()
            },
            Limits {
                depth: 1,
                ..limits()
            },
        ] {
            assert!(declared_content_id(&[file("a"), file("src/b")], &l).is_err());
        }
        let mut l = limits();
        l.file_bytes = 7;
        assert!(declared_content_id(&[file("a")], &l).is_err());
        let mut l = limits();
        l.duration_seconds = 0;
        assert!(l.validate().is_err());
        let mut l = limits();
        l.entries = 500_001;
        assert!(l.validate().is_err());
    }
}
