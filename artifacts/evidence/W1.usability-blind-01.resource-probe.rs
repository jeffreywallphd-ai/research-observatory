//! Read-only diagnostic. Calls the compiled supervisor path validator; never
//! creates a UI, starts Core, changes settings, or reads project data.
use research_observatory_desktop_lib::supervisor::SupervisorConfig;
use std::path::Path;

fn main() {
    let root = std::env::args().nth(1).expect("exact test resource directory");
    let plain = Path::new(&root);
    let canonical = plain.canonicalize().expect("existing test directory");
    let plain_result = SupervisorConfig::from_resource_root(plain).map(|_| "accepted");
    let canonical_result =
        SupervisorConfig::from_resource_root(&canonical).map(|_| "accepted");
    println!("supplied_root={}", plain.display());
    println!("std_canonical_root={}", canonical.display());
    println!("supplied_result={plain_result:?}");
    println!("std_canonical_result={canonical_result:?}");
    assert!(plain_result.is_ok(), "plain fixture must validate");
    assert_eq!(canonical_result, Err("RO-CORE-INTEGRITY-FAILED"));
}
