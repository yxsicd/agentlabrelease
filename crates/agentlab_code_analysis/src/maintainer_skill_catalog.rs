use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    process::Command,
};

#[derive(Clone)]
struct FileEntry {
    path: String,
    oid: String,
}

fn value(args: &[String], name: &str) -> Result<String, String> {
    let index = args
        .iter()
        .position(|arg| arg == name)
        .ok_or_else(|| format!("missing {name}"))?;
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("missing value for {name}"))
}

fn git(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| format!("run git in {}: {error}", root.display()))?;
    if !output.status.success() {
        return Err(format!(
            "git {:?} failed in {}: {}",
            args,
            root.display(),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(output.stdout)
}

fn slug(value: &str) -> String {
    let result = value
        .bytes()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() {
                (byte as char).to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("-");
    if result.is_empty() {
        "root".to_owned()
    } else {
        result
    }
}

fn extension(path: &str) -> String {
    Path::new(path)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("no-extension")
        .to_ascii_lowercase()
}

fn is_source(path: &str) -> bool {
    matches!(
        extension(path).as_str(),
        "ets"
            | "ts"
            | "js"
            | "java"
            | "kt"
            | "cpp"
            | "cc"
            | "c"
            | "h"
            | "hpp"
            | "html"
            | "css"
            | "scss"
    )
}

fn is_test(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    lower.contains("/ohostest/")
        || lower.contains("/test/")
        || lower.contains("/tests/")
        || lower.contains(".test.")
        || lower.contains(".spec.")
        || lower.contains("e2e-spec")
}

fn source_text(root: &Path, path: &str) -> Option<String> {
    String::from_utf8(fs::read(root.join(path)).ok()?).ok()
}

fn quoted_value(text: &str) -> Option<String> {
    let start = text.find(&['\'', '"'][..])?;
    let quote = text.as_bytes()[start];
    let tail = &text[start + 1..];
    let end = tail.bytes().position(|byte| byte == quote)?;
    Some(tail[..end].to_owned())
}

fn dependency_signals(text: &str, extension: &str, output: &mut BTreeSet<String>) {
    for line in text.lines() {
        let trimmed = line.trim();
        let dependency = if matches!(extension, "ets" | "ts" | "js") {
            trimmed
                .split_once(" from ")
                .and_then(|(_, tail)| quoted_value(tail))
                .or_else(|| trimmed.strip_prefix("import ").and_then(quoted_value))
        } else if matches!(extension, "java" | "kt") {
            trimmed
                .strip_prefix("import ")
                .map(|value| value.trim_end_matches(';').to_owned())
        } else if matches!(extension, "c" | "cc" | "cpp" | "h" | "hpp") {
            trimmed
                .strip_prefix("#include <")
                .and_then(|value| value.strip_suffix('>'))
                .map(str::to_owned)
        } else {
            None
        };
        if let Some(dependency) = dependency.filter(|value| !value.starts_with('.')) {
            output.insert(dependency);
        }
    }
}

fn documentation(root: &Path, members: &[FileEntry]) -> (Option<String>, Option<String>) {
    let readme = members.iter().find(|member| {
        Path::new(&member.path)
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|name| name.to_ascii_lowercase().starts_with("readme"))
    });
    let Some(text) = readme.and_then(|member| source_text(root, &member.path)) else {
        return (None, None);
    };
    let title = text
        .lines()
        .map(str::trim)
        .find_map(|line| line.strip_prefix("# ").filter(|value| !value.is_empty()))
        .map(str::to_owned);
    let purpose = text
        .lines()
        .map(str::trim)
        .find(|line| {
            !line.is_empty()
                && !line.starts_with('#')
                && !line.starts_with('!')
                && !line.starts_with('<')
                && !line.starts_with("[![")
        })
        .map(|line| line.chars().take(500).collect());
    (title, purpose)
}

fn entries(root: &Path) -> Result<Vec<FileEntry>, String> {
    let output = git(root, &["ls-tree", "-r", "-z", "HEAD"])?;
    let mut result = Vec::new();
    for record in output
        .split(|byte| *byte == 0)
        .filter(|row| !row.is_empty())
    {
        let text = std::str::from_utf8(record).map_err(|error| error.to_string())?;
        let (metadata, path) = text
            .split_once('\t')
            .ok_or_else(|| "invalid git ls-tree record".to_owned())?;
        let mut fields = metadata.split_whitespace();
        let _mode = fields.next();
        let kind = fields.next();
        let oid = fields.next();
        if kind == Some("blob") {
            result.push(FileEntry {
                path: path.to_owned(),
                oid: oid.unwrap_or_default().to_owned(),
            });
        }
    }
    Ok(result)
}

fn guide_projects(files: &[FileEntry]) -> BTreeSet<String> {
    files
        .iter()
        .filter(|file| file.path.ends_with("build-profile.json5"))
        .filter_map(|file| {
            let parts: Vec<_> = file.path.split('/').collect();
            match parts.len() {
                2 => Some(parts[0].to_owned()),
                n if n >= 3 => Some(format!("{}/{}", parts[0], parts[1])),
                _ => None,
            }
        })
        .collect()
}

fn boundary(strategy: &str, path: &str, guide_roots: &BTreeSet<String>) -> (String, &'static str) {
    let parts: Vec<_> = path.split('/').collect();
    match strategy {
        "harmony-multi-product-modules" => {
            if parts.first() == Some(&"features") || parts.first() == Some(&"products") {
                if parts.len() >= 2 {
                    (format!("{}/{}", parts[0], parts[1]), "module")
                } else {
                    (parts[0].to_owned(), "support")
                }
            } else if parts.len() >= 2 {
                (parts[0].to_owned(), "module")
            } else {
                (".".to_owned(), "repository-support")
            }
        }
        "harmony-sample-project-corpus" => {
            let two = (parts.len() >= 2).then(|| format!("{}/{}", parts[0], parts[1]));
            if let Some(root) = two.filter(|root| guide_roots.contains(root)) {
                (root, "sample-project")
            } else if parts
                .first()
                .is_some_and(|root| guide_roots.contains(*root))
            {
                (parts[0].to_owned(), "sample-project")
            } else if parts.len() >= 2 {
                (format!("{}/_support", parts[0]), "domain-support")
            } else {
                (".".to_owned(), "repository-support")
            }
        }
        "harmony-small-app-source-units" => {
            if path.starts_with("entry/src/main/ets/") && path.ends_with(".ets") {
                (path.to_owned(), "source-unit")
            } else if path.starts_with("entry/src/main/resources/") {
                ("entry/src/main/resources".to_owned(), "resources")
            } else if path.starts_with("AppScope/") {
                ("AppScope".to_owned(), "application-scope")
            } else if path.starts_with("screenshots/") {
                ("screenshots".to_owned(), "documentation")
            } else if path.starts_with("entry/") {
                ("entry/_build".to_owned(), "module-build")
            } else {
                (".".to_owned(), "repository-support")
            }
        }
        "cordova-plugin-monorepo" => {
            let first = parts.first().copied().unwrap_or(".");
            if first == "cordova-plugin-hms-iap" {
                let suffix = if path.starts_with("cordova-plugin-hms-iap/example/cordova/") {
                    "example/cordova"
                } else if path.starts_with("cordova-plugin-hms-iap/example/ionic/") {
                    "example/ionic"
                } else if path.starts_with("cordova-plugin-hms-iap/src/android/") {
                    "src/android"
                } else if path.starts_with("cordova-plugin-hms-iap/src/www/") {
                    "src/www"
                } else if path.starts_with("cordova-plugin-hms-iap/ionic-native/") {
                    "ionic-native"
                } else if path.starts_with("cordova-plugin-hms-iap/hooks/") {
                    "hooks"
                } else if path.starts_with("cordova-plugin-hms-iap/types/") {
                    "types"
                } else if path.starts_with("cordova-plugin-hms-iap/www/") {
                    "www"
                } else {
                    "_package"
                };
                (format!("cordova-plugin-hms-iap/{suffix}"), "iap-layer")
            } else if first.starts_with("cordova-plugin-") {
                (first.to_owned(), "plugin")
            } else if parts.len() >= 2 {
                (first.to_owned(), "repository-support")
            } else {
                (".".to_owned(), "repository-support")
            }
        }
        _ => (".".to_owned(), "repository-support"),
    }
}

fn responsibility(strategy: &str, kind: &str, boundary: &str) -> String {
    match (strategy, kind) {
        (_, "sample-project") => format!("Maintain the independently buildable Harmony sample rooted at {boundary}; keep its modules, tests, resources, and SDK contract together."),
        (_, "domain-support") => format!("Maintain shared documentation or support assets for the {} sample domain without treating them as an application.", boundary.trim_end_matches("/_support")),
        (_, "source-unit") => format!("Maintain the application behavior owned by {boundary} and its callers, state transitions, and IAP contract."),
        (_, "plugin") => format!("Maintain the complete Cordova plugin package rooted at {boundary}, including JS/TS, native bridge, metadata, examples, and generated distributions."),
        (_, "iap-layer") => format!("Maintain the Cordova IAP layer {boundary} and its cross-layer contract with adjacent IAP scope Skills."),
        (_, "module") => format!("Maintain the Harmony module rooted at {boundary}, including its build manifest, source, resources, and tests."),
        _ if boundary == "." => "Maintain repository-wide build, policy, documentation, and release support files.".to_owned(),
        _ => format!("Maintain the tracked repository support boundary {boundary}."),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let spec_path = PathBuf::from(value(&args, "--source-spec")?);
    let output = PathBuf::from(value(&args, "--output")?);
    let summary_path = PathBuf::from(value(&args, "--summary")?);
    let spec: Value = serde_json::from_slice(&fs::read(&spec_path)?)?;
    let mut roots = BTreeMap::new();
    let mut index = 0;
    while let Some(position) = args[index..].iter().position(|arg| arg == "--repository") {
        let actual = index + position;
        let binding = args.get(actual + 1).ok_or("missing --repository value")?;
        let (id, path) = binding
            .split_once('=')
            .ok_or("--repository must be id=path")?;
        roots.insert(id.to_owned(), PathBuf::from(path));
        index = actual + 2;
        if index >= args.len() {
            break;
        }
    }
    let mut rows = Vec::new();
    let mut repository_summaries = Vec::new();
    for repository in spec["repositories"]
        .as_array()
        .ok_or("source spec has no repositories")?
    {
        let id = repository["id"].as_str().ok_or("repository has no id")?;
        let revision = repository["revision"]
            .as_str()
            .ok_or("repository has no revision")?;
        let strategy = repository["strategy"]
            .as_str()
            .ok_or("repository has no strategy")?;
        let root = roots
            .get(id)
            .ok_or_else(|| format!("no checkout bound for {id}"))?;
        let head = String::from_utf8(git(root, &["rev-parse", "HEAD"])?)?
            .trim()
            .to_owned();
        if head != revision {
            return Err(format!("{id} revision differs: {head}").into());
        }
        let tree_oid = String::from_utf8(git(root, &["rev-parse", "HEAD^{tree}"])?)?
            .trim()
            .to_owned();
        let files = entries(root)?;
        let guide_roots = if strategy == "harmony-sample-project-corpus" {
            guide_projects(&files)
        } else {
            BTreeSet::new()
        };
        let mut groups: BTreeMap<(String, &str), Vec<FileEntry>> = BTreeMap::new();
        for file in files.iter().cloned() {
            let key = boundary(strategy, &file.path, &guide_roots);
            groups.entry(key).or_default().push(file);
        }
        let scope_skill_count = groups.len();
        let mut repository_source_files = 0usize;
        let mut repository_code_lines = 0usize;
        let mut repository_test_files = 0usize;
        let mut repository_dependencies = BTreeSet::new();
        for ((path, kind), members) in groups {
            let mut languages = BTreeMap::<String, usize>::new();
            let mut builds = Vec::new();
            let mut tests = Vec::new();
            let mut source_files = 0usize;
            let mut code_lines = 0usize;
            let mut dependencies = BTreeSet::new();
            for member in &members {
                *languages.entry(extension(&member.path)).or_default() += 1;
                if is_source(&member.path) {
                    source_files += 1;
                    if let Some(text) = source_text(root, &member.path) {
                        code_lines += text.lines().count();
                        dependency_signals(&text, &extension(&member.path), &mut dependencies);
                    }
                }
                if member.path.ends_with("build-profile.json5")
                    || member.path.ends_with("package.json")
                    || member.path.ends_with("plugin.xml")
                    || member.path.ends_with("CMakeLists.txt")
                {
                    builds.push(member.path.clone());
                }
                if is_test(&member.path) {
                    tests.push(member.path.clone());
                }
            }
            let (documented_title, documented_purpose) = documentation(root, &members);
            let dependency_count = dependencies.len();
            repository_source_files += source_files;
            repository_code_lines += code_lines;
            repository_test_files += tests.len();
            repository_dependencies.extend(dependencies.iter().cloned());
            let dependencies: Vec<_> = dependencies.into_iter().take(100).collect();
            let evidence: Vec<_> = members
                .iter()
                .take(3)
                .map(|member| json!({"path":member.path,"gitBlobOid":member.oid}))
                .collect();
            rows.push(json!({
                "schema":"agentlab.maintainer_scope_skill.v1",
                "id":format!("skill-scope-{}-{}", slug(id), slug(&path)),
                "skillLayer":"instance",
                "stage":"repository-scope",
                "assetClass":"reusable-knowledge",
                "status":"source-supported",
                "repositoryId":id,
                "repository":repository["repository"],
                "sourceRevision":revision,
                "sourceTreeOid":tree_oid,
                "strategy":strategy,
                "kind":kind,
                "pathBoundary":path,
                "responsibility":responsibility(strategy, kind, &path),
                "documentedTitle":documented_title,
                "documentedPurpose":documented_purpose,
                "trackedFileCount":members.len(),
                "sourceFileCount":source_files,
                "codeLineCount":code_lines,
                "testFileCount":tests.len(),
                "languages":languages,
                "externalDependencyCount":dependency_count,
                "externalDependencies":dependencies,
                "buildEntrypoints":builds,
                "testEntrypoints":tests,
                "evidence":evidence,
                "coverage":"all tracked files under this leaf boundary are assigned exactly once",
                "automaticPromotion":false
            }));
        }
        repository_summaries.push(json!({
            "repositoryId":id,
            "revision":revision,
            "treeOid":tree_oid,
            "strategy":strategy,
            "trackedFileCount":files.len(),
            "sourceFileCount":repository_source_files,
            "codeLineCount":repository_code_lines,
            "testFileCount":repository_test_files,
            "externalDependencyCount":repository_dependencies.len(),
            "assignedFileCount":files.len(),
            "unassignedFileCount":0,
            "scopeSkillCount":scope_skill_count,
            "sampleProjectRootCount":guide_roots.len()
        }));
    }
    rows.sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
    let jsonl = rows
        .iter()
        .map(|row| serde_json::to_string(row).unwrap() + "\n")
        .collect::<String>();
    let summary = json!({
        "schema":"agentlab.maintainer_skill_catalog_summary.v1",
        "sourceSpecSha256":digest(&fs::read(&spec_path)?),
        "catalogSha256":digest(jsonl.as_bytes()),
        "repositoryCount":repository_summaries.len(),
        "scopeSkillCount":rows.len(),
        "repositories":repository_summaries,
        "trackedFilesAssignedExactlyOnce":true,
        "automaticPromotion":false
    });
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut catalog = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output)?;
    catalog.write_all(jsonl.as_bytes())?;
    let mut summary_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&summary_path)?;
    summary_file.write_all(&serde_json::to_vec_pretty(&summary)?)?;
    summary_file.write_all(b"\n")?;
    println!("{}", serde_json::to_string(&summary)?);
    Ok(())
}
