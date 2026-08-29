#[cfg(windows)]
mod windows_fixture {
    use std::fs;
    use std::io::{BufRead, Read, Write};
    use std::net::TcpListener;
    use std::path::Path;
    use std::process::{Command, Stdio};
    use std::thread;
    use std::time::Duration;

    const NONCE: &str = "0123456789abcdef0123456789abcdef";

    pub fn run() {
        let argument = std::env::args().nth(1);
        if argument.as_deref() == Some("--descendant") {
            fs::write("fixture-child.pid", std::process::id().to_string())
                .expect("write descendant PID");
            loop {
                thread::sleep(Duration::from_secs(60));
            }
        }
        assert_eq!(argument.as_deref(), Some("--supervised"));
        fs::write("fixture-root.pid", std::process::id().to_string()).expect("write root PID");
        let mode = fs::read_to_string("fixture-mode.txt").expect("fixture mode");
        let mode = mode.trim();
        let capability_token = read_startup_authentication();

        if mode.starts_with("child-") {
            spawn_descendant();
        }
        if mode == "malformed-handshake" {
            println!("not-json");
            loop {
                thread::sleep(Duration::from_secs(60));
            }
        }
        if mode == "port-zero" {
            print_handshake(0);
            loop {
                thread::sleep(Duration::from_secs(60));
            }
        }

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind fixture listener");
        let port = listener.local_addr().expect("listener address").port();
        print_handshake(port);
        if mode == "early-exit" {
            return;
        }

        let compatible = mode != "never-ready";
        let api_compatible = mode != "api-incompatible";
        let delayed = mode == "child-delayed-ready";
        thread::spawn(move || {
            serve(
                listener,
                compatible,
                api_compatible,
                delayed,
                capability_token,
            )
        });
        let mut line = String::new();
        std::io::stdin()
            .lock()
            .read_line(&mut line)
            .expect("read supervisor control");
        if matches!(mode, "child-hung" | "child-delayed-ready") {
            loop {
                thread::sleep(Duration::from_secs(60));
            }
        }
    }

    // The supervisor, rather than the fixture parent, must prove it owns and
    // reaps this descendant through the Windows Job Object boundary.
    #[allow(clippy::zombie_processes)]
    fn spawn_descendant() {
        use std::os::windows::process::CommandExt;
        let executable = std::env::current_exe().expect("fixture executable");
        Command::new(executable)
            .arg("--descendant")
            .creation_flags(0x0800_0000)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn immediate descendant");
    }

    fn print_handshake(port: u16) {
        println!(
            concat!(
                "{{\"protocolVersion\":\"1.0\",\"buildId\":\"0.1.0\",",
                "\"pid\":{},\"host\":\"127.0.0.1\",\"port\":{},",
                "\"nonce\":\"{}\",\"capabilities\":[\"intent.acceptance\",\"intent.drafts\",\"intent.impact-preview\",\"intent.policy-evaluation\",\"intent.read\",\"operations.cancel\",\"operations.events\",\"operations.read\",\"privacy.cache-cleanup\",\"privacy.policy\",\"projects.lifecycle\",\"runtime.contract\",\"runtime.status\"],",
                "\"databaseCompatibility\":{{\"minimum\":\"0.1.0\",",
                "\"maximumExclusive\":\"0.2.0\"}},",
                "\"diagnosticCode\":\"RO-CORE-STARTING\"}}"
            ),
            std::process::id(),
            port,
            NONCE,
        );
    }

    fn read_startup_authentication() -> String {
        let mut line = String::new();
        std::io::stdin()
            .lock()
            .read_line(&mut line)
            .expect("read startup authentication");
        let token = line
            .strip_prefix("auth ")
            .and_then(|value| value.strip_suffix('\n'))
            .expect("strict startup authentication record");
        assert_eq!(token.len(), 64);
        assert!(
            token
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        );
        token.to_owned()
    }

    fn serve(
        listener: TcpListener,
        compatible: bool,
        api_compatible: bool,
        delayed: bool,
        capability_token: String,
    ) {
        for connection in listener.incoming() {
            let Ok(mut stream) = connection else {
                return;
            };
            let mut request = [0_u8; 1024];
            let received = stream.read(&mut request).unwrap_or_default();
            let request = String::from_utf8_lossy(&request[..received]);
            let expected_authority = format!(
                "Host: 127.0.0.1:{}\r\n",
                listener.local_addr().expect("listener address").port(),
            );
            let expected_auth = format!("Authorization: Bearer {capability_token}\r\n");
            if !request.contains(&expected_authority) || !request.contains(&expected_auth) {
                let _ = stream.write_all(
                    b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                );
                continue;
            }
            if delayed && request.starts_with("GET /readyz ") {
                fs::write("fixture-ready-requested.flag", b"ready")
                    .expect("write readiness marker");
                thread::sleep(Duration::from_millis(750));
            }
            if request.starts_with("GET /runtime/version ") {
                let trace_id = request
                    .split("\r\n")
                    .find_map(|line| line.strip_prefix("X-Trace-Id: "))
                    .expect("version request trace ID");
                let api_version = if api_compatible { "1.0.0" } else { "2.0.0" };
                let body = format!(
                    concat!(
                        "{{\"schemaVersion\":\"1.0\",",
                        "\"service\":\"research-observatory-core\",",
                        "\"version\":\"0.1.0\",\"apiVersion\":\"{}\",",
                        "\"minimumClientApiVersion\":\"1.0.0\",",
                        "\"maximumClientApiVersionExclusive\":\"2.0.0\"}}"
                    ),
                    api_version,
                );
                let response = format!(
                    concat!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n",
                        "X-Trace-Id: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}"
                    ),
                    trace_id,
                    body.len(),
                    body,
                );
                let _ = stream.write_all(response.as_bytes());
                continue;
            }
            let version = if compatible { "0.1.0" } else { "99.0.0" };
            let body = format!(
                concat!(
                    "{{\"schemaVersion\":\"1.0\",",
                    "\"service\":\"research-observatory-core\",",
                    "\"version\":\"{}\",\"state\":\"ready\",",
                    "\"capabilities\":[\"intent.acceptance\",\"intent.drafts\",\"intent.impact-preview\",\"intent.policy-evaluation\",\"intent.read\",\"operations.cancel\",\"operations.events\",\"operations.read\",\"privacy.cache-cleanup\",\"privacy.policy\",\"projects.lifecycle\",\"runtime.contract\",\"runtime.status\"],\"ready\":true}}"
                ),
                version,
            );
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body,
            );
            let _ = stream.write_all(response.as_bytes());
        }
    }

    #[allow(dead_code)]
    fn _assert_working_directory_is_local(path: &Path) -> bool {
        path.join("fixture-mode.txt").is_file()
    }
}

#[cfg(windows)]
fn main() {
    windows_fixture::run();
}

#[cfg(not(windows))]
fn main() {
    panic!("supervisor fixture is release-authoritative on Windows x64");
}
