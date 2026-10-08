//! Behavioral entrypoint tests. Run with rustc --test; no model or external network calls.
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "agentlab-local-contract-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        for dir in [
            "project/scripts",
            "bin",
            "knowledge",
            "project/examples/maintainer-knowledge-gate",
        ] {
            fs::create_dir_all(root.join(dir)).unwrap();
        }
        let f = Self(root.canonicalize().unwrap());
        fs::copy(
            "scripts/run-maintainer-skill-local-flywheel.sh",
            f.0.join("project/scripts/run-maintainer-skill-local-flywheel.sh"),
        )
        .unwrap();
        fs::write(f.0.join("knowledge/input"), b"original immutable cut\n").unwrap();
        fs::write(f.0.join("knowledge/assessment.json"), b"{}\n").unwrap();
        f.executable("bin/pi", "exit 99");
        f.executable(
            "bin/gate",
            r#"
printf 'gate\n' >> "$TRACE"
while test $# -gt 0; do
  case "$1" in --base) base=$2;shift 2;; --output) output=$2;shift 2;; *) shift;; esac
done
printf '{"assessmentPath":"%s/assessment.json"}\n' "$base" > "$output"
"#,
        );
        f.executable("bin/python3", r#"
case "$1" in
  scripts/maintainer-skill-tablegit.py)
    action=$2;shift 2
    printf '%s\n' "$action" >> "$TRACE"
    while test $# -gt 0; do
      case "$1" in --base) base=$2;shift 2;; --export) export_root=$2;shift 2;; --receipt) receipt=$2;shift 2;; *) shift;; esac
    done
    if test "$action" = preflight; then
      test "${REJECT_AUTHORITY:-0}" = 0 || exit 86
      printf '{"authorityVerified":true}\n' > "$receipt"
    elif test "$action" = sync; then
      printf 'export:%s\n' "$export_root" >> "$TRACE"
      mkdir -p "$export_root"
      printf 'committed successor\n' > "$export_root/input"
      printf '{}\n' > "$export_root/assessment.json"
      printf '{"revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","authorityVerified":true}\n' > "$receipt"
    else exit 87; fi;;
  examples/maintainer-knowledge-gate/agent_flywheel.py)
    shift 2
    while test $# -gt 0; do
      case "$1" in --output) output=$2;shift 2;; *) shift;; esac
    done
    printf '{"summary":{"eligible":1}}\n' > "$output";;
  examples/maintainer-knowledge-gate/case_generation_shadow.py)
    action=$2;shift 2
    printf 'shadow-%s\n' "$action" >> "$TRACE"
    while test $# -gt 0; do
      case "$1" in --output) output=$2;shift 2;; --rounds) rounds=$2;shift 2;; --receipt) receipt=$2;shift 2;; *) shift;; esac
    done
    case "$action" in
      prepare) printf '{"policy":{"shadowEligible":false}}\n' > "$output";;
      record-failure) printf '{"id":"rejected-shadow"}\n' >> "$rounds";printf '{"status":"rejected-shadow-attempt"}\n' > "$receipt";;
      *) exit 89;;
    esac;;
  scripts/materialize-skillsgit-maintainer-tree.py) printf '{}\n';;
  *) exit 88;;
esac
"#);
        f.executable(
            "project/scripts/run-maintainer-skill-agent-loop.sh",
            r#"
printf 'model-loop\n' >> "$TRACE"
mkdir -p "$2/loop/knowledge-$4"
printf '{}\n' > "$2/loop/knowledge-$4/stage-manifest.json"
printf '{}\n' > "$2/loop/knowledge-$4/assessment.json"
printf '{"completedIterations":1}\n' > "$2/loop/loop-receipt.json"
"#,
        );
        f.executable(
            "project/scripts/run-case-generation-shadow.sh",
            r#"
printf 'shadow\n' >> "$TRACE"
printf 'retained shadow diagnostic\n' >&2
exit 29
"#,
        );
        f.executable(
            "project/scripts/plan-maintainer-downstream.sh",
            r#"
printf 'downstream:%s\n' "$1" >> "$TRACE"
mkdir -p "$3"
printf '{"closedLoopQualified":false}\n' > "$3/summary.json"
"#,
        );
        f
    }
    fn executable(&self, relative: &str, body: &str) {
        use std::os::unix::fs::PermissionsExt;
        let path = self.0.join(relative);
        fs::write(&path, format!("#!/bin/bash\nset -eu\n{body}\n")).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
    }
    fn run(&self, iterations: &str, env: &[(&str, &str)]) -> Output {
        let mut cmd = Command::new("/bin/bash");
        cmd.arg("scripts/run-maintainer-skill-local-flywheel.sh")
            .arg(self.0.join("knowledge"))
            .arg(
                env.iter()
                    .find(|(k, _)| *k == "FIXTURE_RUN_ROOT")
                    .map(|(_, value)| PathBuf::from(value))
                    .unwrap_or_else(|| self.0.join("run")),
            )
            .arg("arbitrary-repository")
            .arg(iterations)
            .arg(self.0.join("bin/pi"))
            .current_dir(self.0.join("project"))
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    self.0.join("bin").display(),
                    std::env::var("PATH").unwrap()
                ),
            )
            .env("TRACE", self.0.join("trace"))
            .env("AGENTLAB_FLYWHEEL_GATE", self.0.join("bin/gate"))
            .env("AGENTLAB_LM_GATEWAY_URL", "http://gateway.invalid")
            .env("AGENTLAB_LM_GATEWAY_KEY", "fixture-not-a-secret")
            .env("AGENTLAB_MODEL", "fixture-model")
            .env("AGENTLAB_PROVIDER_ROUTE", "fixture-route")
            .env("AGENTLAB_TABLEGIT_MCP_URL", "http://table.invalid")
            .env("AGENTLAB_TABLEGIT_PERSON_ID", "fixture-person")
            .env("AGENTLAB_RUN_ID", "fixture-run")
            .env("AGENTLAB_SCOPE_BATCH_SIZE", "1")
            .env_remove("AGENTLAB_SKILLSGIT_ROOT")
            .env_remove("AGENTLAB_SKILLSGIT_REVISION")
            .env_remove("AGENTLAB_MAX_ITERATIONS")
            .env_remove("AGENTLAB_SHADOW_SAMPLE");
        for (name, value) in env {
            cmd.env(name, value);
        }
        cmd.output().unwrap()
    }
    fn trace(&self) -> String {
        fs::read_to_string(self.0.join("trace")).unwrap_or_default()
    }
}

#[test]
fn nested_output_cannot_write_inside_cut_or_public_checkout() {
    for nested in ["knowledge/new-run", "project/new-run"] {
        let f = Fixture::new();
        let output = f.0.join(nested);
        let out = f.run("1", &[("FIXTURE_RUN_ROOT", output.to_str().unwrap())]);
        assert_eq!(out.status.code(), Some(2), "{:?}", out);
        assert!(f.trace().is_empty());
        assert!(!output.exists());
        assert!(!f.0.join("knowledge/sources").exists());
        assert!(!f.0.join("project/sources").exists());
        assert_eq!(
            fs::read(f.0.join("knowledge/input")).unwrap(),
            b"original immutable cut\n"
        );
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn source_cache_links_and_external_git_metadata_stop_before_budget() {
    use std::os::unix::fs::symlink;
    for kind in ["root", "slot", "git-link", "git-file"] {
        let f = Fixture::new();
        let sources = f.0.join("sources");
        let slot = sources.join("repository-revision");
        match kind {
            "root" => symlink(f.0.join("knowledge"), &sources).unwrap(),
            "slot" => {
                fs::create_dir(&sources).unwrap();
                symlink(f.0.join("knowledge"), &slot).unwrap();
            }
            "git-link" => {
                fs::create_dir_all(&slot).unwrap();
                symlink(f.0.join("knowledge"), slot.join(".git")).unwrap();
            }
            _ => {
                fs::create_dir_all(&slot).unwrap();
                fs::write(slot.join(".git"), b"gitdir: /external/worktree\n").unwrap();
            }
        }
        let out = f.run("1", &[]);
        assert_eq!(out.status.code(), Some(2), "{kind}: {:?}", out);
        assert!(f.trace().is_empty());
        assert!(!f.0.join("run").exists());
        assert_eq!(
            fs::read(f.0.join("knowledge/input")).unwrap(),
            b"original immutable cut\n"
        );
    }
}

#[test]
fn stale_authority_stops_before_model_or_write() {
    let f = Fixture::new();
    let out = f.run("1", &[("REJECT_AUTHORITY", "1")]);
    assert_eq!(out.status.code(), Some(86), "{:?}", out);
    assert_eq!(f.trace(), "preflight\n");
    assert_eq!(
        fs::read(f.0.join("knowledge/input")).unwrap(),
        b"original immutable cut\n"
    );
}

#[test]
fn bounded_default_preserves_input_and_consumes_committed_successor_without_hidden_shadow() {
    let f = Fixture::new();
    let out = f.run("1", &[]);
    assert!(out.status.success(), "{:?}", out);
    let trace = f.trace();
    assert!(
        trace.starts_with("preflight\ngate\nmodel-loop\ngate\nsync\n"),
        "{trace}"
    );
    assert!(trace.contains(&format!("export:{}/run/committed-knowledge", f.0.display())));
    assert!(f.0.join("run/committed-next-round-plan.json").is_file());
    assert!(fs::read_to_string(f.0.join("run/downstream/summary.json"))
        .unwrap()
        .contains("blocked-case-inputs"));
    assert!(!trace.contains("shadow\n"));
    assert_eq!(
        fs::read(f.0.join("knowledge/input")).unwrap(),
        b"original immutable cut\n"
    );
    assert!(f.0.join("run/local-flywheel-receipt.json").is_file());
    assert!(f.0.join("run/tablegit-preflight-receipt.json").is_file());
}

#[test]
fn optional_shadow_failure_retains_committed_success_and_raw_failure() {
    let f = Fixture::new();
    let out = f.run("1", &[("AGENTLAB_SHADOW_SAMPLE", "1")]);
    assert!(out.status.success(), "{:?}", out);
    assert!(f.trace().contains("shadow\n"));
    let receipt = fs::read_to_string(f.0.join("run/shadow-status.json")).unwrap();
    assert!(
        receipt.contains("29") && receipt.contains("failed"),
        "{receipt}"
    );
    assert_eq!(
        fs::read_to_string(f.0.join("run/shadow-stderr.log")).unwrap(),
        "retained shadow diagnostic\n"
    );
    assert!(f.0.join("run/local-flywheel-receipt.json").is_file());
    assert_eq!(
        fs::read(f.0.join("knowledge/input")).unwrap(),
        b"original immutable cut\n"
    );
}

#[test]
fn converge_missing_materialization_contract_stops_before_budget() {
    let f = Fixture::new();
    let out = f.run("converge", &[]);
    assert!(!out.status.success());
    assert!(f.trace().is_empty());
    assert!(!f.0.join("run").exists());
}

#[test]
fn reused_run_root_is_rejected_without_changes() {
    let f = Fixture::new();
    fs::create_dir(f.0.join("run")).unwrap();
    fs::write(f.0.join("run/retained"), b"old failed evidence\n").unwrap();
    let out = f.run("1", &[]);
    assert!(!out.status.success());
    assert!(f.trace().is_empty());
    assert_eq!(fs::read_dir(f.0.join("run")).unwrap().count(), 1);
    assert_eq!(
        fs::read(f.0.join("run/retained")).unwrap(),
        b"old failed evidence\n"
    );
}

#[test]
fn invalid_budgets_stop_before_run_creation() {
    for env in [
        [("AGENTLAB_SCOPE_BATCH_SIZE", "5")],
        [("AGENTLAB_SHADOW_SAMPLE", "yes")],
    ] {
        let f = Fixture::new();
        assert!(!f.run("1", &env).status.success());
        assert!(f.trace().is_empty());
        assert!(!f.0.join("run").exists());
    }
    let f = Fixture::new();
    assert!(!f.run("4", &[]).status.success());
    assert!(f.trace().is_empty());
    assert!(!f.0.join("run").exists());
}

#[test]
fn actual_shadow_entrypoint_refuses_missing_lineage_before_model_budget() {
    let f = Fixture::new();
    fs::copy(
        "scripts/run-case-generation-shadow.sh",
        f.0.join("project/scripts/run-case-generation-shadow.sh"),
    )
    .unwrap();
    let out = f.run("1", &[("AGENTLAB_SHADOW_SAMPLE", "1")]);
    assert!(out.status.success(), "{:?}", out);
    assert!(!f.trace().contains("shadow-prepare"));
    assert!(fs::read_to_string(f.0.join("run/shadow-status.json"))
        .unwrap()
        .contains('3'));
    assert!(fs::read_to_string(f.0.join("run/shadow-stderr.log"))
        .unwrap()
        .contains("shadow lineage is absent"));
}

#[test]
fn actual_shadow_records_only_in_run_evidence_and_preserves_selected_lineage() {
    let f = Fixture::new();
    fs::copy(
        "scripts/run-case-generation-shadow.sh",
        f.0.join("project/scripts/run-case-generation-shadow.sh"),
    )
    .unwrap();
    let lineage = f.0.join("knowledge");
    let rounds = b"{\"id\":\"round-one\"}\n";
    fs::write(lineage.join("case_generation_rounds.jsonl"), rounds).unwrap();
    fs::write(lineage.join("case_generation_candidates.jsonl"), b"[]\n").unwrap();
    let out = f.run(
        "1",
        &[
            ("AGENTLAB_SHADOW_SAMPLE", "1"),
            ("AGENTLAB_SHADOW_LINEAGE_ROOT", lineage.to_str().unwrap()),
        ],
    );
    assert!(out.status.success(), "{:?}", out);
    assert!(f
        .trace()
        .contains("shadow-prepare\nshadow-record-failure\n"));
    assert_eq!(
        fs::read(lineage.join("case_generation_rounds.jsonl")).unwrap(),
        rounds
    );
    assert!(fs::read_to_string(
        f.0.join("run/shadow-case-generation/case_generation_rounds.jsonl")
    )
    .unwrap()
    .contains("rejected-shadow"));
    assert!(!f
        .0
        .join("run/committed-knowledge/case_generation_rounds.jsonl")
        .exists());
}

#[test]
fn real_shadow_lineage_validator_rejects_bad_indices_ids_json_and_drift() {
    let script = std::env::current_dir()
        .unwrap()
        .join("examples/maintainer-knowledge-gate/case_generation_shadow.py");
    let code = r#"
import importlib.util,json,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('shadow',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    rounds=root/'case_generation_rounds.jsonl';candidates=root/'case_generation_candidates.jsonl'
    candidates.write_text('{"id":"candidate-one"}\n')
    good='{"id":"round-one","roundIndex":1}\n'
    for bad in ['invalid-json\n','[]\n','{"id":"round-one"}\n',
                '{"id":"round-one","roundIndex":true}\n',
                '{"id":"round-one","roundIndex":1,"qualification":[]}\n',
                '{"id":"round-one","roundIndex":2}\n',good+good]:
        rounds.write_text(bad)
        try: module.validate_lineage(root)
        except (ValueError,TypeError): pass
        else: raise AssertionError('malformed lineage admitted')
    rounds.write_text(good)
    retained,existing,binding=module.validate_lineage(root)
    assert retained[0]['roundIndex']==1 and existing[0]['id']=='candidate-one'
    request={'caseLineageInputsSha256':binding}
    module.verify_lineage_binding(request,root)
    candidates.write_text('{"id":"other-candidate"}\n')
    try: module.verify_lineage_binding(request,root)
    except ValueError as error: assert 'changed' in str(error)
    else: raise AssertionError('changed lineage admitted')
print('real lineage parsing, shape, identity, budget and drift gate passed')
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(script)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}

#[test]
fn configured_invalid_skillsgit_stops_before_model_and_authority() {
    let f = Fixture::new();
    f.executable("bin/python3", "exit 85");
    let out = f.run(
        "1",
        &[
            ("AGENTLAB_SKILLSGIT_ROOT", "/absent/skills"),
            (
                "AGENTLAB_SKILLSGIT_REVISION",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
        ],
    );
    assert_eq!(out.status.code(), Some(85));
    assert!(f.trace().is_empty());
    assert!(!f.0.join("run").exists());
}

#[test]
fn pinned_native_tools_stage_both_assets_and_refuse_missing_drift_links_and_overrides() {
    let code = r#"
import hashlib,importlib.util,io,json,os,sys,tarfile,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('prepare',Path(sys.argv[1])/'scripts/prepare-participant-runtime.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
driver_spec=importlib.util.spec_from_file_location('driver',Path(sys.argv[1])/'scripts/run-pi-in-docker.py')
driver=importlib.util.module_from_spec(driver_spec);driver_spec.loader.exec_module(driver)
def sha(value):return hashlib.sha256(value).hexdigest()
assets={};specs={}
for name in ['rg','fd']:
    binary=('fixture binary '+name).encode();buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for filename,value in [(name+'/bin',binary),(name+'/LICENSE',b'fixture license'),('../never-extract',b'unadmitted')]:
            member=tarfile.TarInfo(filename);member.size=len(value);tar.addfile(member,io.BytesIO(value))
    url='https://github.com/fixture/'+name+'/releases/download/v1/fixture.tar.gz'
    assets[url]=buf.getvalue();specs[name]={'version':'fixture','url':url,'archiveSha256':sha(assets[url]),
        'member':name+'/bin','binarySha256':sha(binary),'licenses':['LICENSE'],
        'noticeSha256':{'LICENSE':sha(b'fixture license')}}
class Response(io.BytesIO):
    def geturl(self):return 'https://github.com/fixture'
helper.native_tools_specs=lambda architecture:specs
helper.urllib.request.urlopen=lambda url,timeout:Response(assets[url])
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);runtime=root/'runtime';runtime.mkdir()
    state=root/'state';workspace=root/'workspace';case=root/'case'
    for path in [state,workspace,case]:path.mkdir()
    (runtime/'package-lock.json').write_text('fixture-lock');(case/'manifest.json').write_text('{}')
    config={'piRuntimeRoot':str(runtime),'caseInputRoot':str(case),'runtimePurpose':'synthetic-transport-only',
            'piPackageLockSha256':sha((runtime/'package-lock.json').read_bytes()),
            'participantManifestSha256':sha((case/'manifest.json').read_bytes()),'runtimeUser':'fixture',
            'imageId':'fixture'}
    assert '--read-only' in driver.docker_base(config,workspace,state,'fixture')
    for writable_workspace,writable_state in [(runtime,state),(root,state),(workspace,runtime),
                                               (case,state),(workspace,case),(state,root),(state,state)]:
        try:driver.docker_base(config,writable_workspace,writable_state,'fixture')
        except RuntimeError as error:assert 'overlap' in str(error) or 'disjoint' in str(error)
        else:raise AssertionError('writable alias to an immutable input accepted')
    driver.native_tool_override_guard(state)
    (state/'bin').symlink_to(runtime)
    try:driver.native_tool_override_guard(state)
    except RuntimeError as error:assert 'override' in str(error)
    else:raise AssertionError('state/bin override accepted')
    try:helper.native_tools_binding(runtime,'amd64')
    except ValueError as error:assert 'absent' in str(error)
    else:raise AssertionError('missing tools accepted')
    original=specs['fd']['archiveSha256'];specs['fd']['archiveSha256']='0'*64
    try:helper.install_native_tools(runtime,'amd64')
    except ValueError as error:assert 'archive digest differs' in str(error)
    else:raise AssertionError('bad archive accepted')
    assert not (runtime/'bin').exists() and not (runtime/'native-tool-licenses').exists()
    specs['fd']['archiveSha256']=original
    binding=helper.install_native_tools(runtime,'amd64')
    assert set(binding['binaries'])=={'rg','fd'} and not (root/'never-extract').exists()
    assert helper.install_native_tools(runtime,'amd64')==binding
    notice=runtime/'native-tool-licenses/rg/LICENSE';notice.chmod(0o644);notice.write_bytes(b'');notice.chmod(0o444)
    try:helper.native_tools_binding(runtime,'amd64')
    except ValueError as error:assert 'official license content drifted' in str(error)
    else:raise AssertionError('new baseline accepted altered official notice')
    notice.chmod(0o644);notice.write_bytes(b'fixture license');notice.chmod(0o444)
    (runtime/'bin/rg').chmod(0o755)
    try:helper.native_tools_binding(runtime,'amd64')
    except ValueError as error:assert 'immutable' in str(error)
    else:raise AssertionError('writable tool accepted')
    (runtime/'bin/rg').chmod(0o555)
    (runtime/'bin/fd').unlink();(runtime/'bin/fd').symlink_to(runtime/'bin/rg')
    try:helper.native_tools_binding(runtime,'amd64')
    except ValueError as error:assert 'non-symlink' in str(error)
    else:raise AssertionError('tool link accepted')
    (runtime/'bin/fd').unlink();(runtime/'bin/fd').write_bytes(b'changed');(runtime/'bin/fd').chmod(0o555)
    try:helper.native_tools_binding(runtime,'amd64')
    except ValueError as error:assert 'binary drifted' in str(error)
    else:raise AssertionError('binary drift accepted')
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(std::env::current_dir().unwrap())
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}

#[test]
fn explicit_supervisor_profile_binds_whole_plugin_tree_and_keeps_discovery_disabled() {
    let root = std::env::current_dir().unwrap();
    let code = r#"
import importlib.util,json,os,sys,tempfile
from pathlib import Path
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
repo=Path(sys.argv[1]);helper=load('prepare',repo/'scripts/prepare-participant-runtime.py')
module=load('participant',repo/'examples/real-code-agent/participant.py')
driver=load('driver',repo/'scripts/run-pi-in-docker.py')
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);runtime=root/'runtime';plugin=runtime/'node_modules/@bermudi/pi-delegate'
    plugin.mkdir(parents=True);(plugin/'src').mkdir()
    (plugin/'package.json').write_text('{"name":"@bermudi/pi-delegate","version":"0.4.0"}')
    (plugin/'delegate.ts').write_text('fixture only; never executed\n')
    nested=plugin/'src/execution.ts';nested.write_text('first fixture tree\n')
    profile=helper.supervisor_profile(runtime)
    config=root/'runtime.json';config.write_text(json.dumps({'piRuntimeRoot':str(runtime),'piSupervisor':profile}))
    evidence=root/'evidence';evidence.mkdir()
    os.environ.update(AGENTLAB_LM_GATEWAY_KEY='synthetic-only',AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=str(config),
        AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=str(root/'receipts'),DOCKER_CONFIG=str(root/'empty-config'))
    participant=module.Participant(evidence,root/'state','/bin/true','http://localhost','fixture-model')
    def no_execution(*args,**kwargs):raise RuntimeError('fixture stops before any native/model execution')
    participant._run_turn=no_execution
    try:
        try:participant.turn('supervisor',root,prompt='fixture task')
        except RuntimeError:pass
        else:raise AssertionError('fixture unexpectedly executed')
        command=json.loads((evidence/'supervisor-command.json').read_text())
        assert '--no-extensions' in command and '--no-mcp' in command and '--offline' in command
        assert command[command.index('--extension')+1]=='/runtime/node_modules/@bermudi/pi-delegate/delegate.ts'
        assert command[command.index('--tools')+1]=='read,delegate,delegate_ticket,delegate_session'
        settings=json.loads((root/'state/settings.json').read_text())
        assert not settings['retry']['enabled'] and not settings['compaction']['enabled']
        assert json.loads((root/'state/delegate.json').read_text())['surface']=='full'
        assert profile['childPolicy']['conversationIsolationOnly']
        assert not profile['childPolicy']['parentChildFilesystemIsolationQualified']
        args=command[1:];args[args.index('--session')+1]='/agent/sessions/operator/pi-session.jsonl'
        binding=driver.supervisor_launch_binding({'piSupervisor':profile},root/'state',args)
        assert set(binding['effectiveSettingsSha256'])=={'settings.json','delegate.json'}
        for changed in [args+['-e','unreviewed.ts'],args[:-1]+['--system-prompt=unreviewed'],args[:-1]+['@/agent/settings.json'],
                        [item for item in args if item!='--no-mcp']]:
            try:driver.supervisor_launch_binding({'piSupervisor':profile},root/'state',changed)
            except RuntimeError:pass
            else:raise AssertionError('broader supervisor argv accepted')
        changed=args.copy();changed[changed.index('--tools')+1]='read,bash,delegate'
        try:driver.supervisor_launch_binding({'piSupervisor':profile},root/'state',changed)
        except RuntimeError:pass
        else:raise AssertionError('broader parent tools accepted')
        policy=root/'state/delegate.json';original=policy.read_bytes()
        drift=json.loads(original);drift['models']={'explore':'unreviewed/model'};policy.write_text(json.dumps(drift))
        try:driver.supervisor_launch_binding({'piSupervisor':profile},root/'state',args)
        except RuntimeError as error:assert 'policy drifted' in str(error)
        else:raise AssertionError('effective settings drift accepted')
        policy.write_bytes(original);policy.unlink();policy.symlink_to(root/'state/settings.json')
        try:driver.supervisor_launch_binding({'piSupervisor':profile},root/'state',args)
        except RuntimeError as error:assert 'non-symlink' in str(error)
        else:raise AssertionError('settings symlink accepted')
    finally:participant.close()
    nested.write_text('drift in imported nested code\n')
    assert helper.supervisor_profile(runtime)['packageTreeSha256']!=profile['packageTreeSha256']
    try:module.Participant(evidence,root/'refused-state','/bin/true','http://localhost','fixture-model')
    except ValueError as error:assert 'binding differs' in str(error)
    else:raise AssertionError('nested plugin drift accepted')
    assert not (root/'refused-state').exists()
    nested.unlink();nested.symlink_to(root/'runtime.json')
    try:helper.supervisor_profile(runtime)
    except ValueError as error:assert 'unsafe link' in str(error)
    else:raise AssertionError('plugin symlink accepted')
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(root)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}

#[test]
fn real_skillsgit_preflight_rejects_nonexecutable_entrypoint_without_writes() {
    let script = std::env::current_dir()
        .unwrap()
        .join("scripts/materialize-skillsgit-maintainer-tree.py");
    let code = r#"
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('materializer',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);repo=root/'skills';repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(repo),'-c','user.name=fixture','-c','user.email=fixture@example.invalid',*args],stderr=subprocess.DEVNULL).decode().strip()
    git('init','-q')
    for name in module.CORE_SKILLS:
        path=repo/'.agents/skills'/name/'SKILL.md';path.parent.mkdir(parents=True);path.write_text('fixture\n')
    scripts=repo/'scripts';scripts.mkdir()
    apply=scripts/'apply-pack.sh';apply.write_text('#!/bin/sh\nexit 0\n');apply.chmod(0o644)
    validate=scripts/'validate-mst.sh';validate.write_text('#!/bin/sh\nexit 0\n');validate.chmod(0o755)
    def run():
        git('add','.');git('commit','-qm','fixture')
        return subprocess.run([sys.executable,sys.argv[1],'--knowledge',str(root/'absent-input'),
            '--repository','arbitrary','--skillsgit-root',str(repo),'--skillsgit-revision',git('rev-parse','HEAD'),
            '--check-inputs-only'],capture_output=True,text=True)
    result=run()
    assert result.returncode!=0 and 'not executable' in result.stderr
    assert not (root/'absent-input').exists()
    apply.chmod(0o755);result=run()
    assert result.returncode==0,result.stderr
    receipt=json.loads(result.stdout)
    assert receipt['inputsValid'] and not receipt['writesPerformed'] and not receipt['qualified']
    assert git('status','--porcelain')=='' and not (root/'absent-input').exists()
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(script)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}

#[test]
fn real_chunk_header_and_trailer_drips_are_interrupted_at_absolute_deadline() {
    let script = std::env::current_dir()
        .unwrap()
        .join("examples/real-code-agent/participant.py");
    let code = r#"
import http.server,importlib.util,json,os,sys,tempfile,threading,time,urllib.request
from pathlib import Path
spec=importlib.util.spec_from_file_location('participant',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
mode='header';stop=threading.Event()
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
        try:
            if mode=='trailer':self.wfile.write(b'1\r\nx\r\n0\r\nX-Drip: ');self.wfile.flush()
            while not stop.is_set():
                self.wfile.write(b'0' if mode=='header' else b'x');self.wfile.flush();time.sleep(0.04)
        except (BrokenPipeError,ConnectionResetError):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);os.environ['AGENTLAB_LM_GATEWAY_KEY']='synthetic-fixture-only'
        for mode in ('header','trailer'):
            evidence=root/mode;evidence.mkdir()
            participant=module.Participant(evidence,root/(mode+'-state'),'/bin/true',
                f'http://127.0.0.1:{server.server_port}','fixture-model',gateway_timeout_seconds=30)
            # Shorten only this fixture's interval; production policy still admits 30..240.
            participant.gateway_timeout_seconds=2
            started=time.monotonic()
            request=urllib.request.Request(f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions',
                data=b'{"stream":true}')
            with urllib.request.urlopen(request,timeout=5) as response:response.read()
            participant.close()
            assert time.monotonic()-started<4,'chunked parser escaped absolute deadline'
            receipt=json.loads((evidence/'gateway/0001.status.json').read_bytes())
            assert receipt['outcome']=='upstream_deadline_exceeded',receipt
            assert receipt['upstreamDeadlineExceeded'] and receipt['upstreamDeadlinePhase']=='response_body'
            assert not receipt['upstreamEof'] and not receipt['semanticComplete']
            assert (evidence/'gateway/0001.response').read_bytes()==(b'' if mode=='header' else b'x')
finally:
    stop.set();server.shutdown();server.server_close();thread.join()
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(script)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}

#[test]
fn real_gateway_client_backpressure_cannot_hang_close_or_discard_capture() {
    let participant = std::env::current_dir()
        .unwrap()
        .join("examples/real-code-agent/participant.py");
    let code = r#"
import http.server,importlib.util,json,os,socket,sys,tempfile,threading,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('participant',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
payload=b'data: '+json.dumps({'choices':[{'delta':{'content':'x'*32768}}]}).encode()+b'\n\n'
terminal=b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
body=payload*256+terminal
class Upstream(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        try: self.wfile.write(body)
        except OSError: pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream)
threading.Thread(target=server.serve_forever,daemon=True).start()
os.environ['AGENTLAB_LM_GATEWAY_KEY']='fixture-not-a-production-secret'
os.environ.pop('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG',None)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);evidence=root/'evidence';evidence.mkdir()
    p=module.Participant(evidence,root/'state','/unused/pi',f'http://127.0.0.1:{server.server_port}','fixture',gateway_timeout_seconds=30)
    client=socket.socket();client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024)
    client.connect(('127.0.0.1',p.server.server_port))
    request=b'{"model":"fixture","stream":true,"messages":[]}'
    client.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Length: '+str(len(request)).encode()+b'\r\n\r\n'+request)
    # Deliberately keep the client connected without consuming a single byte.
    status=evidence/'gateway/0001.status.json';deadline=time.monotonic()+18
    while not status.exists() and time.monotonic()<deadline: time.sleep(.05)
    assert status.exists(),'downstream backpressure exceeded retained-capture deadline'
    result=json.loads(status.read_bytes())
    assert result['clientDisconnected'] and result['clientWriteTimedOut'],result
    assert result['upstreamEof'] and result['semanticComplete'] and result['outcome']=='completed',result
    assert (evidence/'gateway/0001.response').read_bytes()==body
    started=time.monotonic();p.close();assert time.monotonic()-started<2
    client.close()
server.shutdown();server.server_close()
print('real blocked client bounded, full upstream bytes retained, close completed')
"#;
    let out = Command::new("python3")
        .args(["-c", code])
        .arg(participant)
        .output()
        .unwrap();
    assert!(out.status.success(), "{:?}", out);
}
