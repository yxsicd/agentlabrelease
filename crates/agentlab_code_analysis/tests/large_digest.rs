use agentlab_code_analysis::digest;
use std::time::Instant;

#[test]
fn large_identity_hash_retains_exact_bytes() {
    // Independent SHA-256 vector: 64 MiB of zero bytes. Large Linux executable
    // identity checks must remain byte-based, not a metadata/cache shortcut.
    let mut bytes = vec![0u8; 64 * 1024 * 1024];
    let start = Instant::now();
    let original = digest(&bytes);
    eprintln!("64 MiB identity hash: {:?}", start.elapsed());
    assert_eq!(
        original,
        "3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351"
    );
    bytes[32 * 1024 * 1024] = 1;
    assert_ne!(digest(&bytes), original);
}
