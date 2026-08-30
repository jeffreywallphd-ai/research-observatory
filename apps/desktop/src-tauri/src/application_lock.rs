use std::collections::VecDeque;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::application_lock_verification::{
    NativeVerificationProvider, VerificationOutcome, WindowsHelloVerificationProvider,
    WindowsPasswordVerificationProvider,
};
pub use crate::application_sign_in_policy::SignInMode;
use crate::application_sign_in_policy::{
    ApplicationInstanceGuard, PolicyLoadState, PolicySourceAuthority, PolicyStore, SignInPolicy,
    secure_random_hex,
};
use crate::supervisor::{RuntimeState, RuntimeSupervisor};

const MAX_AUDIT_EVENTS: usize = 64;
const TRANSITION_LIFETIME: Duration = Duration::from_secs(5 * 60);
const THREAT_DISCLOSURE: &str =
    "Application-session protection only; this is not Windows-account isolation.";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ApplicationLockState {
    Locked,
    Unlocked,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ApplicationLockReason {
    Manual,
    Inactivity,
    ApplicationRestart,
    ConfigurationInvalid,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum LockConfigurationState {
    Valid,
    Migrated,
    Invalid,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationLockSnapshot {
    pub schema_version: &'static str,
    pub state: ApplicationLockState,
    pub sign_in_mode: SignInMode,
    pub policy_revision: u64,
    pub profile_name: Option<String>,
    pub inactivity_timeout_minutes: u8,
    pub configuration_state: LockConfigurationState,
    pub reason: Option<ApplicationLockReason>,
    pub threat_disclosure: &'static str,
    pub retry_after_seconds: u64,
    pub audit_sequence: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationLockAuditEvent {
    pub sequence: u64,
    pub operation: &'static str,
    pub outcome: &'static str,
    pub reason_code: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApplicationUnlockAttempt {
    pub schema_version: &'static str,
    pub outcome: VerificationOutcome,
    pub reason_code: &'static str,
    pub snapshot: ApplicationLockSnapshot,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum PolicyTransitionOutcome {
    Prepared,
    Committed,
    Cancelled,
    Denied,
    Unavailable,
    Busy,
    Failed,
    Conflict,
    Expired,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PolicyTransitionResult {
    pub schema_version: &'static str,
    pub outcome: PolicyTransitionOutcome,
    pub reason_code: &'static str,
    pub handle: Option<String>,
    pub source_mode: Option<SignInMode>,
    pub target_mode: SignInMode,
    pub warning_required: bool,
    pub snapshot: ApplicationLockSnapshot,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum TransitionProofClass {
    ConfiguredProvider,
    SameSidPasswordRecovery,
}

#[derive(Clone, Debug)]
struct PendingTransition {
    handle_digest: String,
    source: PolicySourceAuthority,
    source_mode: Option<SignInMode>,
    target: SignInPolicy,
    target_digest: String,
    generation: u64,
    proof_class: TransitionProofClass,
    warning_required: bool,
    expires_at: Instant,
}

#[derive(Clone, Debug)]
struct CompletedTransition {
    handle_digest: String,
    receipt: PolicyTransitionResult,
}

struct ApplicationLockInner {
    state: ApplicationLockState,
    reason: Option<ApplicationLockReason>,
    configuration_state: LockConfigurationState,
    policy: SignInPolicy,
    policy_source: PolicySourceAuthority,
    generation: u64,
    last_activity: Instant,
    failed_attempts: u8,
    retry_at: Option<Instant>,
    reauthentication_in_progress: bool,
    pending_transition: Option<PendingTransition>,
    completed_transition: Option<CompletedTransition>,
    audit_sequence: u64,
    audit: VecDeque<ApplicationLockAuditEvent>,
}

impl ApplicationLockInner {
    fn snapshot(&self) -> ApplicationLockSnapshot {
        ApplicationLockSnapshot {
            schema_version: "1.0",
            state: self.state,
            sign_in_mode: self.policy.mode,
            policy_revision: self.policy.revision(),
            profile_name: (self.state == ApplicationLockState::Unlocked)
                .then(|| self.policy.profile_name.clone())
                .flatten(),
            inactivity_timeout_minutes: self.policy.inactivity_timeout_minutes,
            configuration_state: self.configuration_state,
            reason: self.reason,
            threat_disclosure: THREAT_DISCLOSURE,
            retry_after_seconds: self
                .retry_at
                .and_then(|deadline| deadline.checked_duration_since(Instant::now()))
                .map(|remaining| remaining.as_secs().saturating_add(1))
                .unwrap_or(0),
            audit_sequence: self.audit_sequence,
        }
    }

    fn record(
        &mut self,
        operation: &'static str,
        outcome: &'static str,
        reason_code: &'static str,
    ) {
        self.audit_sequence = self.audit_sequence.saturating_add(1);
        if self.audit.len() == MAX_AUDIT_EVENTS {
            self.audit.pop_front();
        }
        self.audit.push_back(ApplicationLockAuditEvent {
            sequence: self.audit_sequence,
            operation,
            outcome,
            reason_code,
        });
    }

    fn lock(&mut self, reason: ApplicationLockReason) -> bool {
        if !self.policy.mode.is_protected() {
            return false;
        }
        if self.state == ApplicationLockState::Locked {
            if self.reauthentication_in_progress {
                self.generation = self.generation.saturating_add(1);
            }
            return false;
        }
        self.generation = self.generation.saturating_add(1);
        self.state = ApplicationLockState::Locked;
        self.reason = Some(reason);
        self.record("application-lock", "locked", reason_code(reason));
        true
    }
}

#[derive(Clone)]
pub struct ApplicationLockManager {
    policy_store: PolicyStore,
    shared: Arc<Mutex<ApplicationLockInner>>,
    _instance_guard: Option<Arc<ApplicationInstanceGuard>>,
}

impl ApplicationLockManager {
    pub fn acquire(application_data: &Path) -> Result<Self, &'static str> {
        let guard = Arc::new(ApplicationInstanceGuard::acquire(application_data)?);
        Ok(Self::from_application_data(application_data, Some(guard)))
    }

    #[cfg(test)]
    pub(crate) fn new(application_data: &Path) -> Self {
        Self::from_application_data(application_data, None)
    }

    fn from_application_data(
        application_data: &Path,
        instance_guard: Option<Arc<ApplicationInstanceGuard>>,
    ) -> Self {
        let policy_store = PolicyStore::new(application_data);
        let loaded = policy_store.initialize();
        let configuration_state = match loaded.state {
            PolicyLoadState::Valid => LockConfigurationState::Valid,
            PolicyLoadState::Migrated => LockConfigurationState::Migrated,
            PolicyLoadState::Invalid => LockConfigurationState::Invalid,
        };
        let (state, reason) = match loaded.state {
            PolicyLoadState::Invalid => (
                ApplicationLockState::Locked,
                Some(ApplicationLockReason::ConfigurationInvalid),
            ),
            PolicyLoadState::Valid | PolicyLoadState::Migrated
                if loaded.policy.mode.is_protected()
                    && loaded.policy.inactivity_timeout_minutes > 0 =>
            {
                (
                    ApplicationLockState::Locked,
                    Some(ApplicationLockReason::ApplicationRestart),
                )
            }
            PolicyLoadState::Valid | PolicyLoadState::Migrated => {
                (ApplicationLockState::Unlocked, None)
            }
        };
        let mut inner = ApplicationLockInner {
            state,
            reason,
            configuration_state,
            policy: loaded.policy,
            policy_source: loaded.source,
            generation: u64::from(state == ApplicationLockState::Locked),
            last_activity: Instant::now(),
            failed_attempts: 0,
            retry_at: None,
            reauthentication_in_progress: false,
            pending_transition: None,
            completed_transition: None,
            audit_sequence: 0,
            audit: VecDeque::new(),
        };
        if let Some(reason) = reason {
            inner.record("application-start", "locked", reason_code(reason));
        }
        Self {
            policy_store,
            shared: Arc::new(Mutex::new(inner)),
            _instance_guard: instance_guard,
        }
    }

    pub fn status(&self) -> ApplicationLockSnapshot {
        self.shared.lock().expect("lock mutex poisoned").snapshot()
    }

    pub fn audit(&self) -> Vec<ApplicationLockAuditEvent> {
        self.shared
            .lock()
            .expect("lock mutex poisoned")
            .audit
            .iter()
            .cloned()
            .collect()
    }

    pub fn is_unlocked(&self) -> bool {
        self.shared.lock().expect("lock mutex poisoned").state == ApplicationLockState::Unlocked
    }

    pub fn begin_protected_action(&self) -> Result<u64, &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked {
            return Err("RO-APPLICATION-LOCKED");
        }
        Ok(inner.generation)
    }

    pub fn finish_protected_action(&self, generation: u64) -> Result<(), &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked || inner.generation != generation {
            return Err("RO-APPLICATION-LOCKED");
        }
        Ok(())
    }

    pub fn commit_protected_action<T>(
        &self,
        generation: u64,
        commit: impl FnOnce() -> Result<T, &'static str>,
    ) -> Result<T, &'static str> {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Unlocked || inner.generation != generation {
            return Err("RO-APPLICATION-LOCKED");
        }
        commit()
    }

    pub fn lock(&self, reason: ApplicationLockReason) -> (ApplicationLockSnapshot, bool) {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        let changed = inner.lock(reason);
        (inner.snapshot(), changed)
    }

    pub fn record_activity(&self) {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state == ApplicationLockState::Unlocked {
            inner.last_activity = Instant::now();
        }
    }

    pub fn record_notification_failure(&self) {
        self.shared.lock().expect("lock mutex poisoned").record(
            "application-lock-notification",
            "failed",
            "RO-LOCK-NOTIFICATION-FAILED",
        );
    }

    pub fn lock_if_idle(&self) -> Option<ApplicationLockSnapshot> {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        let timeout = inner.policy.inactivity_timeout_minutes;
        if inner.state == ApplicationLockState::Unlocked
            && inner.policy.mode.is_protected()
            && timeout > 0
            && inner.last_activity.elapsed() >= Duration::from_secs(u64::from(timeout) * 60)
            && inner.lock(ApplicationLockReason::Inactivity)
        {
            Some(inner.snapshot())
        } else {
            None
        }
    }

    pub fn prepare_policy_transition(
        &self,
        target_mode: SignInMode,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
        hello_window: Option<isize>,
    ) -> Result<PolicyTransitionResult, &'static str> {
        self.prepare_policy_transition_with(
            target_mode,
            profile_name,
            inactivity_timeout_minutes,
            |mode| verify_system_mode(mode, hello_window),
        )
    }

    fn prepare_policy_transition_with(
        &self,
        target_mode: SignInMode,
        profile_name: Option<String>,
        inactivity_timeout_minutes: u8,
        mut verify: impl FnMut(SignInMode) -> VerificationOutcome,
    ) -> Result<PolicyTransitionResult, &'static str> {
        let (source_mode, source, generation, target, snapshot) = {
            let mut inner = self.shared.lock().expect("lock mutex poisoned");
            expire_pending_transition(&mut inner);
            if inner.configuration_state == LockConfigurationState::Invalid {
                return Ok(transition_result(
                    &inner,
                    PolicyTransitionOutcome::Denied,
                    "RO-SIGN-IN-TRANSITION-RECOVERY-REQUIRED",
                    None,
                    None,
                    target_mode,
                    false,
                ));
            }
            if inner.state != ApplicationLockState::Unlocked {
                return Ok(transition_result(
                    &inner,
                    PolicyTransitionOutcome::Denied,
                    "RO-SIGN-IN-TRANSITION-APPLICATION-LOCKED",
                    None,
                    Some(inner.policy.mode),
                    target_mode,
                    false,
                ));
            }
            if inner.reauthentication_in_progress {
                return Ok(transition_result(
                    &inner,
                    PolicyTransitionOutcome::Busy,
                    "RO-SIGN-IN-TRANSITION-BUSY",
                    None,
                    Some(inner.policy.mode),
                    target_mode,
                    false,
                ));
            }
            let target = SignInPolicy::normalized_target(
                inner
                    .policy
                    .revision()
                    .checked_add(1)
                    .ok_or("RO-SIGN-IN-POLICY-REVISION-EXHAUSTED")?,
                target_mode,
                profile_name,
                inactivity_timeout_minutes,
            )?;
            inner.reauthentication_in_progress = true;
            (
                inner.policy.mode,
                inner.policy_source.clone(),
                inner.generation,
                target,
                inner.snapshot(),
            )
        };
        let mut reservation =
            TransitionPreparationReservation::new(Arc::clone(&self.shared), generation);

        let mut proof_modes = Vec::with_capacity(2);
        if source_mode.is_protected() {
            proof_modes.push(source_mode);
        }
        if target_mode.is_protected() && target_mode != source_mode {
            proof_modes.push(target_mode);
        }
        for proof_mode in proof_modes {
            let outcome = verify(proof_mode);
            if outcome != VerificationOutcome::Succeeded {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.record(
                    "application-sign-in-transition-prepare",
                    verification_audit_outcome(outcome),
                    transition_verification_reason(outcome),
                );
                return Ok(transition_result(
                    &inner,
                    transition_outcome(outcome),
                    transition_verification_reason(outcome),
                    None,
                    Some(source_mode),
                    target_mode,
                    false,
                ));
            }
        }

        let handle = secure_random_hex::<32>()?;
        let handle_digest = sha256_hex(handle.as_bytes());
        let target_digest = sha256_hex(&target.canonical_bytes()?);
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.generation != generation
            || inner.state != snapshot.state
            || inner.configuration_state == LockConfigurationState::Invalid
            || inner.policy_source != source
            || !inner.reauthentication_in_progress
        {
            inner.record(
                "application-sign-in-transition-prepare",
                "failed",
                "RO-SIGN-IN-TRANSITION-STALE",
            );
            return Ok(transition_result(
                &inner,
                PolicyTransitionOutcome::Conflict,
                "RO-SIGN-IN-TRANSITION-STALE",
                None,
                Some(source_mode),
                target_mode,
                false,
            ));
        }
        inner.pending_transition = Some(PendingTransition {
            handle_digest,
            source,
            source_mode: Some(source_mode),
            target,
            target_digest,
            generation,
            proof_class: TransitionProofClass::ConfiguredProvider,
            warning_required: source_mode.is_protected() && target_mode == SignInMode::None,
            expires_at: Instant::now() + TRANSITION_LIFETIME,
        });
        inner.record(
            "application-sign-in-transition-prepare",
            "prepared",
            "RO-SIGN-IN-TRANSITION-PREPARED",
        );
        reservation.retain();
        Ok(transition_result(
            &inner,
            PolicyTransitionOutcome::Prepared,
            "RO-SIGN-IN-TRANSITION-PREPARED",
            Some(handle),
            Some(source_mode),
            target_mode,
            source_mode.is_protected() && target_mode == SignInMode::None,
        ))
    }

    pub fn prepare_password_recovery_reset(&self) -> Result<PolicyTransitionResult, &'static str> {
        self.prepare_password_recovery_reset_with(|| WindowsPasswordVerificationProvider.verify())
    }

    fn prepare_password_recovery_reset_with(
        &self,
        verify: impl FnOnce() -> VerificationOutcome,
    ) -> Result<PolicyTransitionResult, &'static str> {
        let (source_mode, source, generation, target) = {
            let mut inner = self.shared.lock().expect("lock mutex poisoned");
            expire_pending_transition(&mut inner);
            if inner.configuration_state != LockConfigurationState::Invalid
                && !inner.policy.mode.is_protected()
            {
                return Ok(transition_result(
                    &inner,
                    PolicyTransitionOutcome::Denied,
                    "RO-SIGN-IN-RECOVERY-NOT-REQUIRED",
                    None,
                    Some(inner.policy.mode),
                    SignInMode::None,
                    true,
                ));
            }
            if inner.reauthentication_in_progress {
                return Ok(transition_result(
                    &inner,
                    PolicyTransitionOutcome::Busy,
                    "RO-SIGN-IN-TRANSITION-BUSY",
                    None,
                    (inner.configuration_state != LockConfigurationState::Invalid)
                        .then_some(inner.policy.mode),
                    SignInMode::None,
                    true,
                ));
            }
            let target = SignInPolicy::normalized_target(
                inner
                    .policy
                    .revision()
                    .checked_add(1)
                    .ok_or("RO-SIGN-IN-POLICY-REVISION-EXHAUSTED")?,
                SignInMode::None,
                None,
                0,
            )?;
            inner.reauthentication_in_progress = true;
            (
                (inner.configuration_state != LockConfigurationState::Invalid)
                    .then_some(inner.policy.mode),
                inner.policy_source.clone(),
                inner.generation,
                target,
            )
        };
        let mut reservation =
            TransitionPreparationReservation::new(Arc::clone(&self.shared), generation);
        let outcome = verify();
        if outcome != VerificationOutcome::Succeeded {
            let mut inner = self.shared.lock().expect("lock mutex poisoned");
            inner.record(
                "application-sign-in-recovery-prepare",
                verification_audit_outcome(outcome),
                transition_verification_reason(outcome),
            );
            return Ok(transition_result(
                &inner,
                transition_outcome(outcome),
                transition_verification_reason(outcome),
                None,
                source_mode,
                SignInMode::None,
                true,
            ));
        }

        let handle = secure_random_hex::<32>()?;
        let handle_digest = sha256_hex(handle.as_bytes());
        let target_digest = sha256_hex(&target.canonical_bytes()?);
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.generation != generation
            || inner.policy_source != source
            || !inner.reauthentication_in_progress
        {
            inner.record(
                "application-sign-in-recovery-prepare",
                "failed",
                "RO-SIGN-IN-TRANSITION-STALE",
            );
            return Ok(transition_result(
                &inner,
                PolicyTransitionOutcome::Conflict,
                "RO-SIGN-IN-TRANSITION-STALE",
                None,
                source_mode,
                SignInMode::None,
                true,
            ));
        }
        inner.pending_transition = Some(PendingTransition {
            handle_digest,
            source,
            source_mode,
            target,
            target_digest,
            generation,
            proof_class: TransitionProofClass::SameSidPasswordRecovery,
            warning_required: true,
            expires_at: Instant::now() + TRANSITION_LIFETIME,
        });
        inner.record(
            "application-sign-in-recovery-prepare",
            "prepared",
            "RO-SIGN-IN-RECOVERY-PREPARED",
        );
        reservation.retain();
        Ok(transition_result(
            &inner,
            PolicyTransitionOutcome::Prepared,
            "RO-SIGN-IN-RECOVERY-PREPARED",
            Some(handle),
            source_mode,
            SignInMode::None,
            true,
        ))
    }

    pub fn commit_policy_transition(
        &self,
        handle: &str,
        confirmed: bool,
    ) -> PolicyTransitionResult {
        let handle_digest = sha256_hex(handle.as_bytes());
        let pending = {
            let mut inner = self.shared.lock().expect("lock mutex poisoned");
            if let Some(completed) = &inner.completed_transition
                && completed.handle_digest == handle_digest
            {
                return completed.receipt.clone();
            }
            if let Some(expired) = inner.pending_transition.clone()
                && expired.handle_digest == handle_digest
                && expired.expires_at <= Instant::now()
            {
                inner.pending_transition = None;
                inner.reauthentication_in_progress = false;
                inner.record(
                    "application-sign-in-transition",
                    "expired",
                    "RO-SIGN-IN-TRANSITION-EXPIRED",
                );
                return transition_result(
                    &inner,
                    PolicyTransitionOutcome::Expired,
                    "RO-SIGN-IN-TRANSITION-EXPIRED",
                    None,
                    expired.source_mode,
                    expired.target.mode,
                    expired.warning_required,
                );
            }
            expire_pending_transition(&mut inner);
            let Some(pending) = inner.pending_transition.clone() else {
                return transition_result(
                    &inner,
                    PolicyTransitionOutcome::Denied,
                    "RO-SIGN-IN-TRANSITION-HANDLE-INVALID",
                    None,
                    None,
                    SignInMode::None,
                    false,
                );
            };
            if pending.handle_digest != handle_digest {
                return transition_result(
                    &inner,
                    PolicyTransitionOutcome::Denied,
                    "RO-SIGN-IN-TRANSITION-HANDLE-INVALID",
                    None,
                    pending.source_mode,
                    pending.target.mode,
                    pending.warning_required,
                );
            }
            if !confirmed {
                inner.pending_transition = None;
                inner.reauthentication_in_progress = false;
                inner.record(
                    "application-sign-in-transition-commit",
                    "cancelled",
                    "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
                );
                return transition_result(
                    &inner,
                    PolicyTransitionOutcome::Cancelled,
                    "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
                    None,
                    pending.source_mode,
                    pending.target.mode,
                    pending.warning_required,
                );
            }
            pending
        };

        let _process_guard = match self.policy_store.lock() {
            Ok(guard) => guard,
            Err(_) => {
                return self.transition_failure(
                    &pending,
                    PolicyTransitionOutcome::Failed,
                    "RO-SIGN-IN-TRANSITION-LOCK-FAILED",
                );
            }
        };
        let staged = match self.policy_store.stage(&pending.target) {
            Ok(staged) => staged,
            Err(_) => {
                return self.transition_failure(
                    &pending,
                    PolicyTransitionOutcome::Failed,
                    "RO-SIGN-IN-TRANSITION-WRITE-FAILED",
                );
            }
        };
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.generation != pending.generation
            || inner.policy_source != pending.source
            || inner
                .pending_transition
                .as_ref()
                .is_none_or(|current| current.handle_digest != pending.handle_digest)
            || !inner.reauthentication_in_progress
            || pending
                .target
                .canonical_bytes()
                .map_or(true, |bytes| sha256_hex(&bytes) != pending.target_digest)
        {
            inner.pending_transition = None;
            inner.reauthentication_in_progress = false;
            inner.record(
                "application-sign-in-transition-commit",
                "conflict",
                "RO-SIGN-IN-TRANSITION-STALE",
            );
            return transition_result(
                &inner,
                PolicyTransitionOutcome::Conflict,
                "RO-SIGN-IN-TRANSITION-STALE",
                None,
                pending.source_mode,
                pending.target.mode,
                pending.warning_required,
            );
        }
        let publish = self.policy_store.publish(staged, &pending.source);
        let source = match publish {
            Ok(source) => source,
            Err("RO-SIGN-IN-POLICY-CONFLICT") => {
                inner.pending_transition = None;
                inner.reauthentication_in_progress = false;
                inner.record(
                    "application-sign-in-transition-commit",
                    "conflict",
                    "RO-SIGN-IN-TRANSITION-CONFLICT",
                );
                return transition_result(
                    &inner,
                    PolicyTransitionOutcome::Conflict,
                    "RO-SIGN-IN-TRANSITION-CONFLICT",
                    None,
                    pending.source_mode,
                    pending.target.mode,
                    pending.warning_required,
                );
            }
            Err(_) => match self.policy_store.committed_source(&pending.target) {
                Ok(Some(source)) => source,
                Ok(None) | Err(_) => {
                    inner.record(
                        "application-sign-in-transition-commit",
                        "failed",
                        "RO-SIGN-IN-TRANSITION-WRITE-FAILED",
                    );
                    return transition_result(
                        &inner,
                        PolicyTransitionOutcome::Failed,
                        "RO-SIGN-IN-TRANSITION-WRITE-FAILED",
                        None,
                        pending.source_mode,
                        pending.target.mode,
                        pending.warning_required,
                    );
                }
            },
        };

        inner.policy = pending.target.clone();
        inner.policy_source = source;
        inner.configuration_state = LockConfigurationState::Valid;
        inner.generation = inner.generation.saturating_add(1);
        inner.state = ApplicationLockState::Unlocked;
        inner.reason = None;
        inner.last_activity = Instant::now();
        inner.pending_transition = None;
        inner.reauthentication_in_progress = false;
        inner.record(
            "application-sign-in-transition-commit",
            "committed",
            match pending.proof_class {
                TransitionProofClass::ConfiguredProvider => "RO-SIGN-IN-TRANSITION-COMMITTED",
                TransitionProofClass::SameSidPasswordRecovery => "RO-SIGN-IN-RECOVERY-COMMITTED",
            },
        );
        let reason_code = match pending.proof_class {
            TransitionProofClass::ConfiguredProvider => "RO-SIGN-IN-TRANSITION-COMMITTED",
            TransitionProofClass::SameSidPasswordRecovery => "RO-SIGN-IN-RECOVERY-COMMITTED",
        };
        let receipt = transition_result(
            &inner,
            PolicyTransitionOutcome::Committed,
            reason_code,
            None,
            pending.source_mode,
            pending.target.mode,
            pending.warning_required,
        );
        inner.completed_transition = Some(CompletedTransition {
            handle_digest,
            receipt: receipt.clone(),
        });
        receipt
    }

    fn transition_failure(
        &self,
        pending: &PendingTransition,
        outcome: PolicyTransitionOutcome,
        reason_code: &'static str,
    ) -> PolicyTransitionResult {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        inner.record(
            "application-sign-in-transition-commit",
            "failed",
            reason_code,
        );
        transition_result(
            &inner,
            outcome,
            reason_code,
            None,
            pending.source_mode,
            pending.target.mode,
            pending.warning_required,
        )
    }

    pub fn reauthenticate(
        &self,
        supervisor: &RuntimeSupervisor,
        hello_window: Option<isize>,
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        let mode = {
            let inner = self.shared.lock().expect("lock mutex poisoned");
            if inner.configuration_state == LockConfigurationState::Invalid {
                return Err("RO-LOCK-RECOVERY-REQUIRED");
            }
            inner.policy.mode
        };
        match mode {
            SignInMode::None => Err("RO-LOCK-AUTH-NOT-PROTECTED"),
            SignInMode::WindowsPassword => self.reauthenticate_with_native_provider(
                supervisor,
                &WindowsPasswordVerificationProvider,
            ),
            SignInMode::WindowsHello => {
                let provider = hello_provider(hello_window)?;
                self.reauthenticate_with_native_provider(supervisor, &provider)
            }
        }
    }

    pub(crate) fn reauthenticate_with_native_provider(
        &self,
        supervisor: &RuntimeSupervisor,
        provider: &impl NativeVerificationProvider,
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        self.reauthenticate_with(
            provider,
            || supervisor.start().state,
            || {
                supervisor.stop_for_application_lock();
            },
        )
    }

    fn reauthenticate_with(
        &self,
        provider: &impl NativeVerificationProvider,
        start_core: impl FnOnce() -> RuntimeState,
        stop_core: impl FnOnce(),
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        let reservation = match self.reserve_reauthentication() {
            Ok(reservation) => reservation,
            Err(ReauthenticationReservationError::Attempt(attempt)) => return Ok(*attempt),
            Err(ReauthenticationReservationError::InvalidState(reason_code)) => {
                return Err(reason_code);
            }
        };
        let verification = provider.verify();
        if !self.reauthentication_is_current(&reservation) {
            return Ok(self.stale_reauthentication_attempt());
        }
        let result = match verification {
            VerificationOutcome::Cancelled => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "cancelled", "RO-LOCK-AUTH-CANCELLED");
                unlock_attempt(
                    &inner,
                    VerificationOutcome::Cancelled,
                    "RO-LOCK-AUTH-CANCELLED",
                )
            }
            VerificationOutcome::Denied => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.failed_attempts = inner.failed_attempts.saturating_add(1);
                let exponent = inner.failed_attempts.saturating_sub(1).min(5);
                inner.retry_at = Some(Instant::now() + Duration::from_secs(1_u64 << exponent));
                inner.record("application-unlock", "denied", "RO-LOCK-AUTH-DENIED");
                unlock_attempt(&inner, VerificationOutcome::Denied, "RO-LOCK-AUTH-DENIED")
            }
            VerificationOutcome::Unavailable => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record(
                    "application-unlock",
                    "unavailable",
                    "RO-LOCK-AUTH-UNAVAILABLE",
                );
                unlock_attempt(
                    &inner,
                    VerificationOutcome::Unavailable,
                    "RO-LOCK-AUTH-UNAVAILABLE",
                )
            }
            VerificationOutcome::Busy => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "busy", "RO-LOCK-AUTH-BUSY");
                unlock_attempt(&inner, VerificationOutcome::Busy, "RO-LOCK-AUTH-BUSY")
            }
            VerificationOutcome::Failed => {
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                inner.reauthentication_in_progress = false;
                inner.record("application-unlock", "failed", "RO-LOCK-AUTH-FAILED");
                unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-FAILED")
            }
            VerificationOutcome::Succeeded => {
                if start_core() != RuntimeState::Ready {
                    let mut inner = self.shared.lock().expect("lock mutex poisoned");
                    inner.reauthentication_in_progress = false;
                    inner.record("application-unlock", "failed", "RO-LOCK-CORE-UNAVAILABLE");
                    let attempt = unlock_attempt(
                        &inner,
                        VerificationOutcome::Failed,
                        "RO-LOCK-CORE-UNAVAILABLE",
                    );
                    drop(inner);
                    stop_core();
                    return Ok(attempt);
                }
                let mut inner = self.shared.lock().expect("lock mutex poisoned");
                if inner.state != ApplicationLockState::Locked
                    || inner.generation != reservation.generation
                {
                    inner.reauthentication_in_progress = false;
                    inner.record("application-unlock", "failed", "RO-LOCK-AUTH-STALE");
                    let attempt =
                        unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-STALE");
                    drop(inner);
                    stop_core();
                    return Ok(attempt);
                }
                inner.reauthentication_in_progress = false;
                inner.state = ApplicationLockState::Unlocked;
                inner.reason = None;
                inner.failed_attempts = 0;
                inner.retry_at = None;
                inner.last_activity = Instant::now();
                inner.record("application-unlock", "succeeded", "RO-LOCK-UNLOCKED");
                unlock_attempt(&inner, VerificationOutcome::Succeeded, "RO-LOCK-UNLOCKED")
            }
        };
        drop(reservation);
        Ok(result)
    }

    fn reauthentication_is_current(&self, reservation: &ReauthenticationReservation) -> bool {
        let inner = self.shared.lock().expect("lock mutex poisoned");
        inner.state == ApplicationLockState::Locked
            && inner.reauthentication_in_progress
            && inner.generation == reservation.generation
    }

    fn stale_reauthentication_attempt(&self) -> ApplicationUnlockAttempt {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        inner.reauthentication_in_progress = false;
        inner.record("application-unlock", "failed", "RO-LOCK-AUTH-STALE");
        unlock_attempt(&inner, VerificationOutcome::Failed, "RO-LOCK-AUTH-STALE")
    }

    fn reserve_reauthentication(
        &self,
    ) -> Result<ReauthenticationReservation, ReauthenticationReservationError> {
        let mut inner = self.shared.lock().expect("lock mutex poisoned");
        if inner.state != ApplicationLockState::Locked {
            inner.record("application-unlock", "failed", "RO-LOCK-AUTH-NOT-LOCKED");
            return Err(ReauthenticationReservationError::InvalidState(
                "RO-LOCK-AUTH-NOT-LOCKED",
            ));
        }
        if inner.reauthentication_in_progress
            || inner
                .retry_at
                .is_some_and(|deadline| deadline > Instant::now())
        {
            inner.record("application-unlock", "denied", "RO-LOCK-RATE-LIMITED");
            return Err(ReauthenticationReservationError::Attempt(Box::new(
                unlock_attempt(&inner, VerificationOutcome::Busy, "RO-LOCK-RATE-LIMITED"),
            )));
        }
        inner.reauthentication_in_progress = true;
        Ok(ReauthenticationReservation {
            shared: Arc::clone(&self.shared),
            generation: inner.generation,
        })
    }

    #[cfg(test)]
    fn complete_test_reauthentication(
        &self,
        result: VerificationOutcome,
        core_ready: bool,
    ) -> Result<ApplicationUnlockAttempt, &'static str> {
        self.reauthenticate_with(
            &|| result,
            || {
                if core_ready {
                    RuntimeState::Ready
                } else {
                    RuntimeState::RecoveryRequired
                }
            },
            || {},
        )
    }
}

fn unlock_attempt(
    inner: &ApplicationLockInner,
    outcome: VerificationOutcome,
    reason_code: &'static str,
) -> ApplicationUnlockAttempt {
    ApplicationUnlockAttempt {
        schema_version: "1.0",
        outcome,
        reason_code,
        snapshot: inner.snapshot(),
    }
}

struct ReauthenticationReservation {
    shared: Arc<Mutex<ApplicationLockInner>>,
    generation: u64,
}

enum ReauthenticationReservationError {
    Attempt(Box<ApplicationUnlockAttempt>),
    InvalidState(&'static str),
}

impl Drop for ReauthenticationReservation {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.shared.lock() {
            inner.reauthentication_in_progress = false;
        }
    }
}

struct TransitionPreparationReservation {
    shared: Arc<Mutex<ApplicationLockInner>>,
    generation: u64,
    retained: bool,
}

impl TransitionPreparationReservation {
    fn new(shared: Arc<Mutex<ApplicationLockInner>>, generation: u64) -> Self {
        Self {
            shared,
            generation,
            retained: false,
        }
    }

    fn retain(&mut self) {
        self.retained = true;
    }
}

impl Drop for TransitionPreparationReservation {
    fn drop(&mut self) {
        if self.retained {
            return;
        }
        if let Ok(mut inner) = self.shared.lock()
            && inner.generation == self.generation
        {
            inner.reauthentication_in_progress = false;
        }
    }
}

fn expire_pending_transition(inner: &mut ApplicationLockInner) {
    if inner
        .pending_transition
        .as_ref()
        .is_some_and(|pending| pending.expires_at <= Instant::now())
    {
        inner.pending_transition = None;
        inner.reauthentication_in_progress = false;
        inner.record(
            "application-sign-in-transition",
            "expired",
            "RO-SIGN-IN-TRANSITION-EXPIRED",
        );
    }
}

fn transition_result(
    inner: &ApplicationLockInner,
    outcome: PolicyTransitionOutcome,
    reason_code: &'static str,
    handle: Option<String>,
    source_mode: Option<SignInMode>,
    target_mode: SignInMode,
    warning_required: bool,
) -> PolicyTransitionResult {
    PolicyTransitionResult {
        schema_version: "1.0",
        outcome,
        reason_code,
        handle,
        source_mode,
        target_mode,
        warning_required,
        snapshot: inner.snapshot(),
    }
}

fn transition_outcome(outcome: VerificationOutcome) -> PolicyTransitionOutcome {
    match outcome {
        VerificationOutcome::Succeeded => PolicyTransitionOutcome::Prepared,
        VerificationOutcome::Cancelled => PolicyTransitionOutcome::Cancelled,
        VerificationOutcome::Denied => PolicyTransitionOutcome::Denied,
        VerificationOutcome::Unavailable => PolicyTransitionOutcome::Unavailable,
        VerificationOutcome::Busy => PolicyTransitionOutcome::Busy,
        VerificationOutcome::Failed => PolicyTransitionOutcome::Failed,
    }
}

fn transition_verification_reason(outcome: VerificationOutcome) -> &'static str {
    match outcome {
        VerificationOutcome::Succeeded => "RO-SIGN-IN-TRANSITION-AUTH-SUCCEEDED",
        VerificationOutcome::Cancelled => "RO-SIGN-IN-TRANSITION-AUTH-CANCELLED",
        VerificationOutcome::Denied => "RO-SIGN-IN-TRANSITION-AUTH-DENIED",
        VerificationOutcome::Unavailable => "RO-SIGN-IN-TRANSITION-AUTH-UNAVAILABLE",
        VerificationOutcome::Busy => "RO-SIGN-IN-TRANSITION-AUTH-BUSY",
        VerificationOutcome::Failed => "RO-SIGN-IN-TRANSITION-AUTH-FAILED",
    }
}

fn verification_audit_outcome(outcome: VerificationOutcome) -> &'static str {
    match outcome {
        VerificationOutcome::Succeeded => "succeeded",
        VerificationOutcome::Cancelled => "cancelled",
        VerificationOutcome::Denied => "denied",
        VerificationOutcome::Unavailable => "unavailable",
        VerificationOutcome::Busy => "busy",
        VerificationOutcome::Failed => "failed",
    }
}

fn verify_system_mode(mode: SignInMode, hello_window: Option<isize>) -> VerificationOutcome {
    match mode {
        SignInMode::None => VerificationOutcome::Succeeded,
        SignInMode::WindowsPassword => WindowsPasswordVerificationProvider.verify(),
        SignInMode::WindowsHello => hello_window
            .and_then(|window| WindowsHelloVerificationProvider::for_window(window).ok())
            .map(|provider| provider.verify())
            .unwrap_or(VerificationOutcome::Failed),
    }
}

fn hello_provider(
    hello_window: Option<isize>,
) -> Result<WindowsHelloVerificationProvider, &'static str> {
    hello_window
        .ok_or("RO-LOCK-HELLO-WINDOW-UNAVAILABLE")
        .and_then(WindowsHelloVerificationProvider::for_window)
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn reason_code(reason: ApplicationLockReason) -> &'static str {
    match reason {
        ApplicationLockReason::Manual => "RO-LOCK-MANUAL",
        ApplicationLockReason::Inactivity => "RO-LOCK-INACTIVITY",
        ApplicationLockReason::ApplicationRestart => "RO-LOCK-APPLICATION-RESTART",
        ApplicationLockReason::ConfigurationInvalid => "RO-LOCK-CONFIGURATION-INVALID",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::{BufRead, BufReader, Write};
    use std::path::PathBuf;
    use std::process::{Child, Command, Stdio};
    use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
    use std::sync::mpsc;
    use std::thread;

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    fn root(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "research-observatory-lock-test-{name}-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn manager_at(
        root: &Path,
        mode: SignInMode,
        inactivity_timeout_minutes: u8,
    ) -> ApplicationLockManager {
        let store = PolicyStore::new(&root);
        let loaded = store.initialize();
        let policy = SignInPolicy::normalized_target(2, mode, None, inactivity_timeout_minutes)
            .expect("test policy");
        let _guard = store.lock().expect("policy lock");
        let staged = store.stage(&policy).expect("stage test policy");
        store
            .publish(staged, &loaded.source)
            .expect("publish test policy");
        drop(_guard);
        ApplicationLockManager::new(&root)
    }

    fn manager() -> ApplicationLockManager {
        manager_at(&root("password"), SignInMode::WindowsPassword, 0)
    }

    fn default_manager() -> ApplicationLockManager {
        ApplicationLockManager::new(&root("default"))
    }

    #[cfg(windows)]
    fn spawn_policy_child(application_data: &Path, action: &str) -> Child {
        let mut child = Command::new(std::env::current_exe().expect("current test executable"))
            .args([
                "--exact",
                "application_lock::tests::application_lock_policy_child_process",
                "--nocapture",
            ])
            .env("RO_APPLICATION_LOCK_TEST_CHILD_ACTION", action)
            .env("RO_APPLICATION_LOCK_TEST_CHILD_ROOT", application_data)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("spawn policy child");
        let stdout = child.stdout.take().expect("child stdout");
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        loop {
            line.clear();
            let read = reader.read_line(&mut line).expect("read child marker");
            assert!(read > 0, "policy child exited before readiness marker");
            if line.contains("RO-POLICY-CHILD-READY") {
                break;
            }
        }
        child.stdout = Some(reader.into_inner());
        child
    }

    #[cfg(windows)]
    #[test]
    fn application_lock_policy_child_process() {
        let Ok(action) = std::env::var("RO_APPLICATION_LOCK_TEST_CHILD_ACTION") else {
            return;
        };
        let application_data = PathBuf::from(
            std::env::var_os("RO_APPLICATION_LOCK_TEST_CHILD_ROOT")
                .expect("child application data root"),
        );
        match action.as_str() {
            "hold-instance" => {
                let manager = ApplicationLockManager::acquire(&application_data)
                    .expect("child owns desktop instance");
                let prepared = manager
                    .prepare_policy_transition_with(SignInMode::WindowsPassword, None, 15, |_| {
                        VerificationOutcome::Succeeded
                    })
                    .expect("child prepares protected mode");
                let committed = manager.commit_policy_transition(
                    prepared.handle.as_deref().expect("child transition handle"),
                    true,
                );
                assert_eq!(committed.outcome, PolicyTransitionOutcome::Committed);
                println!("RO-POLICY-CHILD-READY");
                std::io::stdout().flush().expect("flush child marker");
                thread::sleep(Duration::from_secs(60));
            }
            "publish-password" => {
                let store = PolicyStore::new(&application_data);
                let loaded = store.initialize();
                let target = SignInPolicy::normalized_target(
                    loaded.policy.revision() + 1,
                    SignInMode::WindowsPassword,
                    None,
                    0,
                )
                .expect("child target policy");
                let _guard = store.lock().expect("child policy lock");
                let staged = store.stage(&target).expect("child stage policy");
                store
                    .publish(staged, &loaded.source)
                    .expect("child publish policy");
                println!("RO-POLICY-CHILD-READY");
                std::io::stdout().flush().expect("flush child marker");
            }
            "hold-policy-mutex" => {
                let store = PolicyStore::new(&application_data);
                store.initialize();
                let _guard = store.lock().expect("child policy lock");
                println!("RO-POLICY-CHILD-READY");
                std::io::stdout().flush().expect("flush child marker");
                thread::sleep(Duration::from_secs(60));
            }
            _ => panic!("unknown child action"),
        }
    }

    #[cfg(windows)]
    #[test]
    fn release_runtime_is_single_instance_for_one_canonical_application_root() {
        let application_data = root("single-instance-process");
        let mut child = spawn_policy_child(&application_data, "hold-instance");
        assert!(matches!(
            ApplicationLockManager::acquire(&application_data),
            Err("RO-DESKTOP-ALREADY-RUNNING")
        ));
        assert_eq!(
            PolicyStore::new(&application_data).initialize().policy.mode,
            SignInMode::WindowsPassword
        );
        child.kill().expect("terminate first desktop process");
        child.wait().expect("wait for first desktop process");

        let restarted = ApplicationLockManager::acquire(&application_data)
            .expect("instance authority released after abrupt process exit");
        assert_eq!(restarted.status().sign_in_mode, SignInMode::WindowsPassword);
        assert_eq!(restarted.status().state, ApplicationLockState::Locked);
        assert_eq!(
            restarted.begin_protected_action(),
            Err("RO-APPLICATION-LOCKED")
        );
    }

    #[cfg(windows)]
    #[test]
    fn child_process_publication_and_abandoned_mutex_preserve_exact_policy() {
        let application_data = root("child-process-publication");
        let parent_store = PolicyStore::new(&application_data);
        let predecessor = parent_store.initialize();
        let stale_target = SignInPolicy::normalized_target(
            predecessor.policy.revision() + 1,
            SignInMode::WindowsHello,
            None,
            0,
        )
        .expect("stale parent target");

        let mut publisher = spawn_policy_child(&application_data, "publish-password");
        assert!(publisher.wait().expect("wait for publisher").success());
        let _guard = parent_store.lock().expect("parent policy lock");
        let staged = parent_store
            .stage(&stale_target)
            .expect("stage stale target");
        assert_eq!(
            parent_store.publish(staged, &predecessor.source),
            Err("RO-SIGN-IN-POLICY-CONFLICT")
        );
        drop(_guard);
        let committed = parent_store.initialize();
        assert_eq!(committed.state, PolicyLoadState::Valid);
        assert_eq!(committed.policy.mode, SignInMode::WindowsPassword);

        let mut lock_holder = spawn_policy_child(&application_data, "hold-policy-mutex");
        let killer = thread::spawn(move || {
            thread::sleep(Duration::from_millis(100));
            lock_holder.kill().expect("terminate policy lock holder");
            lock_holder.wait().expect("wait for policy lock holder");
        });
        let recovered_guard = parent_store
            .lock()
            .expect("abandoned named mutex remains recoverable");
        drop(recovered_guard);
        killer.join().expect("join lock-holder terminator");

        let reopened = parent_store.initialize();
        assert_eq!(reopened.state, PolicyLoadState::Valid);
        assert_eq!(reopened.policy, committed.policy);
        assert_eq!(
            fs::read(parent_store.canonical_path()).expect("canonical policy bytes"),
            committed.policy.canonical_bytes().expect("canonical bytes")
        );
    }

    #[test]
    fn explicit_none_is_the_default_and_never_enters_application_lock() {
        let manager = default_manager();
        let before = manager.status();
        assert_eq!(before.sign_in_mode, SignInMode::None);
        assert_eq!(before.configuration_state, LockConfigurationState::Valid);
        assert_eq!(before.state, ApplicationLockState::Unlocked);
        let (after, changed) = manager.lock(ApplicationLockReason::Manual);
        assert!(!changed);
        assert_eq!(after.state, ApplicationLockState::Unlocked);
        assert!(manager.lock_if_idle().is_none());
        assert!(manager.policy_store.canonical_path().is_file());
    }

    #[test]
    fn policy_contract_rejects_unknown_timeout_and_sensitive_name_controls() {
        assert!(
            SignInPolicy::normalized_target(
                1,
                SignInMode::WindowsPassword,
                Some("Local researcher".to_owned()),
                15,
            )
            .is_ok()
        );
        assert_eq!(
            SignInPolicy::normalized_target(1, SignInMode::WindowsPassword, None, 7),
            Err("RO-SIGN-IN-POLICY-INVALID")
        );
        assert_eq!(
            SignInPolicy::normalized_target(
                1,
                SignInMode::WindowsPassword,
                Some("name\npath".to_owned()),
                5,
            ),
            Err("RO-SIGN-IN-POLICY-INVALID")
        );
    }

    #[test]
    fn manual_lock_invalidates_actions_and_hides_profile_name() {
        let manager = manager();
        {
            let mut inner = manager.shared.lock().expect("lock mutex");
            inner.policy.profile_name = Some("Sensitive profile".to_owned());
        }
        let ticket = manager.begin_protected_action().expect("unlocked ticket");
        let (snapshot, changed) = manager.lock(ApplicationLockReason::Manual);
        assert!(changed);
        assert_eq!(snapshot.state, ApplicationLockState::Locked);
        assert_eq!(snapshot.profile_name, None);
        assert_eq!(
            manager.finish_protected_action(ticket),
            Err("RO-APPLICATION-LOCKED")
        );
        assert_eq!(
            manager.begin_protected_action(),
            Err("RO-APPLICATION-LOCKED")
        );
    }

    #[test]
    fn denied_cancelled_and_failed_core_paths_remain_locked() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let cancelled = manager
            .complete_test_reauthentication(VerificationOutcome::Cancelled, true)
            .expect("cancelled attempt");
        assert_eq!(cancelled.outcome, VerificationOutcome::Cancelled);
        assert_eq!(cancelled.reason_code, "RO-LOCK-AUTH-CANCELLED");
        let denied = manager
            .complete_test_reauthentication(VerificationOutcome::Denied, true)
            .expect("denied attempt");
        assert_eq!(denied.outcome, VerificationOutcome::Denied);
        assert_eq!(denied.reason_code, "RO-LOCK-AUTH-DENIED");
        assert!(manager.status().retry_after_seconds > 0);
        manager.shared.lock().expect("lock mutex").retry_at = None;
        let core_failed = manager
            .complete_test_reauthentication(VerificationOutcome::Succeeded, false)
            .expect("core failure attempt");
        assert_eq!(core_failed.outcome, VerificationOutcome::Failed);
        assert_eq!(core_failed.reason_code, "RO-LOCK-CORE-UNAVAILABLE");
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn provider_outcome_matrix_only_starts_core_and_unlocks_on_success() {
        for outcome in [
            VerificationOutcome::Cancelled,
            VerificationOutcome::Denied,
            VerificationOutcome::Unavailable,
            VerificationOutcome::Busy,
            VerificationOutcome::Failed,
            VerificationOutcome::Succeeded,
        ] {
            let manager = manager();
            manager.lock(ApplicationLockReason::Manual);
            let starts = AtomicUsize::new(0);
            let attempt = manager
                .reauthenticate_with(
                    &|| outcome,
                    || {
                        starts.fetch_add(1, Ordering::SeqCst);
                        RuntimeState::Ready
                    },
                    || {},
                )
                .expect("provider attempt");
            let succeeded = outcome == VerificationOutcome::Succeeded;
            assert_eq!(starts.load(Ordering::SeqCst), usize::from(succeeded));
            assert_eq!(
                attempt.snapshot.state,
                if succeeded {
                    ApplicationLockState::Unlocked
                } else {
                    ApplicationLockState::Locked
                }
            );
            assert_eq!(attempt.outcome, outcome);
        }
    }

    #[test]
    fn idle_deadline_locks_in_native_state_even_without_renderer_activity() {
        let manager = manager();
        {
            let mut inner = manager.shared.lock().expect("lock mutex");
            inner.policy.inactivity_timeout_minutes = 5;
            inner.last_activity = Instant::now() - Duration::from_secs(301);
        }
        let snapshot = manager.lock_if_idle().expect("idle lock");
        assert_eq!(snapshot.state, ApplicationLockState::Locked);
        assert_eq!(snapshot.reason, Some(ApplicationLockReason::Inactivity));
    }

    #[test]
    fn verified_same_user_unlocks_without_restoring_sensitive_identity_to_audit() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let attempt = manager
            .complete_test_reauthentication(VerificationOutcome::Succeeded, true)
            .expect("successful attempt");
        assert_eq!(attempt.outcome, VerificationOutcome::Succeeded);
        assert_eq!(attempt.snapshot.state, ApplicationLockState::Unlocked);
        let serialized = serde_json::to_string(&manager.audit()).expect("audit json");
        assert!(!serialized.contains("profileName"));
        assert!(!serialized.contains("username"));
        assert!(!serialized.contains("project"));
    }

    #[test]
    fn concurrent_reauthentication_admits_one_prompt_and_preserves_backoff() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let prompt_count = Arc::new(AtomicUsize::new(0));
        let (started_tx, started_rx) = mpsc::sync_channel(1);
        let (release_tx, release_rx) = mpsc::sync_channel(1);
        let worker_manager = manager.clone();
        let worker_count = Arc::clone(&prompt_count);
        let release_rx = Arc::new(Mutex::new(release_rx));
        let worker = std::thread::spawn(move || {
            let provider = || {
                worker_count.fetch_add(1, Ordering::SeqCst);
                started_tx.send(()).expect("signal prompt");
                release_rx
                    .lock()
                    .expect("release mutex")
                    .recv()
                    .expect("release prompt");
                VerificationOutcome::Denied
            };
            worker_manager.reauthenticate_with(&provider, || RuntimeState::Ready, || {})
        });
        started_rx.recv().expect("prompt admitted");
        let second_count = Arc::clone(&prompt_count);
        let busy = manager
            .reauthenticate_with(
                &|| {
                    second_count.fetch_add(1, Ordering::SeqCst);
                    VerificationOutcome::Succeeded
                },
                || RuntimeState::Ready,
                || {},
            )
            .expect("busy attempt");
        assert_eq!(busy.outcome, VerificationOutcome::Busy);
        assert_eq!(busy.reason_code, "RO-LOCK-RATE-LIMITED");
        release_tx.send(()).expect("release first prompt");
        let denied = worker
            .join()
            .expect("worker result")
            .expect("denied attempt");
        assert_eq!(denied.outcome, VerificationOutcome::Denied);
        assert_eq!(prompt_count.load(Ordering::SeqCst), 1);
        assert!(manager.status().retry_after_seconds > 0);
    }

    #[test]
    fn cancellation_and_core_failure_release_the_reauthentication_reservation() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let cancelled = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Cancelled,
                || RuntimeState::Ready,
                || {},
            )
            .expect("cancelled attempt");
        assert_eq!(cancelled.outcome, VerificationOutcome::Cancelled);
        let failed = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Succeeded,
                || RuntimeState::RecoveryRequired,
                || {},
            )
            .expect("core failure attempt");
        assert_eq!(failed.outcome, VerificationOutcome::Failed);
        assert_eq!(failed.reason_code, "RO-LOCK-CORE-UNAVAILABLE");
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn unlocked_and_stale_attempts_cannot_invoke_or_publish_provider_success() {
        let unlocked = manager();
        let provider_calls = AtomicUsize::new(0);
        let core_starts = AtomicUsize::new(0);
        let attempt = unlocked.reauthenticate_with(
            &|| {
                provider_calls.fetch_add(1, Ordering::SeqCst);
                VerificationOutcome::Succeeded
            },
            || {
                core_starts.fetch_add(1, Ordering::SeqCst);
                RuntimeState::Ready
            },
            || {},
        );
        assert_eq!(attempt, Err("RO-LOCK-AUTH-NOT-LOCKED"));
        assert_eq!(provider_calls.load(Ordering::SeqCst), 0);
        assert_eq!(core_starts.load(Ordering::SeqCst), 0);

        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let racing_manager = manager.clone();
        let stops = AtomicUsize::new(0);
        let stale = manager
            .reauthenticate_with(
                &|| VerificationOutcome::Succeeded,
                || {
                    racing_manager.lock(ApplicationLockReason::Manual);
                    RuntimeState::Ready
                },
                || {
                    stops.fetch_add(1, Ordering::SeqCst);
                },
            )
            .expect("stale attempt");
        assert_eq!(stale.outcome, VerificationOutcome::Failed);
        assert_eq!(stale.reason_code, "RO-LOCK-AUTH-STALE");
        assert_eq!(stale.snapshot.state, ApplicationLockState::Locked);
        assert_eq!(stops.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn provider_panic_releases_reservation_and_preserves_locked_state() {
        let manager = manager();
        manager.lock(ApplicationLockReason::Manual);
        let result = std::panic::catch_unwind({
            let manager = manager.clone();
            move || {
                manager.reauthenticate_with(
                    &|| panic!("provider panic"),
                    || RuntimeState::Ready,
                    || {},
                )
            }
        });
        assert!(result.is_err());
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);
    }

    #[test]
    fn concurrent_lock_invalidates_a_prepared_transition_without_publication() {
        let manager = manager();
        let prepared = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let handle = prepared.handle.expect("opaque handle");
        manager.lock(ApplicationLockReason::Manual);
        let result = manager.commit_policy_transition(&handle, true);
        assert_eq!(result.outcome, PolicyTransitionOutcome::Conflict);
        assert_eq!(manager.status().sign_in_mode, SignInMode::WindowsPassword);
        assert_eq!(
            manager.policy_store.initialize().policy.mode,
            SignInMode::WindowsPassword
        );
    }

    #[test]
    fn transitions_verify_the_exact_provider_sequence_before_preparation() {
        let cases = [
            (
                SignInMode::None,
                SignInMode::WindowsPassword,
                vec![SignInMode::WindowsPassword],
            ),
            (
                SignInMode::WindowsPassword,
                SignInMode::WindowsHello,
                vec![SignInMode::WindowsPassword, SignInMode::WindowsHello],
            ),
            (
                SignInMode::WindowsHello,
                SignInMode::WindowsPassword,
                vec![SignInMode::WindowsHello, SignInMode::WindowsPassword],
            ),
            (
                SignInMode::WindowsPassword,
                SignInMode::None,
                vec![SignInMode::WindowsPassword],
            ),
        ];
        for (source, target, expected) in cases {
            let manager = if source == SignInMode::None {
                default_manager()
            } else {
                manager_at(&root("provider-order"), source, 0)
            };
            let mut actual = Vec::new();
            let prepared = manager
                .prepare_policy_transition_with(target, None, 0, |mode| {
                    actual.push(mode);
                    VerificationOutcome::Succeeded
                })
                .expect("prepare transition");
            assert_eq!(prepared.outcome, PolicyTransitionOutcome::Prepared);
            assert_eq!(actual, expected);
            assert_eq!(
                prepared.warning_required,
                target == SignInMode::None && source.is_protected()
            );
            let cancelled = manager.commit_policy_transition(
                prepared.handle.as_deref().expect("opaque handle"),
                false,
            );
            assert_eq!(cancelled.outcome, PolicyTransitionOutcome::Cancelled);
        }
    }

    #[test]
    fn every_verification_failure_is_typed_and_preserves_policy_bytes() {
        for (verification, expected) in [
            (
                VerificationOutcome::Cancelled,
                PolicyTransitionOutcome::Cancelled,
            ),
            (VerificationOutcome::Denied, PolicyTransitionOutcome::Denied),
            (
                VerificationOutcome::Unavailable,
                PolicyTransitionOutcome::Unavailable,
            ),
            (VerificationOutcome::Busy, PolicyTransitionOutcome::Busy),
            (VerificationOutcome::Failed, PolicyTransitionOutcome::Failed),
        ] {
            let manager = manager();
            let before = fs::read(manager.policy_store.canonical_path()).expect("policy bytes");
            let result = manager
                .prepare_policy_transition_with(SignInMode::WindowsHello, None, 0, |_| verification)
                .expect("typed transition result");
            assert_eq!(result.outcome, expected);
            assert!(result.handle.is_none());
            assert_eq!(
                fs::read(manager.policy_store.canonical_path()).expect("policy bytes"),
                before
            );
            assert!(
                !manager
                    .shared
                    .lock()
                    .expect("lock mutex")
                    .reauthentication_in_progress
            );
        }
    }

    #[test]
    fn confirmed_commit_is_atomic_and_same_handle_returns_the_committed_receipt() {
        let manager = manager();
        let prepared = manager
            .prepare_policy_transition_with(SignInMode::WindowsHello, None, 15, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let handle = prepared.handle.expect("opaque handle");
        assert_eq!(handle.len(), 64);
        assert!(
            !serde_json::to_string(&manager.audit())
                .expect("audit json")
                .contains(&handle)
        );
        let committed = manager.commit_policy_transition(&handle, true);
        assert_eq!(committed.outcome, PolicyTransitionOutcome::Committed);
        assert_eq!(committed.snapshot.sign_in_mode, SignInMode::WindowsHello);
        assert_eq!(committed.snapshot.inactivity_timeout_minutes, 15);
        assert_eq!(manager.commit_policy_transition(&handle, true), committed);
        let reopened = ApplicationLockManager::new(
            manager
                .policy_store
                .canonical_path()
                .parent()
                .and_then(Path::parent)
                .expect("application data"),
        );
        assert_eq!(reopened.status().sign_in_mode, SignInMode::WindowsHello);
        assert_eq!(reopened.status().state, ApplicationLockState::Locked);
        assert_eq!(
            reopened.status().reason,
            Some(ApplicationLockReason::ApplicationRestart)
        );
    }

    #[test]
    fn missing_confirmation_and_stale_writer_never_change_the_prior_policy() {
        let manager = manager();
        let before = fs::read(manager.policy_store.canonical_path()).expect("policy bytes");
        let prepared = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let handle = prepared.handle.expect("opaque handle");
        let cancelled = manager.commit_policy_transition(&handle, false);
        assert_eq!(cancelled.outcome, PolicyTransitionOutcome::Cancelled);
        assert_eq!(
            fs::read(manager.policy_store.canonical_path()).expect("policy bytes"),
            before
        );
        assert_eq!(
            manager.commit_policy_transition(&handle, true).outcome,
            PolicyTransitionOutcome::Denied
        );

        let shared_root = root("stale-writer");
        let first = manager_at(&shared_root, SignInMode::WindowsPassword, 0);
        let second = ApplicationLockManager::new(&shared_root);
        let first_prepared = first
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("first preparation");
        let second_prepared = second
            .prepare_policy_transition_with(SignInMode::WindowsHello, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("second preparation");
        assert_eq!(
            second
                .commit_policy_transition(
                    second_prepared.handle.as_deref().expect("second handle"),
                    true,
                )
                .outcome,
            PolicyTransitionOutcome::Committed
        );
        assert_eq!(
            first
                .commit_policy_transition(
                    first_prepared.handle.as_deref().expect("first handle"),
                    true,
                )
                .outcome,
            PolicyTransitionOutcome::Conflict
        );
        assert_eq!(
            ApplicationLockManager::new(&shared_root)
                .status()
                .sign_in_mode,
            SignInMode::WindowsHello
        );
    }

    #[test]
    fn corrupt_policy_requires_explicit_same_sid_password_recovery() {
        let root = root("corrupt-recovery");
        let store = PolicyStore::new(&root);
        fs::create_dir_all(store.canonical_path().parent().expect("security dir"))
            .expect("create security dir");
        fs::write(store.canonical_path(), b"{\"schemaVersion\":\"future\"}\n")
            .expect("corrupt policy");
        let before = fs::read(store.canonical_path()).expect("corrupt bytes");
        let manager = ApplicationLockManager::new(&root);
        assert_eq!(
            manager.status().configuration_state,
            LockConfigurationState::Invalid
        );
        assert_eq!(manager.status().state, ApplicationLockState::Locked);

        let calls = AtomicUsize::new(0);
        let ordinary = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                calls.fetch_add(1, Ordering::SeqCst);
                VerificationOutcome::Succeeded
            })
            .expect("ordinary reset denied");
        assert_eq!(ordinary.outcome, PolicyTransitionOutcome::Denied);
        assert_eq!(calls.load(Ordering::SeqCst), 0);

        let cancelled = manager
            .prepare_password_recovery_reset_with(|| VerificationOutcome::Cancelled)
            .expect("cancelled recovery");
        assert_eq!(cancelled.outcome, PolicyTransitionOutcome::Cancelled);
        assert_eq!(
            fs::read(store.canonical_path()).expect("corrupt bytes"),
            before
        );

        let prepared = manager
            .prepare_password_recovery_reset_with(|| VerificationOutcome::Succeeded)
            .expect("verified recovery");
        assert!(prepared.warning_required);
        let committed = manager
            .commit_policy_transition(prepared.handle.as_deref().expect("recovery handle"), true);
        assert_eq!(committed.outcome, PolicyTransitionOutcome::Committed);
        assert_eq!(committed.reason_code, "RO-SIGN-IN-RECOVERY-COMMITTED");
        assert_eq!(committed.snapshot.sign_in_mode, SignInMode::None);
        assert_eq!(committed.snapshot.state, ApplicationLockState::Unlocked);
        assert_eq!(
            ApplicationLockManager::new(&root).status().sign_in_mode,
            SignInMode::None
        );
    }

    #[test]
    #[ignore = "invoked by the renderer contract integration harness"]
    fn renderer_contract_witness() {
        let output = PathBuf::from(
            std::env::var("RO_LOCK_CONTRACT_FIXTURE")
                .expect("RO_LOCK_CONTRACT_FIXTURE is required for this ignored witness"),
        );

        let enable_root = root("renderer-enable");
        let enable_manager = ApplicationLockManager::new(&enable_root);
        let enable_prepared = enable_manager
            .prepare_policy_transition_with(
                SignInMode::WindowsPassword,
                Some("Native fixture".to_owned()),
                5,
                |_| VerificationOutcome::Succeeded,
            )
            .expect("prepare password enable");
        let enable_committed = enable_manager.commit_policy_transition(
            enable_prepared.handle.as_deref().expect("enable handle"),
            true,
        );
        let enable_status = enable_manager.status();

        let cancel_root = root("renderer-cancel");
        let cancel_manager = manager_at(&cancel_root, SignInMode::WindowsPassword, 0);
        let cancel_prepared = cancel_manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare protected reduction");
        assert_eq!(
            cancel_prepared.outcome,
            PolicyTransitionOutcome::Prepared,
            "renderer cancellation fixture must prepare"
        );
        let cancel_receipt = cancel_manager.commit_policy_transition(
            cancel_prepared.handle.as_deref().expect("cancel handle"),
            false,
        );

        let unavailable_root = root("renderer-unavailable");
        let unavailable_manager = manager_at(&unavailable_root, SignInMode::WindowsHello, 0);
        let unavailable = unavailable_manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Unavailable
            })
            .expect("unavailable Hello result");

        let recovery_root = root("renderer-recovery");
        let recovery_store = PolicyStore::new(&recovery_root);
        fs::create_dir_all(
            recovery_store
                .canonical_path()
                .parent()
                .expect("security directory"),
        )
        .expect("create recovery security directory");
        fs::write(
            recovery_store.canonical_path(),
            b"{\"schemaVersion\":\"future\"}\n",
        )
        .expect("write invalid policy fixture");
        let recovery_manager = ApplicationLockManager::new(&recovery_root);
        let ordinary_denied = recovery_manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("ordinary invalid-policy transition");
        let recovery_prepared = recovery_manager
            .prepare_password_recovery_reset_with(|| VerificationOutcome::Succeeded)
            .expect("prepare explicit recovery");
        let recovery_committed = recovery_manager.commit_policy_transition(
            recovery_prepared
                .handle
                .as_deref()
                .expect("recovery handle"),
            true,
        );

        let witness = serde_json::json!({
            "schemaVersion": "1.0",
            "documentType": "application-lock-renderer-contract-witness",
            "enablePassword": {
                "prepared": enable_prepared,
                "committed": enable_committed,
                "statusAfterCommit": enable_status
            },
            "protectedCancellation": {
                "prepared": cancel_prepared,
                "cancelled": cancel_receipt,
                "statusAfterCancel": cancel_manager.status()
            },
            "helloUnavailable": unavailable,
            "invalidPolicyRecovery": {
                "ordinaryDenied": ordinary_denied,
                "prepared": recovery_prepared,
                "committed": recovery_committed
            }
        });
        fs::write(
            &output,
            serde_json::to_vec_pretty(&witness).expect("serialize renderer witness"),
        )
        .expect("write renderer witness");

        for path in [enable_root, cancel_root, unavailable_root, recovery_root] {
            let _ = fs::remove_dir_all(path);
        }
    }

    #[test]
    fn unavailable_configured_provider_never_downgrades_without_explicit_recovery() {
        let root = root("unavailable-recovery");
        let manager = manager_at(&root, SignInMode::WindowsHello, 0);
        let before = fs::read(manager.policy_store.canonical_path()).expect("policy bytes");
        let unavailable = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |mode| {
                assert_eq!(mode, SignInMode::WindowsHello);
                VerificationOutcome::Unavailable
            })
            .expect("unavailable configured provider");
        assert_eq!(unavailable.outcome, PolicyTransitionOutcome::Unavailable);
        assert!(unavailable.handle.is_none());
        assert_eq!(
            fs::read(manager.policy_store.canonical_path()).expect("policy bytes"),
            before
        );

        let recovered = manager
            .prepare_password_recovery_reset_with(|| VerificationOutcome::Succeeded)
            .expect("explicit password recovery");
        assert_eq!(recovered.outcome, PolicyTransitionOutcome::Prepared);
        let committed = manager
            .commit_policy_transition(recovered.handle.as_deref().expect("recovery handle"), true);
        assert_eq!(committed.reason_code, "RO-SIGN-IN-RECOVERY-COMMITTED");
        assert_eq!(committed.snapshot.sign_in_mode, SignInMode::None);
    }

    #[test]
    fn a_pending_transition_uses_the_same_native_verification_admission() {
        let manager = manager();
        let prepared = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let second = manager
            .prepare_policy_transition_with(SignInMode::WindowsHello, None, 0, |_| {
                panic!("a second provider must not be invoked")
            })
            .expect("busy result");
        assert_eq!(second.outcome, PolicyTransitionOutcome::Busy);
        manager.commit_policy_transition(prepared.handle.as_deref().expect("first handle"), false);
    }

    #[test]
    fn expired_and_panicking_preparations_release_admission_without_mutation() {
        let manager = manager();
        let before = fs::read(manager.policy_store.canonical_path()).expect("policy bytes");
        let panic_result = std::panic::catch_unwind({
            let manager = manager.clone();
            move || {
                manager.prepare_policy_transition_with(SignInMode::WindowsHello, None, 0, |_| {
                    panic!("provider panic")
                })
            }
        });
        assert!(panic_result.is_err());
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );

        let prepared = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let handle = prepared.handle.expect("opaque handle");
        manager
            .shared
            .lock()
            .expect("lock mutex")
            .pending_transition
            .as_mut()
            .expect("pending transition")
            .expires_at = Instant::now() - Duration::from_secs(1);
        let expired = manager.commit_policy_transition(&handle, true);
        assert_eq!(expired.outcome, PolicyTransitionOutcome::Expired);
        assert_eq!(
            fs::read(manager.policy_store.canonical_path()).expect("policy bytes"),
            before
        );
        assert!(
            !manager
                .shared
                .lock()
                .expect("lock mutex")
                .reauthentication_in_progress
        );
    }

    #[cfg(windows)]
    #[test]
    fn publication_failure_is_typed_and_preserves_the_committed_bytes() {
        use std::fs::OpenOptions;
        use std::os::windows::fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::FILE_SHARE_READ;

        let manager = manager();
        let before = fs::read(manager.policy_store.canonical_path()).expect("policy bytes");
        let prepared = manager
            .prepare_policy_transition_with(SignInMode::None, None, 0, |_| {
                VerificationOutcome::Succeeded
            })
            .expect("prepare transition");
        let handle = prepared.handle.expect("opaque handle");
        let _deny_delete = OpenOptions::new()
            .read(true)
            .share_mode(FILE_SHARE_READ)
            .open(manager.policy_store.canonical_path())
            .expect("exclusive policy reader");
        let failed = manager.commit_policy_transition(&handle, true);
        assert_eq!(failed.outcome, PolicyTransitionOutcome::Failed);
        assert_eq!(failed.reason_code, "RO-SIGN-IN-TRANSITION-WRITE-FAILED");
        assert_eq!(
            fs::read(manager.policy_store.canonical_path()).expect("policy bytes"),
            before
        );
        assert_eq!(manager.status().sign_in_mode, SignInMode::WindowsPassword);
    }
}
