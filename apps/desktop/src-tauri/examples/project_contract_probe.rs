//! Disposable test composition: actual async native dispatch and supervised Core.

#[cfg(feature = "integration-harness")]
mod probe {
    use std::ffi::OsString;
    use std::io::{self, BufRead, Write};
    use std::path::PathBuf;

    use research_observatory_desktop_lib::{
        dispatch_core_api_request, dispatch_runtime_start, dispatch_runtime_stop,
        supervisor::{CoreApiRequest, RuntimeSupervisor, SupervisorConfig},
    };
    use serde_json::{Value, json};

    fn emit(value: &Value) -> Result<(), &'static str> {
        let mut output = io::stdout().lock();
        serde_json::to_writer(&mut output, value).map_err(|_| "probe-encode-failed")?;
        output
            .write_all(b"\n")
            .and_then(|_| output.flush())
            .map_err(|_| "probe-output-failed")
    }

    pub fn run() -> Result<(), &'static str> {
        let arguments: Vec<OsString> = std::env::args_os().skip(1).collect();
        if arguments
            .first()
            .is_some_and(|value| value == "--check-packaged-path")
            && arguments.len() == 2
        {
            let result = SupervisorConfig::new(PathBuf::from(&arguments[1]));
            return emit(&json!({"accepted": result.is_ok(), "code": result.err()}));
        }
        if arguments.len() != 4 {
            return Err("probe-arguments-invalid");
        }
        let config = SupervisorConfig::for_integration_harness(
            PathBuf::from(&arguments[0]),
            PathBuf::from(&arguments[1]),
            vec![
                OsString::from("-m"),
                OsString::from("native_integration_sidecar"),
                OsString::from("--profile-vault-root"),
                arguments[3].clone(),
            ],
            vec![(OsString::from("PYTHONPATH"), arguments[2].clone())],
        )?;
        let supervisor = RuntimeSupervisor::new(Ok(config));
        let mut launches = Vec::new();
        let result = (|| {
            emit(&json!({"kind": "initialized", "snapshot": supervisor.status()}))?;
            for line in io::stdin().lock().lines() {
                let line = line.map_err(|_| "probe-input-failed")?;
                let value: Value = serde_json::from_str(&line).map_err(|_| "probe-json-invalid")?;
                match value.get("control").and_then(Value::as_str) {
                    Some("start") => {
                        let owned = supervisor.clone();
                        launches.push(std::thread::spawn(move || {
                            tauri::async_runtime::block_on(dispatch_runtime_start(owned))
                        }));
                        emit(&json!({"kind": "snapshot", "snapshot": supervisor.status()}))?;
                    }
                    Some("status") => {
                        emit(&json!({"kind": "snapshot", "snapshot": supervisor.status()}))?
                    }
                    Some("stop") => {
                        let snapshot = tauri::async_runtime::block_on(dispatch_runtime_stop(
                            supervisor.clone(),
                        ))?;
                        emit(&json!({"kind": "snapshot", "snapshot": snapshot}))?;
                    }
                    Some(_) => return Err("probe-control-invalid"),
                    None => {
                        let request: CoreApiRequest =
                            serde_json::from_value(value).map_err(|_| "probe-envelope-invalid")?;
                        match tauri::async_runtime::block_on(dispatch_core_api_request(
                            supervisor.clone(),
                            request,
                        )) {
                            Ok(response) => {
                                emit(&json!({"kind": "response", "response": response}))?
                            }
                            Err(code) => emit(&json!({"kind": "error", "code": code}))?,
                        }
                    }
                }
            }
            Ok(())
        })();
        let stopped = tauri::async_runtime::block_on(dispatch_runtime_stop(supervisor));
        for launch in launches {
            launch.join().map_err(|_| "probe-launch-thread-failed")??;
        }
        stopped?;
        result
    }
}

#[cfg(feature = "integration-harness")]
fn main() {
    if let Err(code) = probe::run() {
        eprintln!("{code}");
        std::process::exit(1);
    }
}

#[cfg(not(feature = "integration-harness"))]
fn main() {
    eprintln!("The disposable probe requires the integration-harness feature.");
    std::process::exit(1);
}
