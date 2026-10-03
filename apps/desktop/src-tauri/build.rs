fn main() {
    tauri_build::build();

    // Cargo links tauri-build's Windows resource into binaries, not examples.
    // The disposable native harness imports Common Controls v6 entry points.
    // Give every example the same activation dependency before the loader runs.
    #[cfg(windows)]
    {
        println!("cargo:rerun-if-changed=resources/example-application.rc");
        println!("cargo:rerun-if-changed=resources/example-application.manifest");
        embed_resource::compile_for_examples(
            "resources/example-application.rc",
            embed_resource::NONE,
        )
        .manifest_required()
        .expect("failed to embed the Windows example activation manifest");
    }
}
