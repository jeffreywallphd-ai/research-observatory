use research_observatory_desktop_lib::application_lock_verification::windows_hello_availability_snapshot;

fn main() {
    println!(
        "{}",
        serde_json::to_string(&windows_hello_availability_snapshot())
            .expect("serialize Windows Hello availability")
    );
}
