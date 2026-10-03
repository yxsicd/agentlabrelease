use agentlab_code_analysis::harmony_build_plan::prepare;
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};
static NEXT: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);
impl Fixture {
    fn new(kind: &str) -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "harmony-build-plan-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(root.join("features/subject/src/main")).unwrap();
        fs::create_dir_all(root.join("products/host/src/main")).unwrap();
        fs::write(root.join("build-profile.json5"), "{ // JSON5 comments must not become fake fields\n app:{products:[{name:'default'}],buildModeSet:[{name:'debug'}]}, modules:[{name:'subject',srcPath:'./features/subject'},{name:'host',srcPath:'./products/host'}], }").unwrap();
        fs::write(
            root.join("features/subject/src/main/module.json5"),
            format!("{{module:{{type:'{kind}',name:'subject'}}}}"),
        )
        .unwrap();
        fs::write(
            root.join("products/host/src/main/module.json5"),
            "{module:{type:'entry',name:'host'}}",
        )
        .unwrap();
        for dir in ["features/subject", "products/host"] {
            fs::write(
                root.join(dir).join("build-profile.json5"),
                "{targets:[{name:'default'},{name:'ohosTest'}]}",
            )
            .unwrap();
        }
        Self(root)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn selects_tasks_from_output_type_and_resolves_registered_paths() {
    for (kind, output, task) in [
        ("entry", "hap", "assembleHap"),
        ("feature", "hap", "assembleHap"),
        ("har", "har", "genOnDeviceTestHap"),
        ("shared", "hsp", "genOnDeviceTestHap"),
    ] {
        let f = Fixture::new(kind);
        let plan = prepare(&f.0, "subject", "host", "default", "debug").unwrap();
        assert_eq!(plan["modulePath"], "features/subject");
        assert_eq!(plan["hostModulePath"], "products/host");
        assert_eq!(plan["outputType"], output);
        assert_eq!(plan["commands"][1]["task"], task);
        assert_eq!(plan["commands"][0]["task"], "assembleHap");
        assert_eq!(plan["sourceBindings"].as_array().unwrap().len(), 5);
        assert_eq!(
            plan,
            prepare(&f.0, "subject", "host", "default", "debug").unwrap()
        );
        assert_eq!(plan["automaticPromotion"], false);
        assert_eq!(plan["runtimeQualified"], false);
    }
}

#[test]
fn rejects_missing_or_noninstallable_host_and_undeclared_product_mode() {
    let f = Fixture::new("har");
    for (host, product, mode) in [
        ("subject", "default", "debug"),
        ("missing", "default", "debug"),
        ("host", "other", "debug"),
        ("host", "default", "release"),
    ] {
        assert!(prepare(&f.0, "subject", host, product, mode).is_err());
    }
}

#[test]
fn rejects_unregistered_test_target_and_unknown_output_type() {
    let f = Fixture::new("unknown");
    assert!(prepare(&f.0, "subject", "host", "default", "debug").is_err());
    fs::write(
        f.0.join("features/subject/src/main/module.json5"),
        "{module:{type:'har'}}",
    )
    .unwrap();
    fs::write(
        f.0.join("features/subject/build-profile.json5"),
        "{targets:[{name:'default'}]}",
    )
    .unwrap();
    assert!(prepare(&f.0, "subject", "host", "default", "debug").is_err());
}

#[test]
fn rejects_duplicate_registrations_path_escape_and_symlink_evidence() {
    let f = Fixture::new("har");
    for modules in [
        "[{name:'subject',srcPath:'../outside'}]",
        "[{name:'subject',srcPath:'features/subject'},{name:'subject',srcPath:'features/subject'}]",
    ] {
        fs::write(f.0.join("build-profile.json5"),format!("{{app:{{products:[{{name:'default'}}],buildModeSet:[{{name:'debug'}}]}},modules:{modules}}}")).unwrap();
        assert!(prepare(&f.0, "subject", "host", "default", "debug").is_err());
    }
    #[cfg(unix)]
    {
        let f = Fixture::new("har");
        fs::remove_file(f.0.join("features/subject/src/main/module.json5")).unwrap();
        std::os::unix::fs::symlink(
            "../../../../products/host/src/main/module.json5",
            f.0.join("features/subject/src/main/module.json5"),
        )
        .unwrap();
        assert!(prepare(&f.0, "subject", "host", "default", "debug").is_err());
    }
}
