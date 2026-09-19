//! Bounded content-free diagnostic export. Paths and staging never reach the renderer.

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::windows::ffi::OsStrExt;
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::AsRawHandle;
use std::path::{Path, PathBuf};
use windows_sys::Win32::Foundation::{GENERIC_READ, GENERIC_WRITE};
use windows_sys::Win32::Storage::FileSystem::{
    DELETE, FILE_DISPOSITION_INFO, FILE_FLAG_OPEN_REPARSE_POINT, FILE_RENAME_INFO,
    FileDispositionInfo, FileRenameInfo, SetFileInformationByHandle,
};

const HEADER: &str = "ordinal,line_start,line_end,status,diagnostic\r\n";
const FAILED: &str = "RO-IMPORT-REPORT-FAILED";
const LIMIT: u64 = 256 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct ReportPage {
    preview_id: String,
    revision: u32,
    record_count: u32,
    next_after: u32,
    complete: bool,
    csv: String,
}

pub(crate) struct ReportCursor {
    preview_id: String,
    revision: u32,
    count: Option<u32>,
    pub after: u32,
    pub complete: bool,
}
impl ReportCursor {
    pub(crate) fn new(preview_id: &str, revision: u32) -> Self {
        Self {
            preview_id: preview_id.into(),
            revision,
            count: None,
            after: 0,
            complete: false,
        }
    }
    fn matches(&self, page: &ReportPage) -> bool {
        page.preview_id == self.preview_id
            && page.revision == self.revision
            && page.record_count <= 200000
            && self.count.is_none_or(|count| count == page.record_count)
            && page.next_after <= page.record_count
            && page.complete == (page.next_after == page.record_count)
    }
    pub(crate) fn accept(&mut self, page: ReportPage) -> Result<String, &'static str> {
        if self.complete
            || !self.matches(&page)
            || page.csv.len() > 900000
            || page.next_after < self.after
            || page.next_after - self.after > 25
            || page.next_after == self.after && !page.complete
        {
            return Err(FAILED);
        }
        let data = if self.after == 0 {
            page.csv.strip_prefix(HEADER).ok_or(FAILED)?
        } else {
            &page.csv
        };
        let mut ordinal = self.after;
        let mut warning_rows = 0;
        for line in data.split_inclusive("\r\n") {
            let line = line.strip_suffix("\r\n").ok_or(FAILED)?;
            let values: Vec<_> = line.split(',').collect();
            if values.len() != 5 {
                return Err(FAILED);
            }
            let number = |value: &str| -> Result<u32, &'static str> {
                if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
                    return Err(FAILED);
                }
                value.parse().map_err(|_| FAILED)
            };
            let row = number(values[0])?;
            let start = number(values[1])?;
            let end = number(values[2])?;
            if row == ordinal + 1 {
                ordinal = row;
                warning_rows = 0;
            }
            if row <= self.after
                || row != ordinal
                || row > page.next_after
                || start == 0
                || end < start
                || end > 268435457
                || !matches!(values[3], "parsed" | "malformed")
                || values[4].is_empty()
                || values[4].len() > 64
                || !values[4]
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte == b'-')
            {
                return Err(FAILED);
            }
            warning_rows += 1;
            if warning_rows > 64 {
                return Err(FAILED);
            }
        }
        if ordinal != page.next_after {
            return Err(FAILED);
        }
        self.after = page.next_after;
        self.count = Some(page.record_count);
        self.complete = page.complete;
        Ok(page.csv)
    }
    /// Separate final Core authorization; never append a second header.
    pub(crate) fn authorize_final(&self, page: ReportPage) -> Result<(), &'static str> {
        if !self.complete
            || !self.matches(&page)
            || page.next_after != self.after
            || !page.complete
            || page.csv != if self.after == 0 { HEADER } else { "" }
        {
            return Err(FAILED);
        }
        Ok(())
    }
}

pub(crate) struct StagedReport {
    file: File,
    _guards: Vec<File>,
    #[cfg(test)]
    staging: PathBuf,
    destination: PathBuf,
    digest: Sha256,
    bytes: u64,
    verified: bool,
    published: bool,
}
impl StagedReport {
    pub(crate) fn create(directory: &Path, operation: &str) -> Result<Self, &'static str> {
        if operation.len() != 32
            || !operation
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(FAILED);
        }
        let guards = crate::import_source::pin_directory(directory)?;
        let staging = directory.join(format!(".import-diagnostics-{operation}.partial"));
        let destination = directory.join(format!("import-diagnostics-{operation}.csv"));
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .access_mode(GENERIC_READ | GENERIC_WRITE | DELETE)
            .share_mode(0)
            .create_new(true)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .open(&staging)
            .map_err(|_| FAILED)?;
        Ok(Self {
            file,
            _guards: guards,
            #[cfg(test)]
            staging,
            destination,
            digest: Sha256::new(),
            bytes: 0,
            verified: false,
            published: false,
        })
    }
    pub(crate) fn append(&mut self, bytes: &[u8]) -> Result<(), &'static str> {
        if self.published || bytes.len() > 900000 || self.bytes + bytes.len() as u64 > LIMIT {
            return Err(FAILED);
        }
        self.verified = false;
        self.file.write_all(bytes).map_err(|_| FAILED)?;
        self.digest.update(bytes);
        self.bytes += bytes.len() as u64;
        Ok(())
    }
    pub(crate) fn verify(&mut self, authorized: impl Fn() -> bool) -> Result<(), &'static str> {
        if self.published || !authorized() {
            return Err(FAILED);
        }
        self.file.sync_all().map_err(|_| FAILED)?;
        self.file.seek(SeekFrom::Start(0)).map_err(|_| FAILED)?;
        let mut digest = Sha256::new();
        let mut total = 0;
        let mut buffer = [0_u8; 128 * 1024];
        loop {
            if !authorized() {
                return Err(FAILED);
            }
            let count = self.file.read(&mut buffer).map_err(|_| FAILED)?;
            if count == 0 {
                break;
            }
            total += count as u64;
            if total > self.bytes {
                return Err(FAILED);
            }
            digest.update(&buffer[..count]);
        }
        if !authorized()
            || total != self.bytes
            || digest.finalize() != self.digest.clone().finalize()
        {
            return Err(FAILED);
        }
        self.verified = true;
        Ok(())
    }
    /// Caller holds native lock/project/operation publication guards. Rename is
    /// the publication point; never delete or report cancellation after success.
    pub(crate) fn publish(&mut self) -> Result<(), &'static str> {
        if !self.verified || self.published {
            return Err(FAILED);
        }
        let name: Vec<u16> = self
            .destination
            .as_os_str()
            .encode_wide()
            .chain(Some(0))
            .collect();
        let bytes = std::mem::offset_of!(FILE_RENAME_INFO, FileName) + name.len() * 2;
        let mut buffer = vec![
            0_u64;
            bytes
                .max(std::mem::size_of::<FILE_RENAME_INFO>())
                .div_ceil(8)
        ];
        // u64 storage supplies the Windows x64 structure alignment; extra space
        // owns the full flexible UTF-16 tail including its terminator.
        assert!(std::mem::align_of::<FILE_RENAME_INFO>() <= std::mem::align_of::<u64>());
        let info = buffer.as_mut_ptr().cast::<FILE_RENAME_INFO>();
        unsafe {
            (*info).Anonymous.ReplaceIfExists = false;
            (*info).RootDirectory = std::ptr::null_mut();
            (*info).FileNameLength = ((name.len() - 1) * 2) as u32;
            std::ptr::copy_nonoverlapping(name.as_ptr(), (*info).FileName.as_mut_ptr(), name.len());
            if SetFileInformationByHandle(
                self.file.as_raw_handle(),
                FileRenameInfo,
                info.cast(),
                bytes as u32,
            ) == 0
            {
                return Err(FAILED);
            }
        }
        self.published = true;
        Ok(())
    }
    pub(crate) fn receipt(&self) -> (String, u64) {
        (
            self.destination
                .file_name()
                .unwrap()
                .to_string_lossy()
                .into_owned(),
            self.bytes,
        )
    }
}
impl Drop for StagedReport {
    fn drop(&mut self) {
        if !self.published {
            let info = FILE_DISPOSITION_INFO { DeleteFile: true };
            // Delete exactly our held create-new object, not a re-resolved path.
            unsafe {
                SetFileInformationByHandle(
                    self.file.as_raw_handle(),
                    FileDispositionInfo,
                    (&info as *const FILE_DISPOSITION_INFO).cast(),
                    std::mem::size_of_val(&info) as u32,
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::application_sign_in_policy::secure_random_hex;
    use std::fs;
    use std::sync::atomic::{AtomicBool, Ordering};

    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "ro-import-report-{}",
                secure_random_hex::<16>().unwrap()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    fn fragment(after: u32, complete: bool) -> ReportPage {
        ReportPage {
            preview_id: "01900000-0000-7000-8000-000000000001".into(),
            revision: 2,
            record_count: 2,
            next_after: after + 1,
            complete,
            csv: format!(
                "{}{},1,1,parsed,none\r\n",
                if after == 0 { HEADER } else { "" },
                after + 1
            ),
        }
    }
    #[test]
    fn report_stream_publishes_complete_verified_bytes_without_replacing_destination() {
        let fixture = Fixture::new();
        let mut stage = StagedReport::create(&fixture.0, &"a".repeat(32)).unwrap();
        let destination = stage.destination.clone();
        let mut cursor = ReportCursor::new("01900000-0000-7000-8000-000000000001", 2);
        stage
            .append(cursor.accept(fragment(0, false)).unwrap().as_bytes())
            .unwrap();
        stage
            .append(cursor.accept(fragment(1, true)).unwrap().as_bytes())
            .unwrap();
        assert!(!destination.exists());
        assert!(fs::rename(&fixture.0, fixture.0.with_extension("moved")).is_err());
        stage.verify(|| true).unwrap();
        fs::write(&destination, b"existing synthetic report").unwrap();
        assert!(stage.publish().is_err());
        drop(stage);
        assert_eq!(
            fs::read(&destination).unwrap(),
            b"existing synthetic report"
        );
        assert_eq!(fs::read_dir(&fixture.0).unwrap().count(), 1);
        let mut stage = StagedReport::create(&fixture.0, &"b".repeat(32)).unwrap();
        let destination = stage.destination.clone();
        stage.append(HEADER.as_bytes()).unwrap();
        stage.verify(|| true).unwrap();
        stage.publish().unwrap();
        drop(stage);
        assert_eq!(fs::read(destination).unwrap(), HEADER.as_bytes());
    }
    #[test]
    fn report_failure_cancellation_and_private_staging_leave_no_partial_export() {
        let fixture = Fixture::new();
        let mut stage = StagedReport::create(&fixture.0, &"a".repeat(32)).unwrap();
        let staging = stage.staging.clone();
        stage.append(b"synthetic").unwrap();
        assert!(fs::read(&staging).is_err());
        assert!(fs::write(&staging, b"replacement").is_err());
        assert!(stage.publish().is_err()); // Unverified is never publishable.
        let allowed = AtomicBool::new(false);
        assert!(stage.verify(|| allowed.load(Ordering::Acquire)).is_err());
        drop(stage);
        assert_eq!(fs::read_dir(&fixture.0).unwrap().count(), 0);
        assert!(StagedReport::create(&fixture.0, "../escape").is_err());
    }
    #[test]
    fn report_pages_reject_wrong_identity_drift_skips_and_content() {
        let make = || ReportCursor::new("01900000-0000-7000-8000-000000000001", 2);
        let mut wrong = fragment(0, false);
        wrong.revision = 3;
        assert!(make().accept(wrong).is_err());
        let mut wrong = fragment(0, false);
        wrong.preview_id = "01900000-0000-7000-8000-000000000002".into();
        assert!(make().accept(wrong).is_err());
        let mut wrong = fragment(0, false);
        wrong.next_after = 0;
        assert!(make().accept(wrong).is_err());
        let mut wrong = fragment(0, true);
        wrong.record_count = 2;
        assert!(make().accept(wrong).is_err());
        let mut wrong = fragment(0, false);
        wrong.csv = format!("{HEADER}1,1,1,parsed,=unsafe\r\n");
        assert!(make().accept(wrong).is_err());
        let mut wrong = fragment(0, false);
        wrong.csv = format!("{HEADER}2,1,1,parsed,none\r\n");
        assert!(make().accept(wrong).is_err());
        let mut cursor = make();
        cursor.accept(fragment(0, false)).unwrap();
        let mut wrong = fragment(1, true);
        wrong.record_count = 3;
        assert!(cursor.accept(wrong).is_err());
    }

    #[test]
    fn report_streams_one_hundred_thousand_records_with_multiple_diagnostics_and_one_header() {
        let fixture = Fixture::new();
        let preview = "01900000-0000-7000-8000-000000000001";
        let mut cursor = ReportCursor::new(preview, 1);
        let mut stage = StagedReport::create(&fixture.0, &"c".repeat(32)).unwrap();
        let destination = stage.destination.clone();
        while !cursor.complete {
            let mut csv = if cursor.after == 0 {
                HEADER.to_string()
            } else {
                String::new()
            };
            let next = cursor.after + 25;
            for ordinal in cursor.after + 1..=next {
                csv.push_str(&format!("{ordinal},{ordinal},{ordinal},parsed,duplicate-field\r\n{ordinal},{ordinal},{ordinal},parsed,excluded\r\n"));
            }
            assert!(csv.len() < 4096);
            let csv = cursor
                .accept(ReportPage {
                    preview_id: preview.into(),
                    revision: 1,
                    record_count: 100000,
                    next_after: next,
                    complete: next == 100000,
                    csv,
                })
                .unwrap();
            stage.append(csv.as_bytes()).unwrap();
        }
        stage.verify(|| true).unwrap();
        cursor
            .authorize_final(ReportPage {
                preview_id: preview.into(),
                revision: 1,
                record_count: 100000,
                next_after: 100000,
                complete: true,
                csv: String::new(),
            })
            .unwrap();
        stage.publish().unwrap();
        drop(stage);
        let text = fs::read_to_string(destination).unwrap();
        assert_eq!(text.matches(HEADER).count(), 1);
        assert_eq!(text.lines().count(), 200001);
        assert!(text.ends_with("100000,100000,100000,parsed,excluded\r\n"));
    }
}
