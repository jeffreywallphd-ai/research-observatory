//! Native-owned, bounded source read authority. No renderer path or plaintext staging.

use crate::directory_picker::{is_reparse, local_path_syntax, same_path};
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::os::windows::ffi::OsStringExt;
use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
use std::os::windows::io::AsRawHandle;
use std::path::{Path, PathBuf};
use windows_sys::Win32::Storage::FileSystem::{
    BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_OFFLINE, FILE_FLAG_BACKUP_SEMANTICS,
    FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES, FILE_SHARE_READ, FILE_SHARE_WRITE,
    FILE_TYPE_DISK, GetDriveTypeW, GetFileInformationByHandle, GetFileType,
    GetFinalPathNameByHandleW,
};

const CHUNK_BYTES: usize = 128 * 1024;
const MAX_SOURCE_BYTES: u64 = 256 * 1024 * 1024;
const UNAVAILABLE: &str = "RO-IMPORT-SOURCE-UNAVAILABLE";
const CANCELLED: &str = "RO-IMPORT-SOURCE-CANCELLED";

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct SourceSeal {
    pub source_sha256: String,
    pub byte_length: u64,
    pub chunk_count: u32,
}

pub(crate) struct HeldImportSource {
    file: File,
    // Keep all ancestors non-deletable until the last read and receipt check.
    _ancestors: Vec<File>,
    identity: (u32, u64),
    length: u64,
    basename: String,
}

fn device_component(value: &str) -> bool {
    let base = value
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();
    matches!(
        base.as_str(),
        "con" | "prn" | "aux" | "nul" | "conin$" | "conout$" | "clock$"
    ) || ["com", "lpt"].iter().any(|prefix| {
        base.strip_prefix(prefix).is_some_and(|suffix| {
            suffix.chars().count() == 1
                && suffix
                    .chars()
                    .all(|c| c.is_ascii_digit() || matches!(c, '¹' | '²' | '³'))
        })
    })
}

fn opened_path(file: &File) -> Result<PathBuf, &'static str> {
    let mut buffer = [0_u16; 4102];
    let length = unsafe {
        GetFinalPathNameByHandleW(
            file.as_raw_handle(),
            buffer.as_mut_ptr(),
            buffer.len() as u32,
            0,
        )
    } as usize;
    if length == 0 || length >= buffer.len() {
        return Err(UNAVAILABLE);
    }
    let value = std::ffi::OsString::from_wide(&buffer[..length]);
    let value = value.to_str().ok_or(UNAVAILABLE)?;
    let value = value.strip_prefix(r"\\?\").ok_or(UNAVAILABLE)?;
    if !local_path_syntax(value) {
        return Err(UNAVAILABLE);
    }
    Ok(PathBuf::from(value))
}

fn identity(file: &File) -> Result<(u32, u64), &'static str> {
    let mut info = std::mem::MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), info.as_mut_ptr()) } == 0 {
        return Err(UNAVAILABLE);
    }
    let info = unsafe { info.assume_init() };
    Ok((
        info.dwVolumeSerialNumber,
        (u64::from(info.nFileIndexHigh) << 32) | u64::from(info.nFileIndexLow),
    ))
}

impl HeldImportSource {
    pub(crate) fn open_selected(path: &Path) -> Result<Self, &'static str> {
        let value = path.to_str().ok_or(UNAVAILABLE)?;
        if !local_path_syntax(value)
            || path
                .components()
                .any(|part| device_component(&part.as_os_str().to_string_lossy()))
        {
            return Err(UNAVAILABLE);
        }
        let drive = value[..3]
            .replace('/', "\\")
            .encode_utf16()
            .chain(Some(0))
            .collect::<Vec<_>>();
        if !matches!(unsafe { GetDriveTypeW(drive.as_ptr()) }, 2 | 3 | 5 | 6) {
            return Err(UNAVAILABLE);
        }
        let basename = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or(UNAVAILABLE)?;
        if basename.trim().is_empty() || basename.chars().count() > 255 {
            return Err(UNAVAILABLE);
        }
        let mut ancestors = Vec::new();
        let mut current = PathBuf::new();
        for part in path.parent().ok_or(UNAVAILABLE)?.components() {
            current.push(part);
            if !current.is_absolute() {
                continue;
            }
            let guard = OpenOptions::new()
                .access_mode(FILE_READ_ATTRIBUTES)
                .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
                .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
                .open(&current)
                .map_err(|_| "RO-IMPORT-SOURCE-ANCESTOR-UNAVAILABLE")?;
            let metadata = guard.metadata().map_err(|_| UNAVAILABLE)?;
            if !metadata.is_dir()
                || is_reparse(&metadata)
                || !same_path(&opened_path(&guard)?, &current)
            {
                return Err("RO-IMPORT-SOURCE-ANCESTOR-INVALID");
            }
            ancestors.push(guard);
        }
        let file = OpenOptions::new()
            .read(true)
            .share_mode(FILE_SHARE_READ)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(path)
            .map_err(|_| "RO-IMPORT-SOURCE-FILE-UNAVAILABLE")?;
        let metadata = file.metadata().map_err(|_| UNAVAILABLE)?;
        if !metadata.is_file()
            || is_reparse(&metadata)
            || metadata.len() > MAX_SOURCE_BYTES
            || metadata.file_attributes() & FILE_ATTRIBUTE_OFFLINE != 0
            || unsafe { GetFileType(file.as_raw_handle()) } != FILE_TYPE_DISK
            || !same_path(&opened_path(&file)?, path)
        {
            return Err("RO-IMPORT-SOURCE-FILE-INVALID");
        }
        Ok(Self {
            identity: identity(&file)?,
            length: metadata.len(),
            file,
            _ancestors: ancestors,
            basename: basename.to_owned(),
        })
    }

    pub(crate) fn basename(&self) -> &str {
        &self.basename
    }

    pub(crate) fn transfer(
        mut self,
        authorized: impl Fn() -> bool,
        mut accept_chunk: impl FnMut(u32, &[u8]) -> Result<(), &'static str>,
    ) -> Result<SourceSeal, &'static str> {
        let mut remaining = self.length;
        let mut chunks = 0;
        let mut digest = Sha256::new();
        let mut buffer = vec![0_u8; CHUNK_BYTES];
        loop {
            if !authorized() {
                return Err(CANCELLED);
            }
            if identity(&self.file)? != self.identity
                || self.file.metadata().map_err(|_| UNAVAILABLE)?.len() != self.length
            {
                return Err(UNAVAILABLE);
            }
            let count = remaining.min(CHUNK_BYTES as u64) as usize;
            if count == 0 {
                // Verify EOF on this same held handle, including an empty file.
                if self.file.read(&mut buffer[..1]).map_err(|_| UNAVAILABLE)? != 0 {
                    return Err(UNAVAILABLE);
                }
                if !authorized() {
                    return Err(CANCELLED);
                }
                return Ok(SourceSeal {
                    source_sha256: format!("{:x}", digest.finalize()),
                    byte_length: self.length,
                    chunk_count: chunks,
                });
            }
            self.file
                .read_exact(&mut buffer[..count])
                .map_err(|_| UNAVAILABLE)?;
            if !authorized() {
                return Err(CANCELLED);
            }
            chunks += 1;
            accept_chunk(chunks, &buffer[..count])?;
            digest.update(&buffer[..count]);
            remaining -= count as u64;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::application_sign_in_policy::secure_random_hex;
    use sha2::{Digest, Sha256};
    use std::fs::{self, OpenOptions};
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicBool, Ordering};

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "ro-import-source-{}",
                secure_random_hex::<16>().unwrap()
            ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }
        fn source(&self, bytes: &[u8]) -> PathBuf {
            let path = self.0.join("synthetic.ris");
            fs::write(&path, bytes).unwrap();
            path
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            // This exact random directory is test-owned; no selected user path is removed.
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn held_source_streams_exact_bounded_chunks_and_verified_empty_eof() {
        let fixture = Fixture::new();
        let bytes = vec![b'X'; CHUNK_BYTES * 2 + 7];
        let path = fixture.source(&bytes);
        let source = HeldImportSource::open_selected(&path).unwrap();
        assert_eq!(source.basename(), "synthetic.ris");
        let mut received = Vec::new();
        let mut sizes = Vec::new();
        let seal = source
            .transfer(
                || true,
                |ordinal, chunk| {
                    assert_eq!(ordinal as usize, sizes.len() + 1);
                    sizes.push(chunk.len());
                    received.extend_from_slice(chunk);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(sizes, [CHUNK_BYTES, CHUNK_BYTES, 7]);
        assert_eq!(received, bytes);
        assert_eq!(seal.byte_length, bytes.len() as u64);
        assert_eq!(seal.chunk_count, 3);
        assert_eq!(seal.source_sha256, format!("{:x}", Sha256::digest(&bytes)));
        fs::write(&path, []).unwrap();
        let empty = HeldImportSource::open_selected(&path)
            .unwrap()
            .transfer(|| true, |_, _| panic!("empty source has no chunk"))
            .unwrap();
        assert_eq!(empty.byte_length, 0);
        assert_eq!(empty.chunk_count, 0);
        assert_eq!(empty.source_sha256, format!("{:x}", Sha256::digest([])));
    }

    #[test]
    fn held_source_denies_mutation_replacement_and_parent_rename_until_drop() {
        let fixture = Fixture::new();
        let path = fixture.source(b"synthetic");
        let source = HeldImportSource::open_selected(&path).unwrap();
        assert!(OpenOptions::new().write(true).open(&path).is_err());
        assert!(fs::rename(&path, fixture.0.join("replacement.ris")).is_err());
        assert!(fs::rename(&fixture.0, fixture.0.with_extension("moved")).is_err());
        let mut received = Vec::new();
        source
            .transfer(
                || true,
                |_, bytes| {
                    received.extend_from_slice(bytes);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(received, b"synthetic");
        assert!(OpenOptions::new().write(true).open(&path).is_ok());
    }

    #[test]
    fn held_source_denies_an_existing_writer_and_oversized_or_non_file_input() {
        let fixture = Fixture::new();
        let path = fixture.source(b"synthetic");
        let writer = OpenOptions::new().write(true).open(&path).unwrap();
        assert!(HeldImportSource::open_selected(&path).is_err());
        writer.set_len(MAX_SOURCE_BYTES + 1).unwrap();
        drop(writer);
        assert!(HeldImportSource::open_selected(&path).is_err());
        assert!(HeldImportSource::open_selected(&fixture.0).is_err());
        for value in [
            r"\\server\share\source.ris",
            r"\\?\C:\source.ris",
            r"C:\source.ris:secret",
            r"C:\NUL",
            r"C:\AUX.ris",
            r"relative.ris",
        ] {
            assert!(HeldImportSource::open_selected(Path::new(value)).is_err());
        }
    }

    #[test]
    fn held_source_revocation_and_receiver_failure_never_produce_a_seal() {
        let fixture = Fixture::new();
        let path = fixture.source(&vec![b'X'; CHUNK_BYTES + 1]);
        let valid = AtomicBool::new(true);
        let mut calls = 0;
        assert_eq!(
            HeldImportSource::open_selected(&path).unwrap().transfer(
                || valid.load(Ordering::Acquire),
                |_, _| {
                    calls += 1;
                    valid.store(false, Ordering::Release);
                    Ok(())
                }
            ),
            Err(CANCELLED)
        );
        assert_eq!(calls, 1);
        assert_eq!(
            HeldImportSource::open_selected(&path)
                .unwrap()
                .transfer(|| false, |_, _| panic!("revoked intake must not dispatch")),
            Err(CANCELLED)
        );
        assert_eq!(
            HeldImportSource::open_selected(&path)
                .unwrap()
                .transfer(|| true, |_, _| Err("synthetic-receiver-denial")),
            Err("synthetic-receiver-denial")
        );
    }

    #[test]
    fn held_source_rejects_a_junction_ancestor() {
        use std::os::windows::process::CommandExt;
        let fixture = Fixture::new();
        let real = fixture.0.join("real");
        fs::create_dir(&real).unwrap();
        fs::write(real.join("synthetic.ris"), b"synthetic").unwrap();
        let link = fixture.0.join("link");
        let powershell = PathBuf::from(std::env::var_os("SystemRoot").unwrap())
            .join("System32/WindowsPowerShell/v1.0/powershell.exe");
        let result = std::process::Command::new(powershell)
            .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:RO_IMPORT_TEST_LINK -Target $env:RO_IMPORT_TEST_TARGET | Out-Null"])
            .env("RO_IMPORT_TEST_LINK", &link).env("RO_IMPORT_TEST_TARGET", &real)
            .creation_flags(0x08000000).output().unwrap();
        assert!(
            result.status.success(),
            "owned junction fixture creation failed"
        );
        assert!(HeldImportSource::open_selected(&link.join("synthetic.ris")).is_err());
        fs::remove_dir(&link).unwrap();
        assert_eq!(fs::read(real.join("synthetic.ris")).unwrap(), b"synthetic");
    }
}
