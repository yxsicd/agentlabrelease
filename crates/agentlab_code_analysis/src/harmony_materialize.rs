//! Fixed-source benchmark reference materialization, not a general refactoring engine.
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, process::Command};

const PIN: &str = "7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6";
fn git(source: &Path, args: &[&str]) -> Result<String, Box<dyn std::error::Error>> {
    let out = Command::new("git")
        .arg("-C")
        .arg(source)
        .args(args)
        .output()?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).into_owned().into());
    }
    Ok(String::from_utf8(out.stdout)?)
}
fn copy(from: &Path, to: &Path) -> std::io::Result<()> {
    fs::create_dir_all(to)?;
    for entry in fs::read_dir(from)? {
        let e = entry?;
        let target = to.join(e.file_name());
        if e.file_type()?.is_dir() {
            copy(&e.path(), &target)?;
        } else {
            fs::copy(e.path(), target)?;
        }
    }
    Ok(())
}
fn section<'a>(
    text: &'a str,
    begin: &str,
    end: &str,
) -> Result<&'a str, Box<dyn std::error::Error>> {
    let start = text.find(begin).ok_or("Missing fixed-source section")?;
    let finish = start + text[start..].find(end).ok_or("Missing fixed-source end")?;
    Ok(&text[start..finish])
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 4 {
        return Err("usage: agentlab-harmony-materialize SOURCE OUTPUT SEED".into());
    }
    let source = Path::new(&args[1]);
    let root = Path::new(&args[2]);
    if git(source, &["rev-parse", "HEAD"])?.trim() != PIN {
        return Err("Source cut differs from benchmark pin".into());
    }
    if root.exists() {
        return Err("Use a fresh output root; prior evidence is retained".into());
    }
    fs::create_dir_all(root)?;
    let tree = root.join("patched-source");
    fs::create_dir(&tree)?;
    let archive = root.join("source.tar");
    let file = fs::File::create(&archive)?;
    let status = Command::new("git")
        .arg("-C")
        .arg(source)
        .args(["archive", PIN])
        .stdout(file)
        .status()?;
    if !status.success() {
        return Err("git archive failed".into());
    }
    if !Command::new("tar")
        .arg("-xf")
        .arg(&archive)
        .arg("-C")
        .arg(&tree)
        .status()?
        .success()
    {
        return Err("source extraction failed".into());
    }
    let feedback_path = "common/src/main/ets/component/FeedbackSheet.ets";
    let navigation_path = "common/src/main/ets/routermanager/PageContext.ets";
    let caller_path = "features/devpractices/src/main/ets/view/PracticeHomeView.ets";
    let feedback = git(source, &["show", &format!("{PIN}:{feedback_path}")])?;
    let original_submit = section(
        &feedback,
        "  private handleSubmit(): void",
        "  private handleVoteClick(",
    )?;
    let submit=original_submit.replace("if (!this.feedbackData.canSubmit)","if (this.submitting || !this.feedbackData.canSubmit)")
        .replace("    SubmitInfoUtil.submitFeedbackInfo","    this.submitting = true;\n    this.submitError = '';\n    SubmitInfoUtil.submitFeedbackInfo")
        .replace("      });","      }).catch((err: Error) => {\n        this.submitError = err.message;\n      }).finally(() => {\n        this.submitting = false;\n      });");
    let patched_feedback=feedback.replace(original_submit,&submit)
        .replace("  @Prop feedbackInitParams:","  @State submitting: boolean = false;\n  @State submitError: string = '';\n  @Prop feedbackInitParams:")
        .replace("        Button($r('app.string.submit'))","        if (this.submitError !== '') {\n          Text(this.submitError)\n        }\n        Button($r('app.string.submit'))")
        .replace("          .opacity(this.feedbackData.canSubmit", "          .enabled(!this.submitting)\n          .opacity(this.feedbackData.canSubmit");
    let navigation = git(source, &["show", &format!("{PIN}:{navigation_path}")])?;
    let patched_navigation = navigation.replace(": void", ": boolean").replace(
        "    } catch (err) {",
        "      return true;\n    } catch (err) {",
    );
    let patched_navigation = patched_navigation
        .lines()
        .map(|line| {
            if line.trim_start().starts_with("Logger.error(TAG,") {
                format!("{line}\n      return false;")
            } else {
                line.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    let caller = git(source, &["show", &format!("{PIN}:{caller_path}")])?;
    let patched_caller=caller.replace("  scroller: Scroller", "  @State navigationFailed: boolean = false;\n  scroller: Scroller")
        .replace("    this.samplePageContext.replacePage(","    this.navigationFailed = !this.samplePageContext.replacePage(")
        .replace("HdsNavigation(this.samplePageContext.navPathStack) {\n    }","HdsNavigation(this.samplePageContext.navPathStack) {\n      if (this.navigationFailed) {\n        Text('Navigation failed; retry by reopening this view')\n      }\n    }");
    let mut patches = Vec::new();
    let loading_path = "common/src/main/ets/view/DelayedLoadingView.ets";
    let breakpoint_path = "common/src/main/ets/util/BreakpointSystem.ets";
    let loading = git(source, &["show", &format!("{PIN}:{loading_path}")])?;
    let breakpoint = git(source, &["show", &format!("{PIN}:{breakpoint_path}")])?;
    let patched_loading=loading.replace("  aboutToAppear(): void {", "  aboutToAppear(): void {\n    if (this.delayTimer !== -1) { clearTimeout(this.delayTimer); }\n    this.showLoading = false;");
    let patched_breakpoint=breakpoint.replace("    return this.lg;", "    if (currentBreakpoint === WidthBreakpoint.WIDTH_LG) { return this.lg; }\n    return this.sm;");
    let debounce_path = "common/src/main/ets/util/DebounceUtil.ets";
    let debounce = git(source, &["show", &format!("{PIN}:{debounce_path}")])?;
    let patched_debounce = debounce
        .replace("  private static lastClickTime: number = 0;", "")
        .replace(
            "    return () => {",
            "    let lastClickTime: number = -Infinity;\n    return () => {",
        )
        .replace("DebounceUtil.lastClickTime", "lastClickTime")
        .replace(
            "        lastClickTime = now;\n        return;",
            "        return;",
        );
    let url_path = "common/src/main/ets/util/UrlUtil.ets";
    let url_source = git(source, &["show", &format!("{PIN}:{url_path}")])?;
    let old_url = section(
        &url_source,
        "  public static isNetUrl(",
        "  public static maskUrl(",
    )?;
    let patched_url = url_source.replace(old_url, r#"  public static isNetUrl(value: string): boolean {
    if (typeof value !== 'string' || /\s/.test(value) || !/^https?:\/\//i.test(value)) {
      return false;
    }
    try {
      const parsed = url.URL.parseURL(value);
      return parsed.hostname.length > 0 && (parsed.protocol === 'http:' || parsed.protocol === 'https:');
    } catch {
      return false;
    }
  }

"#);
    let mut reference_patch = String::new();
    for (name, original, patched) in [
        (debounce_path, &debounce, &patched_debounce),
        (url_path, &url_source, &patched_url),
        (feedback_path, &feedback, &patched_feedback),
        (navigation_path, &navigation, &patched_navigation),
        (caller_path, &caller, &patched_caller),
        (loading_path, &loading, &patched_loading),
        (breakpoint_path, &breakpoint, &patched_breakpoint),
    ] {
        let before = root.join("before").join(name);
        fs::create_dir_all(before.parent().ok_or("Before path")?)?;
        fs::write(&before, original)?;
        fs::write(tree.join(name), patched)?;
        let analysis = agentlab_code_analysis::analyze(name, patched.as_bytes(), PIN)?;
        if analysis.has_errors {
            return Err(format!("Patched grammar error: {name}").into());
        }
        let diff = Command::new("git")
            .args(["diff", "--no-index", "--"])
            .arg(&before)
            .arg(tree.join(name))
            .output()?;
        if diff.status.code() != Some(1) {
            return Err("Expected a concrete source patch".into());
        }
        let text = String::from_utf8(diff.stdout)?
            .replace(
                &format!("a/{}", before.display().to_string().trim_start_matches('/')),
                &format!("a/{name}"),
            )
            .replace(
                &format!(
                    "b/{}",
                    tree.join(name)
                        .display()
                        .to_string()
                        .trim_start_matches('/')
                ),
                &format!("b/{name}"),
            );
        reference_patch.push_str(&text);
        patches.push(json!({"path":name,"beforeSha256":format!("{:x}",Sha256::digest(original.as_bytes())),"afterSha256":format!("{:x}",Sha256::digest(patched.as_bytes()))}));
    }
    fs::write(root.join("reference.patch"), reference_patch)?;
    let project = root.join("workspace/hello");
    copy(Path::new(&args[3]), &project)?;
    let ets = project.join("entry/src/main/ets");
    fs::create_dir_all(ets.join("routermanager"))?;
    fs::create_dir_all(ets.join("model"))?;
    fs::create_dir_all(ets.join("util"))?;
    fs::write(
        ets.join("routermanager/PageContext.ets"),
        &patched_navigation,
    )?;
    for name in [
        "model/PageEnum.ets",
        "model/FeedbackData.ets",
        "util/Logger.ets",
    ] {
        fs::write(
            ets.join(name),
            git(
                source,
                &["show", &format!("{PIN}:common/src/main/ets/{name}")],
            )?,
        )?;
    }
    let resets = section(
        &feedback,
        "  private resetSubmitStatus(): void",
        "  @Builder",
    )?;
    let license = section(&feedback, "/*", "import ")?;
    let page=format!("{license}\nimport {{ FeedbackData, FeedbackInitParams, FeedbackType }} from '../model/FeedbackData';\nimport {{ PageContext }} from '../routermanager/PageContext';\nimport {{ PageEnum }} from '../model/PageEnum';\nimport {{ SubmitInfoUtil, Toast }} from '../util/BenchmarkSubmit';\n@Entry\n@Component\nstruct Index {{\n  @State feedbackData: FeedbackData = new FeedbackData();\n  @State feedbackListState: boolean[] = [true, false];\n  @State feedbackInitParams: FeedbackInitParams = new FeedbackInitParams();\n  @State bindFeedback: boolean = true;\n  @State submitting: boolean = false;\n  @State submitError: string = '';\n  @State navigationFailed: boolean = false;\n  pageContext: PageContext = new PageContext();\n  aboutToAppear(): void {{\n    this.feedbackData.canSubmit = true;\n    this.feedbackData.listSelected = true;\n    this.feedbackData.feedbackTypeStatus = FeedbackType.LIKE;\n  }}\n{submit}\n{resets}\n  build() {{\n    Column() {{\n      Text('Harmony Controller Slice Verified')\n      Text(this.submitting ? 'Submitting' : 'Ready')\n      if (this.submitError !== '') {{ Text(this.submitError) }}\n      Button('Submit / retry').enabled(!this.submitting).onClick(() => {{ this.handleSubmit(); }})\n      Button('Navigate').onClick(() => {{\n        this.navigationFailed = !this.pageContext.replacePage({{ routerName: PageEnum.PRACTICES_VIEW }}, false);\n      }})\n      if (this.navigationFailed) {{ Text('Navigation failed') }}\n    }}\n  }}\n}}\n");
    fs::write(ets.join("pages/Index.ets"), page)?;
    fs::write(
        ets.join("util/BenchmarkSubmit.ets"),
        r#"import { FeedbackData, FeedbackInitParams } from '../model/FeedbackData';
export class SubmitInfoUtil {
  public static failNext: boolean = true;
  public static submitFeedbackInfo(params: FeedbackInitParams, data: FeedbackData, selected: boolean[]): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      setTimeout(() => {
        if (SubmitInfoUtil.failNext) {
          SubmitInfoUtil.failNext = false;
          reject(new Error('Controlled failure; retry'));
        } else { resolve(); }
      }, 100);
    });
  }
}
export class Toast { public static showToast(message: ResourceStr): void { console.info('Benchmark toast'); } }
"#,
    )?;
    let strings = project.join("entry/src/main/resources/base/element/string.json");
    let mut resources: serde_json::Value = serde_json::from_str(&fs::read_to_string(&strings)?)?;
    for name in ["feedback_reason"] {
        resources["string"]
            .as_array_mut()
            .ok_or("String resources")?
            .push(json!({"name":name,"value":"Select a reason"}));
    }
    fs::write(strings, serde_json::to_string_pretty(&resources)?)?;
    fs::write(
        root.join("materialization.json"),
        serde_json::to_string_pretty(&json!({
            "schema":"agentlab.harmony_controller_materialization.v1","sourceRevision":PIN,"patches":patches,
            "wholeProject":"patched-source","sliceProject":"workspace/hello","sliceMarker":"Harmony Controller Slice Verified",
            "sliceOriginals":["PageContext","PageEnum","FeedbackData","Logger","handleSubmit","resetSubmitStatus","resetAllStatus"],
            "adapters":["Minimal host UI replaces full FeedbackSheet and HdsNavigation caller UI","Deferred benchmark submit replaces demonstration backend","Toast is an explicit logging stub"],
            "fullSourceBuildQualified":false,"deviceInteractionQualified":false,"subjectAgentRun":false
        }))?,
    )?;
    Ok(())
}
