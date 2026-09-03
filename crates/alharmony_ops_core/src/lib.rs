//! AgentLab Harmony engineering atomic-operation core.
//!
//! This crate is the base Harmony project/build layer.  It absorbs the
//! operation/receipt discipline from asrelease while keeping Web2Atomic as an
//! upper pipeline.

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

pub const RECEIPT_SCHEMA: &str = "agentlab.harmony_ops.receipt.v1";
pub const SOURCE_REPOSITORY: &str = "https://github.com/yxsorg/asrelease.git";
pub const SOURCE_REF: &str = "origin/main";
pub const SOURCE_COMMIT: &str = "374ab3cf2bdd3c31418997adfdd1aaa13ac8f550";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SideEffect {
    ReadOnly,
    WorkspaceWrite,
    LocalProcess,
    DeviceWrite,
    ExternalWrite,
}

impl SideEffect {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ReadOnly => "read-only",
            Self::WorkspaceWrite => "workspace-write",
            Self::LocalProcess => "local-process",
            Self::DeviceWrite => "device-write",
            Self::ExternalWrite => "external-write",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RecoveryOwner {
    Agent,
    User,
    Environment,
    None,
}

impl RecoveryOwner {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Agent => "agent",
            Self::User => "user",
            Self::Environment => "environment",
            Self::None => "none",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Receipt {
    pub operation: &'static str,
    pub ok: bool,
    pub side_effect: SideEffect,
    pub next_action: Option<&'static str>,
    pub recovery_owner: RecoveryOwner,
    pub diagnostics: Vec<String>,
    pub evidence: BTreeMap<String, JsonValue>,
}

impl Receipt {
    pub fn new(operation: &'static str, side_effect: SideEffect) -> Self {
        Self {
            operation,
            ok: true,
            side_effect,
            next_action: None,
            recovery_owner: RecoveryOwner::None,
            diagnostics: Vec::new(),
            evidence: BTreeMap::new(),
        }
    }

    pub fn blocked(
        operation: &'static str,
        side_effect: SideEffect,
        owner: RecoveryOwner,
        diagnostic: impl Into<String>,
        next_action: Option<&'static str>,
    ) -> Self {
        let mut receipt = Self::new(operation, side_effect);
        receipt.ok = false;
        receipt.recovery_owner = owner;
        receipt.diagnostics.push(diagnostic.into());
        receipt.next_action = next_action;
        receipt
    }

    pub fn evidence(mut self, key: impl Into<String>, value: JsonValue) -> Self {
        self.evidence.insert(key.into(), value);
        self
    }

    pub fn diagnostic(mut self, value: impl Into<String>) -> Self {
        self.diagnostics.push(value.into());
        self
    }

    pub fn next(mut self, value: &'static str) -> Self {
        self.next_action = Some(value);
        self
    }

    pub fn to_json_pretty(&self) -> String {
        let mut out = String::new();
        out.push_str("{\n");
        field(
            &mut out,
            1,
            "schema",
            &JsonValue::String(RECEIPT_SCHEMA.into()),
            true,
        );
        field(
            &mut out,
            1,
            "operation",
            &JsonValue::String(self.operation.into()),
            true,
        );
        field(&mut out, 1, "ok", &JsonValue::Bool(self.ok), true);
        field(
            &mut out,
            1,
            "sideEffect",
            &JsonValue::String(self.side_effect.as_str().into()),
            true,
        );
        match self.next_action {
            Some(value) => field(
                &mut out,
                1,
                "nextAction",
                &JsonValue::String(value.into()),
                true,
            ),
            None => field(&mut out, 1, "nextAction", &JsonValue::Null, true),
        }
        field(
            &mut out,
            1,
            "recoveryOwner",
            &JsonValue::String(self.recovery_owner.as_str().into()),
            true,
        );
        field(
            &mut out,
            1,
            "diagnostics",
            &JsonValue::Array(
                self.diagnostics
                    .iter()
                    .cloned()
                    .map(JsonValue::String)
                    .collect(),
            ),
            true,
        );
        field(
            &mut out,
            1,
            "evidence",
            &JsonValue::Object(self.evidence.clone()),
            false,
        );
        out.push_str("}\n");
        out
    }
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Number(i128),
    String(String),
    Array(Vec<JsonValue>),
    Object(BTreeMap<String, JsonValue>),
}

impl JsonValue {
    pub fn string(value: impl Into<String>) -> Self {
        Self::String(value.into())
    }
}

pub fn env_status(harmony_home: Option<&Path>) -> Receipt {
    let root = harmony_home
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("ALHARMONY_HOME").map(PathBuf::from))
        .or_else(|| std::env::var_os("HARMONY_HOME").map(PathBuf::from))
        .or_else(|| std::env::var_os("AGENTLAB_HARMONY_HOME").map(PathBuf::from));

    let Some(root) = root else {
        return Receipt::blocked(
            "harmony.env.status",
            SideEffect::ReadOnly,
            RecoveryOwner::Environment,
            "Harmony home is not configured; pass --harmony-home or set ALHARMONY_HOME/HARMONY_HOME/AGENTLAB_HARMONY_HOME.",
            None,
        );
    };

    let mut commands = BTreeMap::new();
    let candidates = [
        ("hvigorw", root.join("bin/hvigorw")),
        ("ohpm", root.join("bin/ohpm")),
        ("hdc", root.join("sdk/default/openharmony/toolchains/hdc")),
    ];
    for (name, path) in candidates {
        let mut item = BTreeMap::new();
        item.insert("path".into(), JsonValue::string(path.display().to_string()));
        item.insert("exists".into(), JsonValue::Bool(path.is_file()));
        commands.insert(name.into(), JsonValue::Object(item));
    }
    let ok = commands.values().all(|v| match v {
        JsonValue::Object(map) => matches!(map.get("exists"), Some(JsonValue::Bool(true))),
        _ => false,
    });
    let mut receipt = Receipt::new("harmony.env.status", SideEffect::ReadOnly)
        .evidence("harmonyHome", JsonValue::string(root.display().to_string()))
        .evidence("commands", JsonValue::Object(commands));
    if ok {
        receipt.next_action = Some("harmony.project.create");
    } else {
        receipt.ok = false;
        receipt.recovery_owner = RecoveryOwner::Environment;
        receipt
            .diagnostics
            .push("Required Harmony CLI/SDK paths are missing.".into());
    }
    receipt
}

pub fn project_create_plan(project_root: &Path, bundle_name: &str, app_label: &str) -> Receipt {
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert("bundleName".into(), JsonValue::string(bundle_name));
    evidence.insert("appLabel".into(), JsonValue::string(app_label));
    evidence.insert("plannedOnly".into(), JsonValue::Bool(true));
    Receipt::new("harmony.project.create", SideEffect::WorkspaceWrite)
        .evidence("plan", JsonValue::Object(evidence))
        .diagnostic("P0 skeleton emits a deterministic project-create plan; template materialization will be added after receipt gates are stable.")
        .next("harmony.project.verify")
}

pub fn project_verify(project_root: &Path) -> Receipt {
    let required = [
        "AppScope/app.json5",
        "build-profile.json5",
        "entry/build-profile.json5",
        "entry/hvigorfile.ts",
        "entry/oh-package.json5",
        "entry/src/main/module.json5",
        "hvigorfile.ts",
        "oh-package.json5",
    ];
    let mut files = BTreeMap::new();
    let mut ok = true;
    for rel in required {
        let exists = project_root.join(rel).is_file();
        ok &= exists;
        files.insert(rel.into(), JsonValue::Bool(exists));
    }
    let mut receipt = Receipt::new("harmony.project.verify", SideEffect::ReadOnly)
        .evidence(
            "projectRoot",
            JsonValue::string(project_root.display().to_string()),
        )
        .evidence("requiredFiles", JsonValue::Object(files));
    if ok {
        receipt.next_action = Some("harmony.ohpm.install");
    } else {
        receipt.ok = false;
        receipt.recovery_owner = RecoveryOwner::Agent;
        receipt
            .diagnostics
            .push("Project is missing required Harmony project files.".into());
        receipt.next_action = Some("harmony.project.create");
    }
    receipt
}

pub fn ohpm_install_plan(project_root: &Path, harmony_home: &Path) -> Receipt {
    command_plan(
        "harmony.ohpm.install",
        SideEffect::LocalProcess,
        project_root,
        harmony_home.join("bin/ohpm"),
        &["install"],
        Some("harmony.build.debug"),
    )
}

pub fn build_debug_plan(project_root: &Path, harmony_home: &Path) -> Receipt {
    command_plan(
        "harmony.build.debug",
        SideEffect::LocalProcess,
        project_root,
        harmony_home.join("bin/hvigorw"),
        &["assembleHap", "--mode", "module", "-p", "product=default"],
        Some("harmony.artifact.inspect"),
    )
}

fn command_plan(
    operation: &'static str,
    side_effect: SideEffect,
    project_root: &Path,
    command: PathBuf,
    args: &[&str],
    next: Option<&'static str>,
) -> Receipt {
    let mut cmd = BTreeMap::new();
    cmd.insert(
        "cwd".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    cmd.insert(
        "command".into(),
        JsonValue::string(command.display().to_string()),
    );
    let command_exists = command.is_file();
    let project_root_exists = project_root.is_dir();
    cmd.insert("exists".into(), JsonValue::Bool(command_exists));
    cmd.insert(
        "projectRootExists".into(),
        JsonValue::Bool(project_root_exists),
    );
    cmd.insert(
        "args".into(),
        JsonValue::Array(args.iter().map(|s| JsonValue::string(*s)).collect()),
    );
    cmd.insert("plannedOnly".into(), JsonValue::Bool(true));
    cmd.insert("timeoutSeconds".into(), JsonValue::Number(600));
    cmd.insert("maxOutputBytes".into(), JsonValue::Number(65536));
    let mut receipt =
        Receipt::new(operation, side_effect).evidence("commandPlan", JsonValue::Object(cmd));
    receipt.next_action = next;
    if !command_exists {
        receipt.ok = false;
        receipt.recovery_owner = RecoveryOwner::Environment;
        receipt
            .diagnostics
            .push("Required Harmony command is missing; run harmony.env.status.".into());
        receipt.next_action = Some("harmony.env.status");
    } else if !project_root_exists {
        receipt.ok = false;
        receipt.recovery_owner = RecoveryOwner::Agent;
        receipt.diagnostics.push("Project root does not exist; create or select a valid Harmony project before planning a local process operation.".into());
        receipt.next_action = Some("harmony.project.create");
    }
    receipt
}

pub fn artifact_inspect(path: &Path) -> Receipt {
    match fs::metadata(path) {
        Ok(meta) if meta.is_file() => {
            let extension = path.extension().and_then(|s| s.to_str()).unwrap_or("");
            let mut evidence = BTreeMap::new();
            evidence.insert("path".into(), JsonValue::string(path.display().to_string()));
            evidence.insert("bytes".into(), JsonValue::Number(meta.len() as i128));
            evidence.insert("extension".into(), JsonValue::string(extension));
            evidence.insert(
                "supportedHarmonyArtifact".into(),
                JsonValue::Bool(matches!(extension, "hap" | "app" | "har" | "hsp")),
            );
            let mut receipt = Receipt::new("harmony.artifact.inspect", SideEffect::ReadOnly)
                .evidence("artifact", JsonValue::Object(evidence));
            if matches!(extension, "hap" | "app" | "har" | "hsp") {
                receipt.next_action = None;
            } else {
                receipt.ok = false;
                receipt.recovery_owner = RecoveryOwner::Agent;
                receipt
                    .diagnostics
                    .push("Artifact extension is not one of hap/app/har/hsp.".into());
                receipt.next_action = Some("harmony.build.debug");
            }
            receipt
        }
        _ => Receipt::blocked(
            "harmony.artifact.inspect",
            SideEffect::ReadOnly,
            RecoveryOwner::Agent,
            "Artifact file does not exist.",
            Some("harmony.build.debug"),
        ),
    }
}

fn field(out: &mut String, indent: usize, key: &str, value: &JsonValue, comma: bool) {
    write_indent(out, indent);
    let _ = write!(out, "\"{}\": ", escape(key));
    write_json(out, value, indent);
    if comma {
        out.push(',');
    }
    out.push('\n');
}

fn write_json(out: &mut String, value: &JsonValue, indent: usize) {
    match value {
        JsonValue::Null => out.push_str("null"),
        JsonValue::Bool(v) => out.push_str(if *v { "true" } else { "false" }),
        JsonValue::Number(v) => {
            let _ = write!(out, "{}", v);
        }
        JsonValue::String(v) => {
            let _ = write!(out, "\"{}\"", escape(v));
        }
        JsonValue::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push_str("[\n");
            for (index, item) in items.iter().enumerate() {
                write_indent(out, indent + 1);
                write_json(out, item, indent + 1);
                if index + 1 != items.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            write_indent(out, indent);
            out.push(']');
        }
        JsonValue::Object(map) => {
            if map.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (index, (key, item)) in map.iter().enumerate() {
                write_indent(out, indent + 1);
                let _ = write!(out, "\"{}\": ", escape(key));
                write_json(out, item, indent + 1);
                if index + 1 != map.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            write_indent(out, indent);
            out.push('}');
        }
    }
}

fn write_indent(out: &mut String, indent: usize) {
    for _ in 0..indent {
        out.push_str("  ");
    }
}

fn escape(input: &str) -> String {
    let mut out = String::new();
    for ch in input.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn receipt_json_has_contract_fields() {
        let json = Receipt::new("harmony.env.status", SideEffect::ReadOnly).to_json_pretty();
        assert!(json.contains("agentlab.harmony_ops.receipt.v1"));
        assert!(json.contains("harmony.env.status"));
        assert!(json.contains("\"sideEffect\": \"read-only\""));
    }

    #[test]
    fn missing_env_is_fail_closed() {
        std::env::remove_var("ALHARMONY_HOME");
        std::env::remove_var("HARMONY_HOME");
        std::env::remove_var("AGENTLAB_HARMONY_HOME");
        let receipt = env_status(None);
        assert!(!receipt.ok);
        assert_eq!(receipt.recovery_owner, RecoveryOwner::Environment);
    }

    #[test]
    fn command_plans_fail_when_project_root_is_missing() {
        let dir = std::env::temp_dir().join(format!("alharmony-sdk-test-{}", std::process::id()));
        let sdk = dir.join("sdk");
        fs::create_dir_all(sdk.join("bin")).unwrap();
        fs::write(sdk.join("bin/ohpm"), b"").unwrap();
        fs::write(sdk.join("bin/hvigorw"), b"").unwrap();
        let missing_project = dir.join("missing-project");

        let ohpm = ohpm_install_plan(&missing_project, &sdk);
        let build = build_debug_plan(&missing_project, &sdk);

        fs::remove_dir_all(&dir).ok();
        assert!(!ohpm.ok);
        assert_eq!(ohpm.recovery_owner, RecoveryOwner::Agent);
        assert_eq!(ohpm.next_action, Some("harmony.project.create"));
        assert!(!build.ok);
        assert_eq!(build.recovery_owner, RecoveryOwner::Agent);
        assert_eq!(build.next_action, Some("harmony.project.create"));
    }

    #[test]
    fn artifact_inspect_accepts_hap_extension() {
        let dir = std::env::temp_dir().join(format!("alharmony-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("demo.hap");
        fs::write(&path, b"demo").unwrap();
        let receipt = artifact_inspect(&path);
        fs::remove_file(&path).ok();
        fs::remove_dir(&dir).ok();
        assert!(receipt.ok);
        assert_eq!(receipt.operation, "harmony.artifact.inspect");
    }
}
