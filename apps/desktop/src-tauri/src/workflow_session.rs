//! Native-owned recovery epoch. A dirty launch is never presumed ordinary.
//! Separate from sign-in policy: no researcher, project, path or secret payload.

use crate::application_sign_in_policy::{
    FileAuthority, file_authority, publish_file, read_bounded_file, reject_reparse,
    secure_random_hex, stable_application_data_path,
};
use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

const MARKER_FILE: &str = "workflow-session-v1.json";
const UNAVAILABLE: &str = "RO-WORKFLOW-SESSION-UNAVAILABLE";

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum Disposition {
    Active,
    Ordinary,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Marker {
    schema_version: String,
    resume_epoch: String,
    launch_nonce: String,
    disposition: Disposition,
}

fn identity(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct WorkflowSessionContext {
    pub(crate) resume_epoch: String,
    pub(crate) launch_nonce: String,
    security_generation: u64,
}

#[derive(Default)]
struct SessionState {
    current: Option<WorkflowSessionContext>,
    authority: Option<FileAuthority>,
    applied_security_generation: u64,
    terminal: bool,
}

pub(crate) struct WorkflowSessionAuthority {
    directory: PathBuf,
    path: PathBuf,
    state: Mutex<SessionState>,
    security_generation: Arc<AtomicU64>,
}

impl WorkflowSessionAuthority {
    pub(crate) fn new(application_data: &Path) -> Self {
        let directory = stable_application_data_path(application_data).join("security");
        Self {
            path: directory.join(MARKER_FILE),
            directory,
            state: Mutex::new(SessionState::default()),
            security_generation: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Atomic only: call before immediate process termination, never disk I/O.
    pub(crate) fn invalidate_for_security_lock(&self) {
        self.security_generation.fetch_add(1, Ordering::AcqRel);
    }

    /// Shared with lock admission. Incrementing this must never wait on I/O.
    pub(crate) fn security_latch(&self) -> Arc<AtomicU64> {
        Arc::clone(&self.security_generation)
    }

    fn read(&self, state: &SessionState) -> Result<(Option<Marker>, FileAuthority), &'static str> {
        let authority = file_authority(&self.path).map_err(|_| UNAVAILABLE)?;
        if state
            .authority
            .as_ref()
            .is_some_and(|prior| prior != &authority)
        {
            return Err(UNAVAILABLE);
        }
        let bytes = read_bounded_file(&self.path).map_err(|_| UNAVAILABLE)?;
        let marker = match bytes {
            Some(bytes) => {
                if bytes.len() > 512 {
                    return Err(UNAVAILABLE);
                }
                let marker: Marker = serde_json::from_slice(&bytes).map_err(|_| UNAVAILABLE)?;
                if marker.schema_version != "1.0"
                    || !identity(&marker.resume_epoch)
                    || !identity(&marker.launch_nonce)
                {
                    return Err(UNAVAILABLE);
                }
                Some(marker)
            }
            None => None,
        };
        if file_authority(&self.path).map_err(|_| UNAVAILABLE)? != authority {
            return Err(UNAVAILABLE);
        }
        Ok((marker, authority))
    }

    fn publish(
        &self,
        marker: &Marker,
        prior: &FileAuthority,
        replace: bool,
    ) -> Result<FileAuthority, &'static str> {
        fs::create_dir_all(&self.directory).map_err(|_| UNAVAILABLE)?;
        reject_reparse(&self.directory).map_err(|_| UNAVAILABLE)?;
        let parent = file_authority(&self.directory).map_err(|_| UNAVAILABLE)?;
        let stage = self.directory.join(format!(
            ".{MARKER_FILE}.{}.staging",
            secure_random_hex::<16>().map_err(|_| UNAVAILABLE)?
        ));
        let result = (|| {
            let bytes = serde_json::to_vec(marker).map_err(|_| UNAVAILABLE)?;
            let mut file = OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&stage)
                .map_err(|_| UNAVAILABLE)?;
            file.write_all(&bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| UNAVAILABLE)?;
            drop(file);
            if file_authority(&self.path).map_err(|_| UNAVAILABLE)? != *prior
                || file_authority(&self.directory).map_err(|_| UNAVAILABLE)? != parent
            {
                return Err(UNAVAILABLE);
            }
            publish_file(&stage, &self.path, replace).map_err(|_| UNAVAILABLE)?;
            file_authority(&self.path).map_err(|_| UNAVAILABLE)
        })();
        // Only this exact create-new staging path; never a directory sweep.
        let _ = fs::remove_file(&stage);
        result
    }

    pub(crate) fn prepare_launch(&self) -> Result<WorkflowSessionContext, &'static str> {
        let mut state = self.state.lock().map_err(|_| UNAVAILABLE)?;
        if state.terminal {
            return Err(UNAVAILABLE);
        }
        let generation = self.security_generation.load(Ordering::Acquire);
        let (prior, authority) = self.read(&state)?;
        let unresolved = prior.as_ref().is_some_and(|marker| {
            marker.disposition == Disposition::Active
                && !state.current.as_ref().is_some_and(|context| {
                    context.launch_nonce == marker.launch_nonce
                        && context.resume_epoch == marker.resume_epoch
                        && context.security_generation == generation
                })
        });
        let resume_epoch = match &prior {
            Some(marker) if !unresolved && generation == state.applied_security_generation => {
                marker.resume_epoch.clone()
            }
            _ => secure_random_hex::<16>().map_err(|_| UNAVAILABLE)?,
        };
        let context = WorkflowSessionContext {
            resume_epoch,
            launch_nonce: secure_random_hex::<16>().map_err(|_| UNAVAILABLE)?,
            security_generation: generation,
        };
        let marker = Marker {
            schema_version: "1.0".into(),
            resume_epoch: context.resume_epoch.clone(),
            launch_nonce: context.launch_nonce.clone(),
            disposition: Disposition::Active,
        };
        state.authority = Some(self.publish(&marker, &authority, prior.is_some())?);
        // A concurrent lock wins even if its durable finalizer is still pending.
        if self.security_generation.load(Ordering::Acquire) != generation {
            return Err(UNAVAILABLE);
        }
        state.applied_security_generation = generation;
        state.current = Some(context.clone());
        Ok(context)
    }

    /// After immediate termination. Active spans the *native* lifetime, including
    /// ordinary child stops and no-child intervals; a crash still rotates it.
    pub(crate) fn settle_security(&self) -> Result<(), &'static str> {
        self.prepare_launch().map(|_| ())
    }

    /// Only after lock admission is terminal and supervisor launches/processes
    /// are drained. No later operation may publish through this authority.
    pub(crate) fn seal_terminal(&self) -> Result<(), &'static str> {
        let mut state = self.state.lock().map_err(|_| UNAVAILABLE)?;
        if state.terminal {
            return Err(UNAVAILABLE);
        }
        state.terminal = true;
        let generation = self.security_generation.load(Ordering::Acquire);
        let (prior, authority) = self.read(&state)?;
        let context = state.current.as_ref().ok_or(UNAVAILABLE)?;
        if prior.as_ref().is_none_or(|marker| {
            marker.launch_nonce != context.launch_nonce
                || marker.resume_epoch != context.resume_epoch
        }) {
            return Err(UNAVAILABLE);
        }
        let marker = Marker {
            schema_version: "1.0".into(),
            resume_epoch: if generation != state.applied_security_generation {
                secure_random_hex::<16>().map_err(|_| UNAVAILABLE)?
            } else {
                context.resume_epoch.clone()
            },
            launch_nonce: secure_random_hex::<16>().map_err(|_| UNAVAILABLE)?,
            disposition: Disposition::Ordinary,
        };
        state.authority = Some(self.publish(&marker, &authority, prior.is_some())?);
        state.applied_security_generation = generation;
        state.current = None;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "ro-workflow-session-{}",
            secure_random_hex::<16>().expect("fixture identity")
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn ordinary_restart_retains_epoch_but_unresolved_native_restart_rotates_it() {
        let root = fixture();
        let authority = WorkflowSessionAuthority::new(&root);
        let first = authority.prepare_launch().unwrap();
        authority.seal_terminal().unwrap();
        let restarted = WorkflowSessionAuthority::new(&root);
        let second = restarted.prepare_launch().unwrap();
        assert_eq!(first.resume_epoch, second.resume_epoch);
        assert_ne!(first.launch_nonce, second.launch_nonce);
        let unresolved = WorkflowSessionAuthority::new(&root);
        let third = unresolved.prepare_launch().unwrap();
        assert_ne!(second.resume_epoch, third.resume_epoch);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn same_native_child_restart_keeps_epoch_but_its_death_does_not() {
        let root = fixture();
        let authority = WorkflowSessionAuthority::new(&root);
        let first = authority.prepare_launch().unwrap();
        let second = authority.prepare_launch().unwrap();
        assert_eq!(first.resume_epoch, second.resume_epoch);
        let third = WorkflowSessionAuthority::new(&root)
            .prepare_launch()
            .unwrap();
        assert_ne!(second.resume_epoch, third.resume_epoch);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn security_latch_wins_ordinary_finalizer_and_lock_without_child() {
        let root = fixture();
        let authority = WorkflowSessionAuthority::new(&root);
        let first = authority.prepare_launch().unwrap();
        authority.invalidate_for_security_lock();
        authority.settle_security().unwrap();
        let second = authority.prepare_launch().unwrap();
        assert_ne!(first.resume_epoch, second.resume_epoch);
        authority.invalidate_for_security_lock();
        authority.seal_terminal().unwrap();
        assert!(authority.prepare_launch().is_err());
        assert!(authority.settle_security().is_err());
        let third = WorkflowSessionAuthority::new(&root)
            .prepare_launch()
            .unwrap();
        assert_ne!(second.resume_epoch, third.resume_epoch);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn corrupt_or_replaced_marker_fails_closed_without_rewriting_evidence() {
        let root = fixture();
        let authority = WorkflowSessionAuthority::new(&root);
        authority.prepare_launch().unwrap();
        let path = root.join("security").join(MARKER_FILE);
        fs::write(&path, b"{not-valid}").unwrap();
        assert!(authority.prepare_launch().is_err());
        assert!(authority.seal_terminal().is_err());
        assert!(
            WorkflowSessionAuthority::new(&root)
                .prepare_launch()
                .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), b"{not-valid}");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn lock_without_child_and_crash_before_publication_cannot_resume_old_work() {
        let root = fixture();
        let authority = WorkflowSessionAuthority::new(&root);
        let first = authority.prepare_launch().unwrap();
        // Ordinary child stop deliberately does not publish a clean marker.
        authority.invalidate_for_security_lock();
        let next = WorkflowSessionAuthority::new(&root)
            .prepare_launch()
            .unwrap();
        assert_ne!(first.resume_epoch, next.resume_epoch);
        fs::remove_dir_all(root).unwrap();
    }
}
