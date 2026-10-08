//! Run on a disposable Linux-x64 consumer: <binary> <controller> <public-fixture> <pinned-image>.
//! Uses only public bytes; touches one absent fixture volume and its exact test containers.
use std::collections::BTreeSet;
use std::path::Path;
use std::process::{Command, Output};

const VOLUME: &str = "vol-agentlab-pack-controller-qualification-90496dc0-linux-x64-42368ff87f09";
const DIGEST: &str = "42368ff87f09d406f3a6c4169a70c9bcbf353ba730de303d7b7fa6b60103826d";

fn run(program: &str, args: &[&str]) -> Output {
    Command::new(program)
        .args(args)
        .output()
        .expect("execute bounded qualification command")
}
fn ok(program: &str, args: &[&str]) -> String {
    let result = run(program, args);
    assert!(
        result.status.success(),
        "{} {:?}: {}",
        program,
        args,
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8(result.stdout).unwrap()
}
fn ids(args: &[&str]) -> BTreeSet<String> {
    ok("docker", args).lines().map(str::to_string).collect()
}
fn fingerprint(image: &str) -> String {
    ok("docker", &["run", "--rm", "--pull=never", "--network=none", "--entrypoint", "sh",
        "--mount", &format!("type=volume,source={VOLUME},target=/probe,readonly,volume-nocopy"), image,
        "-ceu", "cat /probe/probe.txt /probe/.agentlab-pack/READY /probe/.agentlab-pack/manifest.json; stat -c '%i:%s:%a:%y:%z' /probe/probe.txt /probe/.agentlab-pack /probe/.agentlab-pack/READY /probe/.agentlab-pack/manifest.json"])
}
fn install(control: &str, fixture: &str, image: &str) -> Output {
    Command::new(control)
        .args(["pack", "install-docker", fixture])
        .env("AGENTLAB_PACK_INSTALL_IMAGE", image)
        .output()
        .unwrap()
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(
        args.len(),
        4,
        "usage: acceptance <controller> <public-fixture> <pinned-image>"
    );
    let (control, fixture, image) = (&args[1], &args[2], &args[3]);
    assert!(Path::new(control).is_absolute() && Path::new(fixture).is_absolute());
    assert_eq!(ok(control, &["digest", fixture]).trim(), DIGEST);
    let containers = ids(&[
        "container",
        "ls",
        "--all",
        "--no-trunc",
        "--format",
        "{{.ID}}",
    ]);
    let volumes = ids(&["volume", "ls", "--format", "{{.Name}}"]);
    let images = ids(&["image", "ls", "--all", "--quiet", "--no-trunc"]);
    assert!(
        !volumes.contains(VOLUME),
        "fixture namespace must be absent; do not overwrite historical state"
    );
    let first = install(control, fixture, image);
    assert!(
        first.status.success(),
        "cold install: {}",
        String::from_utf8_lossy(&first.stderr)
    );
    let first_receipt = String::from_utf8(first.stdout).unwrap();
    assert!(first_receipt.contains(VOLUME) && first_receipt.contains(DIGEST));
    let expected = fingerprint(image);
    assert!(expected.starts_with("agentlab native controller immutable fixture\n"));

    let ro_name = format!("agentlab-controller-ro-90496dc0-{}", std::process::id());
    let ro = ok(
        "docker",
        &[
            "create",
            "--name",
            &ro_name,
            "--pull=never",
            "--network=none",
            "--entrypoint",
            "sleep",
            "--mount",
            &format!("type=volume,source={VOLUME},target=/probe,readonly,volume-nocopy"),
            image,
            "300",
        ],
    );
    let ro = ro.trim();
    assert_eq!(ro.len(), 64);
    ok("docker", &["start", ro]);
    let second = install(control, fixture, image);
    assert!(
        second.status.success(),
        "active RO reuse: {}",
        String::from_utf8_lossy(&second.stderr)
    );
    assert_eq!(String::from_utf8(second.stdout).unwrap(), first_receipt);
    assert_eq!(
        fingerprint(image),
        expected,
        "read-only reuse changed payload or metadata"
    );
    assert_eq!(
        ok("docker", &["inspect", "--format", "{{.State.Running}}", ro]).trim(),
        "true"
    );

    let rw_name = format!("agentlab-controller-rw-90496dc0-{}", std::process::id());
    let rw = ok(
        "docker",
        &[
            "create",
            "--name",
            &rw_name,
            "--pull=never",
            "--network=none",
            "--entrypoint",
            "sleep",
            "--mount",
            &format!("type=volume,source={VOLUME},target=/probe,volume-nocopy"),
            image,
            "300",
        ],
    );
    let rw = rw.trim();
    assert_eq!(rw.len(), 64);
    let denied = install(control, fixture, image);
    assert!(!denied.status.success());
    assert!(String::from_utf8_lossy(&denied.stderr).contains("writable consumer"));
    assert_eq!(fingerprint(image), expected);
    ok("docker", &["rm", rw]);
    ok("docker", &["stop", "--time", "1", ro]);
    ok("docker", &["rm", ro]);

    // Deliberate payload-only drift in the uniquely created fixture, never shared supply.
    ok(
        "docker",
        &[
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--entrypoint",
            "sh",
            "--mount",
            &format!("type=volume,source={VOLUME},target=/probe,volume-nocopy"),
            image,
            "-ceu",
            "printf 'deliberate fixture drift\n' > /probe/probe.txt",
        ],
    );
    let drifted = fingerprint(image);
    let denied = install(control, fixture, image);
    assert!(!denied.status.success());
    assert!(String::from_utf8_lossy(&denied.stderr).contains("installed bytes/types/modes/links"));
    assert_eq!(
        fingerprint(image),
        drifted,
        "drift must be preserved, not repaired"
    );
    ok("docker", &["volume", "rm", VOLUME]);
    assert_eq!(
        ids(&[
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--format",
            "{{.ID}}"
        ]),
        containers
    );
    assert_eq!(ids(&["volume", "ls", "--format", "{{.Name}}"]), volumes);
    assert_eq!(
        ids(&["image", "ls", "--all", "--quiet", "--no-trunc"]),
        images
    );
    println!("PASS: public native cold install, active RO exact reuse, stopped RW denial, payload drift preserved, exact fixture cleanup; not full Harness");
}
