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
        let delayed = mode == "child-delayed-ready";
        thread::spawn(move || serve(listener, compatible, delayed));
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
                "\"nonce\":\"{}\",\"capabilities\":[\"runtime.status\"],",
                "\"databaseCompatibility\":{{\"minimum\":\"0.1.0\",",
                "\"maximumExclusive\":\"0.2.0\"}},",
                "\"diagnosticCode\":\"RO-CORE-STARTING\"}}"
            ),
            std::process::id(),
            port,
            NONCE,
        );
    }

    fn serve(listener: TcpListener, compatible: bool, delayed: bool) {
        for connection in listener.incoming() {
            let Ok(mut stream) = connection else {
                return;
            };
            let mut request = [0_u8; 1024];
            let _ = stream.read(&mut request);
            if delayed {
                fs::write("fixture-ready-requested.flag", b"ready")
                    .expect("write readiness marker");
                thread::sleep(Duration::from_millis(750));
            }
            let version = if compatible { "0.1.0" } else { "99.0.0" };
            let body = format!(
                concat!(
                    "{{\"schemaVersion\":\"1.0\",",
                    "\"service\":\"research-observatory-core\",",
                    "\"version\":\"{}\",\"state\":\"ready\",",
                    "\"capabilities\":[\"runtime.status\"],\"ready\":true}}"
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
