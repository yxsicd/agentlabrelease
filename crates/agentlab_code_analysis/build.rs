use sha2::{Digest, Sha256};
fn main() {
    let mut hash = Sha256::new();
    for path in [
        "grammar/src/parser.c",
        "grammar/src/scanner.c",
        "grammar/upstream/common/scanner.h",
        "grammar/grammar.js",
        "grammar/upstream/common/define-grammar.js",
    ] {
        hash.update(path.as_bytes());
        hash.update(std::fs::read(path).expect("grammar source"));
    }
    println!(
        "cargo:rustc-env=AGENTLAB_GRAMMAR_DIGEST={:x}",
        hash.finalize()
    );
    let mut build = cc::Build::new();
    build
        .include("grammar/src")
        .flag_if_supported("-std=c11")
        .flag_if_supported("-Wno-unused-parameter");
    for file in ["grammar/src/parser.c", "grammar/src/scanner.c"] {
        build.file(file);
        println!("cargo:rerun-if-changed={file}");
    }
    println!("cargo:rerun-if-changed=grammar/upstream/common/scanner.h");
    build.compile("agentlab-arkts-grammar");
}
