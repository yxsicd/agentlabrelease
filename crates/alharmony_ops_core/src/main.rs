use std::path::PathBuf;

use alharmony_ops_core::{
    artifact_inspect, build_debug_plan, env_status, ohpm_install_plan, project_create_plan,
    project_verify,
};

fn main() {
    let mut args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" {
        usage(0);
    }
    let command = args.remove(0);
    let receipt = match command.as_str() {
        "env-status" | "harmony.env.status" => {
            let harmony_home = take_value(&mut args, "--harmony-home").map(PathBuf::from);
            env_status(harmony_home.as_deref())
        }
        "project-create-plan" | "harmony.project.create" => {
            let root = required_path(&mut args, "--project-root");
            let bundle = take_value(&mut args, "--bundle-name")
                .unwrap_or_else(|| "com.agentlab.demo".to_string());
            let label =
                take_value(&mut args, "--app-label").unwrap_or_else(|| "AgentLab Demo".to_string());
            project_create_plan(&root, &bundle, &label)
        }
        "project-verify" | "harmony.project.verify" => {
            let root = required_path(&mut args, "--project-root");
            project_verify(&root)
        }
        "ohpm-install-plan" | "harmony.ohpm.install" => {
            let root = required_path(&mut args, "--project-root");
            let harmony = required_path(&mut args, "--harmony-home");
            ohpm_install_plan(&root, &harmony)
        }
        "build-debug-plan" | "harmony.build.debug" => {
            let root = required_path(&mut args, "--project-root");
            let harmony = required_path(&mut args, "--harmony-home");
            build_debug_plan(&root, &harmony)
        }
        "artifact-inspect" | "harmony.artifact.inspect" => {
            let path = required_path(&mut args, "--artifact");
            artifact_inspect(&path)
        }
        _ => {
            eprintln!("unknown command: {command}");
            usage(2);
        }
    };
    if !args.is_empty() {
        eprintln!("unexpected arguments: {}", args.join(" "));
        std::process::exit(2);
    }
    print!("{}", receipt.to_json_pretty());
    if !receipt.ok {
        std::process::exit(1);
    }
}

fn required_path(args: &mut Vec<String>, name: &str) -> PathBuf {
    match take_value(args, name) {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("missing required argument: {name}");
            usage(2);
        }
    }
}

fn take_value(args: &mut Vec<String>, name: &str) -> Option<String> {
    let idx = args.iter().position(|arg| arg == name)?;
    args.remove(idx);
    if idx >= args.len() {
        eprintln!("{name} requires a value");
        std::process::exit(2);
    }
    Some(args.remove(idx))
}

fn usage(code: i32) -> ! {
    eprintln!(
        "usage: alharmony-ops <env-status|project-create-plan|project-verify|ohpm-install-plan|build-debug-plan|artifact-inspect> [args]\n\n\
         env-status [--harmony-home DIR]\n\
         project-create-plan --project-root DIR [--bundle-name NAME] [--app-label LABEL]\n\
         project-verify --project-root DIR\n\
         ohpm-install-plan --project-root DIR --harmony-home DIR\n\
         build-debug-plan --project-root DIR --harmony-home DIR\n\
         artifact-inspect --artifact FILE"
    );
    std::process::exit(code);
}
