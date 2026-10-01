//! Fixed adversarial image for the Windows LPAC boundary qualification.
//! It never accepts or executes a connector package.

use serde::Deserialize;
use serde_json::json;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::Path;

#[link(name = "Ws2_32")]
unsafe extern "system" {
    fn WSAStartup(version: u16, data: *mut u64) -> i32;
    fn WSACleanup() -> i32;
    fn socket(family: i32, kind: i32, protocol: i32) -> usize;
    fn setsockopt(handle: usize, level: i32, option: i32, value: *const u8, length: i32) -> i32;
    fn connect(handle: usize, address: *const u8, length: i32) -> i32;
    fn closesocket(handle: usize) -> i32;
}

const MAX_CONTROL_FRAME: usize = 1_048_576;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeRequest {
    #[serde(rename = "protocolVersion")]
    protocol_version: String,
    #[serde(rename = "jobNonce")]
    job_nonce: String,
    sequence: u64,
    operation: String,
    #[serde(rename = "readPath")]
    read_path: String,
    #[serde(rename = "writePath")]
    write_path: String,
    #[serde(rename = "loopbackPort")]
    loopback_port: u16,
}

fn read_request() -> Result<ProbeRequest, ()> {
    let mut stdin = io::stdin().lock();
    let mut prefix = [0_u8; 4];
    stdin.read_exact(&mut prefix).map_err(|_| ())?;
    let length = u32::from_be_bytes(prefix) as usize;
    if length == 0 || length > MAX_CONTROL_FRAME {
        return Err(());
    }
    let mut bytes = vec![0_u8; length];
    stdin.read_exact(&mut bytes).map_err(|_| ())?;
    let mut trailing = [0_u8; 1];
    if stdin.read(&mut trailing).map_err(|_| ())? != 0 {
        return Err(());
    }
    let request: ProbeRequest = serde_json::from_slice(&bytes).map_err(|_| ())?;
    if request.protocol_version != "1.0"
        || request.sequence != 0
        || request.operation != "probe"
        || request.job_nonce.len() != 32
        || !request
            .job_nonce
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        || request.read_path.is_empty()
        || request.write_path.is_empty()
        || request.loopback_port == 0
    {
        return Err(());
    }
    Ok(request)
}

fn attempt_read(path: &str) -> &'static str {
    let Ok(mut source) = File::open(path) else {
        return "denied";
    };
    let mut byte = [0_u8; 1];
    if source.read(&mut byte).is_ok() {
        "allowed"
    } else {
        "denied"
    }
}

fn attempt_write(path: &Path) -> &'static str {
    let Ok(mut target) = OpenOptions::new().write(true).create_new(true).open(path) else {
        return "denied";
    };
    let _ = target.write_all(b"probe");
    drop(target);
    let _ = fs::remove_file(path);
    "allowed"
}

fn attempt_loopback(port: u16) -> &'static str {
    // Rust's standard-library socket initialization asserts WSAStartup succeeds.
    // LPAC without a network capability can reject WSAStartup itself, so use
    // Winsock directly and report that as a denied connection attempt.
    let mut winsock_data = [0_u64; 64];
    if unsafe { WSAStartup(0x0202, winsock_data.as_mut_ptr()) } != 0 {
        return "denied";
    }
    let handle = unsafe { socket(2, 1, 6) };
    if handle == usize::MAX {
        unsafe { WSACleanup() };
        return "denied";
    }
    let timeout_ms = 500_i32;
    unsafe {
        setsockopt(handle, 0xffff, 0x1005, (&raw const timeout_ms).cast(), 4);
    }
    let mut address = [0_u8; 16];
    address[0] = 2;
    address[2..4].copy_from_slice(&port.to_be_bytes());
    address[4..8].copy_from_slice(&[127, 0, 0, 1]);
    let connected = unsafe { connect(handle, address.as_ptr(), address.len() as i32) == 0 };
    unsafe {
        closesocket(handle);
        WSACleanup();
    }
    if connected { "allowed" } else { "denied" }
}

fn run() -> Result<(), ()> {
    let request = read_request().map_err(|()| {
        eprintln!("probe-error:request");
    })?;
    let profile = std::env::var_os("LOCALAPPDATA").ok_or_else(|| {
        eprintln!("probe-error:profile-env");
    })?;
    let temp = std::env::var_os("TEMP").ok_or_else(|| {
        eprintln!("probe-error:temp-env");
    })?;
    let profile = Path::new(&profile);
    let temp = Path::new(&temp);
    if !profile.is_dir() || !temp.is_dir() {
        eprintln!("probe-error:profile-or-temp-unavailable");
        return Err(());
    }
    let response = json!({
        "protocolVersion": "1.0",
        "jobNonce": request.job_nonce,
        "sequence": 1,
        "operation": "probe-result",
        "probes": {
            "parentEnvironmentSecret": if std::env::var_os("RO_LPAC_TEST_SECRET").is_none() { "denied" } else { "leaked" },
            "unrelatedRead": attempt_read(&request.read_path),
            "outsideWrite": attempt_write(Path::new(&request.write_path)),
            "directLoopback": attempt_loopback(request.loopback_port),
            "profileWrite": attempt_write(&profile.join("lpac-write-probe")),
            "tempWrite": attempt_write(&temp.join("lpac-write-probe")),
        },
    });
    let bytes = serde_json::to_vec(&response).map_err(|_| {
        eprintln!("probe-error:serialize");
    })?;
    if bytes.len() > MAX_CONTROL_FRAME {
        eprintln!("probe-error:response-oversize");
        return Err(());
    }
    let mut stdout = io::stdout().lock();
    stdout
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .map_err(|_| {
            eprintln!("probe-error:stdout-prefix");
        })?;
    stdout.write_all(&bytes).map_err(|_| {
        eprintln!("probe-error:stdout-payload");
    })?;
    stdout.flush().map_err(|_| {
        eprintln!("probe-error:stdout-flush");
    })?;
    Ok(())
}

fn main() {
    if run().is_err() {
        std::process::exit(2);
    }
}
