//! Fixed synthetic slice qualification. This module is test-only and never a
//! renderer command or an extra RuntimeSupervisor public operation.
use super::*;
use base64::Engine;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
use std::sync::mpsc;

const MAX_FRAME_BYTES: usize = 1_048_576;

fn read_frame(reader: &mut impl BufRead) -> std::io::Result<Option<String>> {
    let mut frame = Vec::with_capacity(4096);
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return if frame.is_empty() {
                Ok(None)
            } else {
                Err(std::io::Error::new(
                    std::io::ErrorKind::UnexpectedEof,
                    "incomplete child frame",
                ))
            };
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let take = newline.map_or(available.len(), |position| position + 1);
        if frame.len() + take > MAX_FRAME_BYTES {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "child frame exceeds bound",
            ));
        }
        frame.extend_from_slice(&available[..take]);
        reader.consume(take);
        if newline.is_some() {
            return String::from_utf8(frame).map(Some).map_err(|_| {
                std::io::Error::new(std::io::ErrorKind::InvalidData, "child frame encoding")
            });
        }
    }
}

struct ChildWatchdog {
    stop: Option<mpsc::Sender<()>>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl Drop for ChildWatchdog {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

const RAW: &[u8] =
    b"title,doi,year\nSynthetic observatory lookup,10.99999/native-lexical-fixture,2024\n";

fn decoded(response: CoreApiResponse) -> Result<Value, &'static str> {
    if response.status != 200 {
        return Err("synthetic Core fixture operation did not succeed");
    }
    serde_json::from_str(&response.body).map_err(|_| "synthetic Core fixture response invalid")
}

struct Fixture {
    supervisor: RuntimeSupervisor,
    child: Option<Arc<Mutex<std::process::Child>>>,
    root: Option<String>,
    project_id: Option<String>,
    preview_id: Option<String>,
    source: Option<Value>,
    work: Option<Value>,
    item: Option<Value>,
    sequence: u32,
    normal_child_exit: bool,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        // A failure remains a failed test; this is emergency ownership cleanup,
        // never evidence of normal child drain.
        if let Some(child) = self.child.as_ref() {
            let mut child = child
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            if !self.normal_child_exit {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
        self.supervisor.stop();
    }
}

impl Fixture {
    fn stop_with_lifetime_receipt(&self, fixture: &Path, stage: &str) -> RuntimeSnapshot {
        assert!(matches!(stage, "restart" | "final"));
        let observation = super::native_stop_proof::Observation::bind_ready(&self.supervisor);
        // An observer binding failure NEVER replaces the original stop/cleanup.
        let stopped = self.supervisor.stop();
        let mut receipt = match observation {
            Ok(observation) => observation.finish(),
            Err(code) => json!({"kind":"native-inner-core-stop-observer-bind-failure",
                "observerBindCode":code,"coreNormalContainedDrain":false}),
        };
        let identity = receipt["record"]["identity"].clone();
        let role_receipt = (|| -> Result<Value, &'static str> {
            let pid = identity["process_id"].as_u64().ok_or("missing-core-pid")?;
            let birth = identity["creation_filetime"]
                .as_str()
                .ok_or("missing-core-birth")?;
            if pid == 0
                || pid > u64::from(u32::MAX)
                || birth.len() != 16
                || !birth.bytes().all(|c| c.is_ascii_hexdigit())
            {
                return Err("invalid-core-identity");
            }
            let path = fixture
                .join("core-owned-role-proof")
                .join(format!("core-owned-roles-{pid}-{birth}.json"));
            let metadata =
                std::fs::symlink_metadata(&path).map_err(|_| "missing-owned-role-receipt")?;
            use std::os::windows::fs::MetadataExt;
            if !metadata.is_file()
                || metadata.file_attributes() & 0x400 != 0
                || metadata.len() > 131_072
            {
                return Err("invalid-owned-role-receipt-file");
            }
            let bytes = std::fs::read(path).map_err(|_| "owned-role-receipt-unreadable")?;
            if bytes.len() > 131_072 {
                return Err("owned-role-receipt-exceeds-bound");
            }
            serde_json::from_slice(&bytes).map_err(|_| "owned-role-receipt-invalid-json")
        })();
        let mut roles_valid = false;
        match role_receipt {
            Ok(roles) => {
                let required_roles = ["guardian", "connector-worker", "lpac-worker", "acl-utility"];
                let counts_valid = roles["roles"].as_object().is_some_and(|all| {
                    all.len() == required_roles.len()
                        && required_roles.iter().all(|role| {
                            all.get(*role)
                                .and_then(Value::as_object)
                                .is_some_and(|counts| {
                                    counts.len() == 4
                                        && ["attempts", "returns", "errors", "inflight"].iter().all(
                                            |key| {
                                                counts.get(*key).and_then(Value::as_u64) == Some(0)
                                            },
                                        )
                                })
                        })
                });
                roles_valid = roles["kind"] == "test-only-core-owned-role-zero-observation"
                    && roles["coreIdentity"] == identity
                    && roles["installedBeforeRuntimeComposition"] == true
                    && roles["runtimeReturned"] == true
                    && roles["finalizedBeforeCoreExit"] == true
                    && roles["coverage"]["aliasesMatchedAtInstall"] == true
                    && roles["coverage"]["observerError"] == false
                    && roles["aliasesRetainedUntilFinalization"] == true
                    && roles["sourcePinsEqualAfter"] == true
                    && roles["unexpectedLiveThreads"]
                        .as_array()
                        .is_some_and(Vec::is_empty)
                    && roles["observedZeroRoleAttempts"] == true
                    && roles["positiveWorkerGuardianDrain"] == "NOT_OBSERVED"
                    && counts_valid;
                receipt["ownedRoleReceipt"] = roles;
            }
            Err(code) => receipt["ownedRoleReceiptError"] = json!(code),
        }
        let attempt_matches =
            receipt["record"]["attempt"].as_u64() == Some(u64::from(stopped.attempt));
        let complete = stopped.state == RuntimeState::Stopped
            && receipt["schemaVersion"] == "2.0"
            && receipt["coreNormalContainedDrain"] == true
            && attempt_matches
            && roles_valid;
        receipt["actualStopSnapshot"] = json!(&stopped);
        receipt["attemptMatches"] = json!(attempt_matches);
        receipt["ownedZeroRolesIndependentlyChecked"] = json!(roles_valid);
        receipt["boundedJourneyNormalLifetime"] = json!(complete);
        receipt["stage"] = json!(stage);
        std::fs::File::create_new(fixture.join(format!("native-stop-{stage}.json")))
            .unwrap()
            .write_all(&serde_json::to_vec_pretty(&receipt).unwrap())
            .unwrap();
        assert!(
            complete,
            "actual lifecycle proof denied; preserve native-stop-{stage}.json"
        );
        stopped
    }
}

impl Fixture {
    fn command_id(&mut self) -> String {
        self.sequence += 1;
        format!("01900000-0000-7000-8000-{:012}", self.sequence)
    }

    fn connection(&self) -> Result<NativeImportConnection, &'static str> {
        self.supervisor.native_import_connection(
            self.root.as_deref().ok_or("owned project not created")?,
            self.project_id
                .as_deref()
                .ok_or("owned project not created")?,
        )
    }

    fn seed_import(&mut self) -> Result<Value, &'static str> {
        if self.preview_id.is_some() {
            return Err("synthetic source can only be created once");
        }
        let connection = self.connection()?;
        let mut address = json!({"root":connection.root,"projectId":connection.project_id});
        let context = decoded(connection.request(NativeImportAction::Context, address.clone())?)?;
        if context["projectId"] != address["projectId"] {
            return Err("synthetic context project mismatch");
        }
        address["sessionId"] = context["sessionId"].clone();
        let mut create = address.clone();
        create.as_object_mut().unwrap().extend(json!({
            "sourceName":"synthetic-native.csv","formatName":"csv","encoding":"utf-8","delimiter":",",
            "rights":{
                "store":{"value":"permitted","basis":"researcher-confirmed"},
                "inspect":{"value":"permitted","basis":"researcher-confirmed"},
                "derive":{"value":"permitted","basis":"researcher-confirmed"},
                "index":{"value":"permitted","basis":"researcher-confirmed"},
                "model-use":{"value":"unknown","basis":"not-reported"},
                "quote":{"value":"unknown","basis":"not-reported"},
                "export":{"value":"unknown","basis":"not-reported"},
                "share":{"value":"unknown","basis":"not-reported"}
            }
        }).as_object().unwrap().clone());
        let created = decoded(connection.request(NativeImportAction::Create, create)?)?;
        let preview = created["previewId"]
            .as_str()
            .ok_or("preview identity missing")?
            .to_owned();
        self.preview_id = Some(preview.clone());
        address["previewId"] = json!(preview);
        let mut chunk = address.clone();
        chunk["ordinal"] = json!(1);
        chunk["data"] = json!(base64::engine::general_purpose::STANDARD.encode(RAW));
        decoded(connection.request(NativeImportAction::Chunk, chunk)?)?;
        let mut seal = address.clone();
        seal["sourceSha256"] = json!(format!("{:x}", Sha256::digest(RAW)));
        seal["byteLength"] = json!(RAW.len());
        seal["chunkCount"] = json!(1);
        decoded(connection.request(NativeImportAction::Seal, seal)?)?;
        decoded(connection.request(NativeImportAction::Schedule, address)?)?;
        // Ephemeral session and capability never cross the child IPC boundary.
        Ok(
            json!({"previewId":preview,"sourceSha256":format!("{:x}",Sha256::digest(RAW)),"byteLength":RAW.len()}),
        )
    }

    fn fixture_core(&self, path: &'static str, body: Value) -> Result<Value, &'static str> {
        // Called only with hard-coded paths and internally constructed bodies.
        let connection = self.connection()?;
        if body["root"].as_str() != Some(connection.root.as_str()) || !connection.is_current() {
            return Err("synthetic fixture no longer current");
        }
        let bytes = serde_json::to_vec(&body).map_err(|_| "synthetic fixture encoding failed")?;
        if bytes.len() > 32768 {
            return Err("synthetic fixture body exceeds bound");
        }
        let response = authenticated_api_request_bytes_owned(
            connection.port,
            &connection.token,
            &CoreApiRequest {
                method: "POST".into(),
                path: path.into(),
                body: None,
                if_match: None,
                idempotency_key: None,
            },
            Some(&bytes),
            Some(connection.cancellation.as_ref()),
            Duration::from_secs(2),
            Some(&|| connection.is_current()),
        )?;
        if !connection.is_current() {
            return Err("synthetic fixture no longer current");
        }
        decoded(response)
    }

    fn publish_rights(&mut self, denied: bool) -> Result<Value, &'static str> {
        let root = self.root.clone().ok_or("owned project missing")?;
        let source = self
            .source
            .clone()
            .ok_or("actual committed source missing")?;
        let work = self.work.clone().ok_or("actual reconciliation missing")?;
        let subject = json!({"projectId":self.project_id,"sourceAssertionRevisionId":work["assertionRevisionId"],
            "address":source,"copyId":work["assertionRevisionId"],"copyLocation":"local-source","resourceClass":"metadata"});
        let current = self.fixture_core(
            "/projects/corpus/rights/current",
            json!({"root":root,"subject":subject}),
        )?;
        let permissions: Vec<Value> = [
            ("local-search","inspect"),("local-search","index"),
            ("corpus-membership","store"),("corpus-membership","inspect"),
            ("corpus-membership","derive"),("corpus-membership","index"),
        ].iter().map(|(purpose,action)|json!({
            "use":{"action":action,"purpose":purpose,"destinationKind":"local-project","provider":null,"region":null,"shareGroup":null},
            "value":if denied && *purpose=="local-search" && *action=="index" {"denied"} else {"permitted"},
            "basis":"researcher-confirmed","confidence":"confirmed","evidenceRevisionIds":[work["assertionRevisionId"]],
            "licenseObservationRevisionId":null,"entitlementRevisionId":null,"expiresAt":null,
            "granteeActorId":null,"confirmationRequired":false
        })).collect();
        let command = self.command_id();
        let policy = self.fixture_core(
            "/projects/corpus/rights/publish",
            json!({
                "root":root,"commandId":command,"subject":subject,"permissions":permissions,
                "expectedPredecessorRevisionId":current.get("revisionId"),"confirmed":true
            }),
        )?;
        // Observe/advance the actual bounded recheck lifecycle; no synthetic
        // 'ready' state and no automatic until-pass retry.
        let mut scope = self.fixture_core(
            "/projects/corpus/rights/recheck-scope",
            json!({"root":root,"subject":subject}),
        )?;
        for _ in 0..8 {
            if scope["subject"] != subject || scope["rightsRevisionId"] != policy["revisionId"] {
                return Err("actual rights recheck identity mismatch");
            }
            if scope["disposition"] == "complete" {
                break;
            }
            if scope["disposition"] != "pending" {
                return Err("actual rights recheck shape invalid");
            }
            scope = self.fixture_core(
                "/projects/corpus/rights/advance-rechecks",
                json!({"root":root,"subject":subject,"batchSize":1000}),
            )?;
        }
        if scope["subject"] != subject
            || scope["rightsRevisionId"] != policy["revisionId"]
            || scope["disposition"] != "complete"
            || scope["exactState"] != "complete"
            || scope["genericState"] != "complete"
            || !scope["pendingReason"].is_null()
        {
            return Err("actual rights rechecks did not complete within the fixed bound");
        }
        Ok(json!({"policy":policy,"recheck":scope}))
    }

    fn create_corpus(&mut self) -> Result<Value, &'static str> {
        if self.item.is_some() {
            return Err("synthetic corpus item already created");
        }
        let work = self.work.clone().ok_or("actual reconciliation missing")?;
        let command = self.command_id();
        let item = self.fixture_core(
            "/projects/corpus/create",
            json!({
                "root":self.root,"commandId":command,"source":self.source,
                "workId":work["workId"],"workRevisionId":work["workRevisionId"]
            }),
        )?;
        self.item = Some(item.clone());
        let rights = self.publish_rights(false)?;
        Ok(json!({"item":item,"rights":rights}))
    }

    fn observe(
        &mut self,
        request: &CoreApiRequest,
        response: &CoreApiResponse,
        fixture: &Path,
    ) -> Result<(), &'static str> {
        if response.status != 200 {
            return Ok(());
        }
        let body: Value =
            serde_json::from_str(&response.body).map_err(|_| "actual response JSON invalid")?;
        if request.path == "/projects" {
            if self.root.is_some() {
                return Err("one owned synthetic project only");
            }
            let root = body["root"].as_str().ok_or("actual project root missing")?;
            let resolved =
                dunce::canonicalize(root).map_err(|_| "actual project path unavailable")?;
            if resolved != fixture.join("projects").join("search") {
                return Err("project is outside owned fixture");
            }
            self.root = Some(root.into());
            self.project_id = Some(
                body["projectId"]
                    .as_str()
                    .ok_or("actual project identity missing")?
                    .into(),
            );
        }
        if request.path == "/projects/imports/manifest/members" {
            let command: Value =
                serde_json::from_str(request.body.as_deref().ok_or("manifest request missing")?)
                    .map_err(|_| "manifest request invalid")?;
            if command["previewId"].as_str() != self.preview_id.as_deref() {
                return Err("manifest outside fixed source");
            }
            let member = body["records"]
                .as_array()
                .and_then(|records| {
                    records.iter().find(|row| {
                        row["included"] == true && !row["sourceRecordRevisionId"].is_null()
                    })
                })
                .ok_or("included committed source missing")?;
            self.source = Some(
                json!({"kind":"import-member","contextId":self.preview_id,"revisionId":command["revisionId"],"ordinal":member["ordinal"],"recordKey":member["recordKey"]}),
            );
        }
        if request.path == "/projects/reconciliation/exact" {
            let command: Value = serde_json::from_str(
                request
                    .body
                    .as_deref()
                    .ok_or("reconciliation request missing")?,
            )
            .map_err(|_| "reconciliation request invalid")?;
            if Some(&command["source"]) != self.source.as_ref() {
                return Err("reconciliation outside fixed source");
            }
            if body["workId"].is_null()
                || body["workRevisionId"].is_null()
                || body["assertionRevisionId"].is_null()
            {
                return Err("actual reconciliation identity missing");
            }
            self.work = Some(body);
        }
        Ok(())
    }
}

#[test]
#[ignore = "explicit real Windows populated Native qualification; requires owned ignored fixture"]
fn populated_generated_client_search_uses_current_native_authority() {
    let repository = dunce::canonicalize(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(3)
            .unwrap(),
    )
    .unwrap();
    let scratch = dunce::canonicalize(repository.join("artifacts/tmp")).unwrap();
    let fixture = dunce::canonicalize(
        std::env::var_os("RO_SEARCH_POPULATED_FIXTURE").expect("explicit fixture required"),
    )
    .unwrap();
    assert_eq!(fixture.parent(), Some(scratch.as_path()));
    assert!(
        fixture
            .file_name()
            .unwrap()
            .to_string_lossy()
            .starts_with("search-populated-native-")
    );
    let python = PathBuf::from(
        std::env::var_os("RO_SEARCH_POPULATED_PYTHON").expect("explicit Python required"),
    );
    let node = PathBuf::from(
        std::env::var_os("RO_SEARCH_POPULATED_NODE").expect("explicit Node required"),
    );
    let python_path = std::env::join_paths([
        repository.join("tests/service/fixtures"),
        repository.join("services/core-api/src"),
        repository.join(".venv/Lib/site-packages"),
    ])
    .unwrap();
    std::fs::create_dir(fixture.join("core-owned-role-proof")).unwrap();
    let config = SupervisorConfig::for_integration_harness(
        python,
        repository.clone(),
        vec![
            "-B".into(),
            "-m".into(),
            "native_integration_sidecar".into(),
            "--profile-vault-root".into(),
            fixture.join("vault").into_os_string(),
        ],
        vec![
            ("PYTHONPATH".into(), python_path),
            ("PYTHONDONTWRITEBYTECODE".into(), "1".into()),
            ("RO_W3_CORE_LIFETIME_PROBE".into(), "1".into()),
            ("TEMP".into(), fixture.join("temp").into_os_string()),
            ("TMP".into(), fixture.join("temp").into_os_string()),
        ],
    )
    .unwrap();
    let supervisor = RuntimeSupervisor::with_fixture_session(config, &fixture.join("session"));
    let mut owned = Fixture {
        supervisor,
        child: None,
        root: None,
        project_id: None,
        preview_id: None,
        source: None,
        work: None,
        item: None,
        sequence: 1000,
        normal_child_exit: false,
    };
    assert_eq!(
        owned.supervisor.start().state,
        RuntimeState::Ready,
        "actual supervisor must become ready"
    );
    let stderr = std::fs::File::create_new(fixture.join("node-stderr.log")).unwrap();
    let mut child = Command::new(node)
        .arg(repository.join("apps/desktop/scripts/search-populated-native-client.mjs"))
        .arg(&fixture)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(stderr))
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    let output = child.stdout.take().unwrap();
    let child = Arc::new(Mutex::new(child));
    owned.child = Some(Arc::clone(&child));
    let watchdog_fired = Arc::new(AtomicBool::new(false));
    let observed_watchdog = Arc::clone(&watchdog_fired);
    let (stop, watchdog) = mpsc::channel();
    let mut watchdog = ChildWatchdog {
        stop: Some(stop),
        thread: Some(std::thread::spawn(move || {
            if matches!(
                watchdog.recv_timeout(Duration::from_secs(180)),
                Err(mpsc::RecvTimeoutError::Timeout)
            ) {
                observed_watchdog.store(true, Ordering::Release);
                let mut child = child
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                let _ = child.kill();
                let _ = child.wait();
            }
        })),
    };
    let (send, receive) = mpsc::sync_channel(1);
    let reader = std::thread::spawn(move || {
        let mut output = BufReader::new(output);
        loop {
            match read_frame(&mut output) {
                Ok(Some(line)) => {
                    if send.send(Ok(line)).is_err() {
                        break;
                    }
                }
                Ok(None) => break,
                Err(error) => {
                    let _ = send.send(Err(error));
                    break;
                }
            }
        }
    });
    let deadline = Instant::now() + Duration::from_secs(180);
    loop {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .expect("fixed Native qualification deadline exceeded");
        let line = receive
            .recv_timeout(remaining)
            .expect("bounded child IPC deadline")
            .expect("child IPC read");
        assert!(
            Instant::now() < deadline && !watchdog_fired.load(Ordering::Acquire),
            "absolute child deadline exceeded"
        );
        let value: Value = serde_json::from_str(&line).expect("closed child IPC JSON");
        if value["kind"] == "finished" {
            assert_eq!(
                value["status"], "PASS",
                "child assertions failed; preserve ignored report"
            );
            break;
        }
        let reply = if let Some(control) = value.get("control").and_then(Value::as_str) {
            assert_eq!(
                value.as_object().unwrap().len(),
                1,
                "fixed controls accept no caller arguments"
            );
            let result = match control {
                "seed-import" => owned.seed_import(),
                "create-corpus" => owned.create_corpus(),
                "rights-deny" => owned.publish_rights(true),
                "rights-restore" => owned.publish_rights(false),
                "restart" => {
                    assert_eq!(
                        owned.stop_with_lifetime_receipt(&fixture, "restart").state,
                        RuntimeState::Stopped
                    );
                    assert_eq!(owned.supervisor.start().state, RuntimeState::Ready);
                    Ok(json!({"restarted":true}))
                }
                _ => Err("unknown fixed synthetic fixture control"),
            };
            match result {
                Ok(value) => json!({"kind":"fixture","value":value}),
                Err(code) => json!({"kind":"error","code":code}),
            }
        } else {
            let request: CoreApiRequest =
                serde_json::from_value(value).expect("closed CoreApiRequest");
            if request.path == "/projects" {
                let body: Value =
                    serde_json::from_str(request.body.as_deref().expect("create body")).unwrap();
                assert_eq!(
                    body["parentDirectory"].as_str(),
                    fixture.join("projects").to_str(),
                    "fixed owned creation parent before mutation"
                );
                assert_eq!(body["directoryName"], "search");
                assert!(owned.root.is_none(), "one fixed project only");
            }
            match owned.supervisor.api_request(&request) {
                Ok(response) => {
                    owned
                        .observe(&request, &response, &fixture)
                        .expect("actual fixture identity binding");
                    json!({"kind":"response","response":response})
                }
                Err(code) => json!({"kind":"error","code":code}),
            }
        };
        let mut wire = serde_json::to_vec(&reply).unwrap();
        wire.push(b'\n');
        assert!(wire.len() <= MAX_FRAME_BYTES, "bounded parent frame");
        input.write_all(&wire).unwrap();
        input.flush().unwrap();
        assert!(
            Instant::now() < deadline && !watchdog_fired.load(Ordering::Acquire),
            "absolute child deadline exceeded"
        );
    }
    drop(input);
    let deadline = deadline.min(Instant::now() + Duration::from_secs(10));
    loop {
        if let Some(status) = owned
            .child
            .as_ref()
            .unwrap()
            .lock()
            .unwrap()
            .try_wait()
            .unwrap()
        {
            assert!(
                status.success(),
                "actual Node client must exit successfully"
            );
            owned.normal_child_exit = true;
            break;
        }
        assert!(
            Instant::now() < deadline,
            "Node normal drain deadline exceeded"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
    drop(receive);
    reader.join().unwrap();
    assert!(
        !watchdog_fired.load(Ordering::Acquire),
        "owned watchdog timeout is failure"
    );
    if let Some(stop) = watchdog.stop.take() {
        let _ = stop.send(());
    }
    if let Some(thread) = watchdog.thread.take() {
        thread.join().unwrap();
    }
    assert!(
        !watchdog_fired.load(Ordering::Acquire),
        "final joined watchdog timeout is failure"
    );
    assert_eq!(
        owned.stop_with_lifetime_receipt(&fixture, "final").state,
        RuntimeState::Stopped,
        "actual supervisor normal drain"
    );
    std::fs::File::create_new(fixture.join("native-proof.json")).unwrap().write_all(&serde_json::to_vec_pretty(&json!({
        "normalChildExit":true,"childReaped":true,"supervisorStopped":true,
        "sourceSha256":format!("{:x}",Sha256::digest(RAW)),"fixtureSetup":"test-private actual Core operations",
        "publicSearchBoundary":"unchanged RuntimeSupervisor.api_request",
        "lifetimeReceiptPaths":["native-stop-restart.json","native-stop-final.json"],
        "lifetimeProof":"actual original stop observations and independently checked zero-role receipts"
    })).unwrap()).unwrap();
}
