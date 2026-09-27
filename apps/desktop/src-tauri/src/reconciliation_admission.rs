//! Narrow renderer admission; Core retains all project, rights and decision authority.

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

fn exact(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key))
    })
}

fn identity(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(crate::supervisor::canonical_uuid_v7)
}

fn nullable_identity(value: &Value) -> bool {
    value.is_null() || identity(value)
}

fn number(value: &Value, minimum: u64, maximum: u64) -> bool {
    value
        .as_u64()
        .is_some_and(|value| (minimum..=maximum).contains(&value))
}

fn digest(value: &Value) -> bool {
    value.as_str().is_some_and(|text| {
        text.len() == 64
            && text
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

fn group(value: &Value) -> bool {
    value.as_str().is_some_and(|text| {
        !text.is_empty()
            && text.len() <= 32
            && text.as_bytes()[0].is_ascii_lowercase()
            && text
                .bytes()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    })
}

fn identities(value: &Value, maximum: usize, sorted: bool) -> bool {
    value.as_array().is_some_and(|values| {
        values.len() <= maximum
            && values.iter().all(identity)
            && values
                .iter()
                .filter_map(Value::as_str)
                .collect::<BTreeSet<_>>()
                .len()
                == values.len()
            && (!sorted
                || values
                    .windows(2)
                    .all(|pair| pair[0].as_str() < pair[1].as_str()))
    })
}

fn source(value: &Value) -> bool {
    exact(
        value,
        &["kind", "contextId", "revisionId", "ordinal", "recordKey"],
    ) && identity(&value["contextId"])
        && identity(&value["revisionId"])
        && match value["kind"].as_str() {
            Some("import-member") => {
                number(&value["ordinal"], 1, 200000) && digest(&value["recordKey"])
            }
            Some("connector-record") => {
                number(&value["ordinal"], 0, 999) && value["recordKey"].is_null()
            }
            _ => false,
        }
}

fn work(value: &Value) -> bool {
    exact(
        value,
        &[
            "schemaVersion",
            "workId",
            "revisionId",
            "previousRevisionId",
            "disposition",
            "aliasTarget",
            "assertionRevisionIds",
            "decisionRevisionId",
        ],
    ) && value["schemaVersion"] == "1.0"
        && identity(&value["workId"])
        && identity(&value["revisionId"])
        && value["workId"] != value["revisionId"]
        && value["previousRevisionId"] != value["revisionId"]
        && nullable_identity(&value["previousRevisionId"])
        && nullable_identity(&value["decisionRevisionId"])
        && value["disposition"] == "active"
        && value["aliasTarget"].is_null()
        && identities(&value["assertionRevisionIds"], 256, true)
        && value["assertionRevisionIds"]
            .as_array()
            .is_some_and(|items| !items.is_empty())
}

fn plan(value: &Value) -> bool {
    if !exact(
        value,
        &[
            "schemaVersion",
            "action",
            "works",
            "unassignedAssertionRevisionIds",
            "partitions",
            "aliases",
            "conflictDisposition",
            "evidenceSha256",
            "rationale",
        ],
    ) || value["schemaVersion"] != "1.0"
        || value["conflictDisposition"] != "retain-all"
        || !digest(&value["evidenceSha256"])
        || !value["rationale"]
            .as_str()
            .is_some_and(|text| (1..=2048).contains(&text.chars().count()))
        || !identities(&value["unassignedAssertionRevisionIds"], 256, true)
    {
        return false;
    }
    let (Some(works), Some(partitions), Some(aliases)) = (
        value["works"].as_array(),
        value["partitions"].as_array(),
        value["aliases"].as_array(),
    ) else {
        return false;
    };
    if works.len() > 32
        || !works.iter().all(work)
        || !(1..=32).contains(&partitions.len())
        || aliases.len() > 256
    {
        return false;
    }
    let work_ids: BTreeMap<_, _> = works
        .iter()
        .map(|work| {
            (
                work["workId"].as_str().unwrap(),
                work["revisionId"].as_str().unwrap(),
            )
        })
        .collect();
    if work_ids.len() != works.len() {
        return false;
    }
    let mut members = BTreeSet::new();
    for member in works
        .iter()
        .flat_map(|work| work["assertionRevisionIds"].as_array().unwrap())
        .chain(value["unassignedAssertionRevisionIds"].as_array().unwrap())
    {
        if !members.insert(member.as_str().unwrap()) {
            return false;
        }
    }
    if members.is_empty() || members.len() > 512 {
        return false;
    }
    let mut outputs = BTreeSet::new();
    let mut survivors = BTreeSet::new();
    let mut groups = BTreeMap::new();
    for part in partitions {
        if !exact(part, &["group", "existingWorkId", "assertionRevisionIds"])
            || !group(&part["group"])
            || !nullable_identity(&part["existingWorkId"])
            || !identities(&part["assertionRevisionIds"], 256, true)
            || part["assertionRevisionIds"].as_array().unwrap().is_empty()
        {
            return false;
        }
        if groups
            .insert(
                part["group"].as_str().unwrap(),
                part["existingWorkId"].as_str(),
            )
            .is_some()
        {
            return false;
        }
        if let Some(id) = part["existingWorkId"].as_str()
            && (!work_ids.contains_key(id) || !survivors.insert(id))
        {
            return false;
        }
        for member in part["assertionRevisionIds"].as_array().unwrap() {
            if !outputs.insert(member.as_str().unwrap()) {
                return false;
            }
        }
    }
    if members != outputs {
        return false;
    }
    let mut alias_ids = BTreeSet::new();
    for alias in aliases {
        if !exact(alias, &["workId", "revisionId", "targetGroup"])
            || !identity(&alias["workId"])
            || !identity(&alias["revisionId"])
            || !group(&alias["targetGroup"])
        {
            return false;
        }
        let id = alias["workId"].as_str().unwrap();
        let Some(target) = groups.get(alias["targetGroup"].as_str().unwrap()) else {
            return false;
        };
        if *target == Some(id)
            || survivors.contains(id)
            || !alias_ids.insert(id)
            || work_ids
                .get(id)
                .is_some_and(|revision| Some(*revision) != alias["revisionId"].as_str())
        {
            return false;
        }
    }
    if work_ids
        .keys()
        .any(|id| !survivors.contains(id) && !alias_ids.contains(id))
    {
        return false;
    }
    let unassigned = value["unassignedAssertionRevisionIds"].as_array().unwrap();
    match value["action"].as_str() {
        Some("merge") => works.len() + unassigned.len() >= 2 && partitions.len() == 1,
        Some("split") => works.len() == 1 && unassigned.is_empty() && partitions.len() >= 2,
        Some("assign") => works.len() <= 1 && !unassigned.is_empty() && partitions.len() == 1,
        _ => false,
    }
}

pub(crate) fn validate_public_request(path: &str, body: &str, root: fn(&str) -> bool) -> bool {
    let Some(route) = path.strip_prefix("/projects/reconciliation/") else {
        return false;
    };
    let keys: &[&str] = match route {
        "batches/prepare" => &["root"],
        "batches/schedule" => &["root", "requestId"],
        "batches/status" | "batches/cancel" => &["root", "requestId", "jobId"],
        "candidates" => &["root", "setRevisionId", "after", "limit"],
        "exact" => &["root", "commandId", "source"],
        "inspect" => &["root", "assertionRevisionId"],
        "connector-address" => &["root", "previewId", "ordinal"],
        "review/context" => &["root", "workIds", "unassignedAssertionRevisionIds"],
        "review/preview" => &["root", "plan"],
        "review/commit" => &["root", "command"],
        _ => return false,
    };
    if body.len()
        > if route.starts_with("review/") {
            262144
        } else {
            32768
        }
    {
        return false;
    }
    let Ok(value) = serde_json::from_str::<Value>(body) else {
        return false;
    };
    if !exact(&value, keys) || !value["root"].as_str().is_some_and(root) {
        return false;
    }
    match route {
        "batches/prepare" => true,
        "batches/schedule" => identity(&value["requestId"]),
        "batches/status" | "batches/cancel" => {
            identity(&value["requestId"]) && identity(&value["jobId"])
        }
        "candidates" => {
            identity(&value["setRevisionId"])
                && number(&value["after"], 0, 20000)
                && number(&value["limit"], 1, 100)
        }
        "exact" => identity(&value["commandId"]) && source(&value["source"]),
        "inspect" => identity(&value["assertionRevisionId"]),
        "connector-address" => identity(&value["previewId"]) && number(&value["ordinal"], 0, 999),
        "review/context" => {
            identities(&value["workIds"], 32, false)
                && identities(&value["unassignedAssertionRevisionIds"], 256, false)
        }
        "review/preview" => plan(&value["plan"]),
        "review/commit" => {
            let command = &value["command"];
            exact(command, &["commandId", "plan", "expectedPreviewSha256"])
                && identity(&command["commandId"])
                && digest(&command["expectedPreviewSha256"])
                && plan(&command["plan"])
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    const ID: &str = "01900000-0000-7000-8000-000000000001";
    const REV: &str = "01900000-0000-7000-8000-000000000002";
    const MEMBER: &str = "01900000-0000-7000-8000-000000000003";
    const OTHER: &str = "01900000-0000-7000-8000-000000000004";

    fn plan() -> Value {
        json!({"schemaVersion":"1.0","action":"split","works":[{
            "schemaVersion":"1.0","workId":ID,"revisionId":REV,"previousRevisionId":null,
            "disposition":"active","aliasTarget":null,"assertionRevisionIds":[MEMBER,OTHER],"decisionRevisionId":null
        }],"unassignedAssertionRevisionIds":[],"partitions":[
            {"group":"retained","existingWorkId":ID,"assertionRevisionIds":[MEMBER]},
            {"group":"separate","existingWorkId":null,"assertionRevisionIds":[OTHER]}
        ],"aliases":[],"conflictDisposition":"retain-all","evidenceSha256":"a".repeat(64),"rationale":"Synthetic split."})
    }

    fn request(route: &str, body: Value) -> crate::supervisor::CoreApiRequest {
        crate::supervisor::CoreApiRequest {
            method: "POST".into(),
            path: format!("/projects/reconciliation/{route}"),
            body: Some(body.to_string()),
            if_match: None,
            idempotency_key: None,
        }
    }

    #[test]
    fn reconciliation_admission_accepts_bounded_routes_and_denies_extra_authority() {
        let source = json!({"kind":"import-member","contextId":ID,"revisionId":REV,"ordinal":1,"recordKey":"a".repeat(64)});
        let routes = [
            ("batches/prepare", json!({})),
            ("batches/schedule", json!({"requestId":ID})),
            ("batches/status", json!({"requestId":ID,"jobId":REV})),
            ("batches/cancel", json!({"requestId":ID,"jobId":REV})),
            (
                "candidates",
                json!({"setRevisionId":REV,"after":0,"limit":25}),
            ),
            ("exact", json!({"commandId":ID,"source":source})),
            ("inspect", json!({"assertionRevisionId":REV})),
            ("connector-address", json!({"previewId":ID,"ordinal":0})),
            (
                "review/context",
                json!({"workIds":[ID],"unassignedAssertionRevisionIds":[]}),
            ),
            ("review/preview", json!({"plan":plan()})),
            (
                "review/commit",
                json!({"command":{"commandId":ID,"plan":plan(),"expectedPreviewSha256":"b".repeat(64)}}),
            ),
        ];
        for (route, mut body) in routes {
            body["root"] = json!("C:/Research/synthetic");
            let good = request(route, body.clone());
            assert!(
                crate::supervisor::validate_api_request(&good).is_ok(),
                "{route}"
            );
            body["actorId"] = json!(ID);
            assert!(crate::supervisor::validate_api_request(&request(route, body)).is_err());
            assert!(
                crate::supervisor::validate_api_request(&crate::supervisor::CoreApiRequest {
                    if_match: Some("unexpected".into()),
                    ..good
                })
                .is_err()
            );
        }
    }

    #[test]
    fn reconciliation_admission_denies_incomplete_partition_and_overbounds() {
        let mut incomplete = plan();
        incomplete["partitions"].as_array_mut().unwrap().pop();
        let mut injected = plan();
        injected["works"][0]["rights"] = json!("permitted");
        for plan in [incomplete, injected] {
            assert!(
                crate::supervisor::validate_api_request(&request(
                    "review/preview",
                    json!({"root":"C:/Research/synthetic","plan":plan})
                ))
                .is_err()
            );
        }
        for limit in [json!(101), json!(true), json!(-1)] {
            assert!(crate::supervisor::validate_api_request(&request("candidates", json!({"root":"C:/Research/synthetic","setRevisionId":ID,"after":0,"limit":limit}))).is_err());
        }
        assert!(
            crate::supervisor::validate_api_request(&request(
                "raw-database",
                json!({"root":"C:/Research/synthetic"})
            ))
            .is_err()
        );
    }
}
