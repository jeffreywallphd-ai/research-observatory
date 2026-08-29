use std::ffi::OsString;
use std::io::{self, BufRead, Write};
use std::path::PathBuf;

use research_observatory_desktop_lib::supervisor::{
    CoreApiRequest, RuntimeState, RuntimeSupervisor, SupervisorConfig,
};
use serde_json::{Value, json};

fn emit(value: &Value) -> Result<(), String> {
    let mut stdout = io::stdout().lock();
    serde_json::to_writer(&mut stdout, value)
        .map_err(|_| "serialize harness response".to_owned())?;
    stdout
        .write_all(b"\n")
        .and_then(|_| stdout.flush())
        .map_err(|_| "write harness response".to_owned())
}

fn start(supervisor: &RuntimeSupervisor) -> Result<(), String> {
    let snapshot = supervisor.start();
    if snapshot.state != RuntimeState::Ready {
        return Err(format!(
            "supervised Core failed to become ready: {:?}; diagnostics: {:?}",
            snapshot.diagnostic_reference,
            supervisor.diagnostics()
        ));
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let python = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .ok_or_else(|| "Python executable argument is required".to_owned())?;
    let repository = std::env::args_os()
        .nth(2)
        .map(PathBuf::from)
        .ok_or_else(|| "repository argument is required".to_owned())?;
    let service_source = std::env::args_os()
        .nth(3)
        .map(PathBuf::from)
        .ok_or_else(|| "service source argument is required".to_owned())?;
    let vault_root = std::env::args_os()
        .nth(4)
        .map(PathBuf::from)
        .ok_or_else(|| "integration vault argument is required".to_owned())?;
    let config = SupervisorConfig::for_integration_harness(
        python,
        repository,
        vec![
            OsString::from("-m"),
            OsString::from("native_integration_sidecar"),
            OsString::from("--profile-vault-root"),
            vault_root.into_os_string(),
        ],
        vec![(
            OsString::from("PYTHONPATH"),
            service_source.into_os_string(),
        )],
    )
    .map_err(str::to_owned)?;
    let supervisor = RuntimeSupervisor::new(Ok(config));
    start(&supervisor)?;
    emit(&json!({"kind": "ready"}))?;

    for line in io::stdin().lock().lines() {
        let line = line.map_err(|_| "read harness request".to_owned())?;
        let value: Value =
            serde_json::from_str(&line).map_err(|_| "parse harness request".to_owned())?;
        if value.get("control").and_then(Value::as_str) == Some("restart") {
            supervisor.stop();
            start(&supervisor)?;
            emit(&json!({"kind": "restarted"}))?;
            continue;
        }
        let request: CoreApiRequest =
            serde_json::from_value(value).map_err(|_| "decode Core request".to_owned())?;
        match supervisor.api_request(&request) {
            Ok(response) => emit(&json!({"kind": "response", "response": response}))?,
            Err(code) => emit(&json!({"kind": "error", "code": code}))?,
        }
    }
    supervisor.stop();
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        let _ = writeln!(io::stderr(), "{error}");
        std::process::exit(1);
    }
}
