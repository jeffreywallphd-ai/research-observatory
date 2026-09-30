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

fn version_reference(value: &Value) -> bool {
    exact(value, &["versionId", "revisionId"])
        && identity(&value["versionId"])
        && identity(&value["revisionId"])
        && value["versionId"] != value["revisionId"]
}

fn version_date(value: &Value) -> bool {
    if !exact(value, &["precision", "value"]) {
        return false;
    }
    let precision = value["precision"].as_str().unwrap_or("");
    if matches!(precision, "unknown" | "not-reported") {
        return value["value"].is_null();
    }
    let Some(text) = value["value"].as_str() else {
        return false;
    };
    let widths: &[usize] = match precision {
        "year" => &[4],
        "month" => &[4, 2],
        "day" => &[4, 2, 2],
        _ => return false,
    };
    let parts: Vec<_> = text.split('-').collect();
    if parts.len() != widths.len()
        || parts
            .iter()
            .zip(widths)
            .any(|(part, width)| part.len() != *width || !part.bytes().all(|b| b.is_ascii_digit()))
    {
        return false;
    }
    let values: Vec<u32> = parts.iter().map(|part| part.parse().unwrap_or(0)).collect();
    let year = values[0];
    let month = *values.get(1).unwrap_or(&1);
    let day = *values.get(2).unwrap_or(&1);
    let days = match month {
        4 | 6 | 9 | 11 => 30,
        2 if year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400)) => {
            29
        }
        2 => 28,
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        _ => 0,
    };
    year > 0 && day > 0 && day <= days
}

fn version_definition(value: &Value) -> bool {
    exact(value, &["kind", "assertionRevisionIds", "date"])
        && matches!(
            value["kind"].as_str(),
            Some(
                "preprint"
                    | "accepted-manuscript"
                    | "version-of-record"
                    | "erratum"
                    | "correction"
                    | "expression-of-concern"
                    | "retraction"
                    | "not-reported"
            )
        )
        && version_date(&value["date"])
        && identities(&value["assertionRevisionIds"], 256, true)
        && value["assertionRevisionIds"]
            .as_array()
            .is_some_and(|items| !items.is_empty())
}

fn version_relation(value: &Value) -> bool {
    if !exact(
        value,
        &[
            "kind",
            "source",
            "target",
            "evidence",
            "date",
            "knowledgeStatus",
        ],
    ) || !matches!(
        value["kind"].as_str(),
        Some(
            "is-version-of"
                | "supersedes"
                | "erratum-for"
                | "corrects"
                | "expresses-concern"
                | "retracts"
        )
    ) || !matches!(
        value["knowledgeStatus"].as_str(),
        Some("adjudicated" | "disputed")
    ) || !version_reference(&value["source"])
        || !version_reference(&value["target"])
        || !version_date(&value["date"])
    {
        return false;
    }
    let ids: BTreeSet<_> = ["source", "target"]
        .iter()
        .flat_map(|side| {
            [
                value[side]["versionId"].as_str().unwrap(),
                value[side]["revisionId"].as_str().unwrap(),
            ]
        })
        .collect();
    let Some(evidence) = value["evidence"].as_array() else {
        return false;
    };
    if ids.len() != 4 || !(1..=32).contains(&evidence.len()) {
        return false;
    }
    let mut keys = BTreeSet::new();
    evidence.iter().all(|item| {
        exact(
            item,
            &["assertionRevisionId", "category", "selector", "valueSha256"],
        ) && identity(&item["assertionRevisionId"])
            && matches!(item["category"].as_str(), Some("field" | "identifier"))
            && item["selector"]
                .as_str()
                .is_some_and(|text| (1..=128).contains(&text.chars().count()))
            && digest(&item["valueSha256"])
            && keys.insert((
                item["assertionRevisionId"].as_str().unwrap(),
                item["category"].as_str().unwrap(),
                item["selector"].as_str().unwrap(),
            ))
    })
}

fn version_plan(value: &Value) -> bool {
    if !exact(
        value,
        &[
            "schemaVersion",
            "action",
            "workIds",
            "contextSha256",
            "rationale",
            "definition",
            "version",
            "relation",
            "previousPreferenceRevisionId",
        ],
    ) || value["schemaVersion"] != "1.0"
        || !digest(&value["contextSha256"])
        || !identities(&value["workIds"], 8, true)
        || value["workIds"]
            .as_array()
            .is_none_or(|items| items.is_empty())
        || !value["rationale"]
            .as_str()
            .is_some_and(|text| (1..=4000).contains(&text.chars().count()))
        || !nullable_identity(&value["previousPreferenceRevisionId"])
    {
        return false;
    }
    let definition = &value["definition"];
    let version = &value["version"];
    let relation = &value["relation"];
    if value["action"] != "prefer" && !value["previousPreferenceRevisionId"].is_null() {
        return false;
    }
    match value["action"].as_str() {
        Some("register") => {
            version_definition(definition) && version.is_null() && relation.is_null()
        }
        Some("revise") => {
            version_definition(definition) && version_reference(version) && relation.is_null()
        }
        Some("relate") => definition.is_null() && version.is_null() && version_relation(relation),
        Some("prefer") => {
            definition.is_null()
                && version_reference(version)
                && relation.is_null()
                && value["workIds"].as_array().unwrap().len() == 1
        }
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
        "versions/works" => &["root", "after", "limit"],
        "versions/context" => &["root", "workIds"],
        "versions/inspect" => &["root", "revisionId"],
        "versions/preview" => &["root", "plan"],
        "versions/commit" => &["root", "command"],
        _ => return false,
    };
    if body.len()
        > if route.starts_with("review/") || route.starts_with("versions/") {
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
        "versions/works" => nullable_identity(&value["after"]) && number(&value["limit"], 1, 32),
        "versions/context" => {
            identities(&value["workIds"], 8, false)
                && value["workIds"]
                    .as_array()
                    .is_some_and(|items| !items.is_empty())
        }
        "versions/inspect" => identity(&value["revisionId"]),
        "versions/preview" => version_plan(&value["plan"]),
        "versions/commit" => {
            let command = &value["command"];
            exact(command, &["commandId", "plan", "expectedPreviewSha256"])
                && identity(&command["commandId"])
                && digest(&command["expectedPreviewSha256"])
                && version_plan(&command["plan"])
        }
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
    fn version_admission_accepts_decisions_and_denies_forged_authority() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/scholarly-metadata/work-versions.v1.json"
        ))
        .unwrap();
        let command = fixture["command"].clone();
        for (route, mut body) in [
            ("versions/works", json!({"after":null,"limit":32})),
            ("versions/context", json!({"workIds":[ID]})),
            ("versions/inspect", json!({"revisionId":REV})),
            ("versions/preview", json!({"plan":command["plan"]})),
            ("versions/commit", json!({"command":command})),
        ] {
            body["root"] = json!("C:/Research/synthetic");
            assert!(
                crate::supervisor::validate_api_request(&request(route, body.clone())).is_ok(),
                "{route}"
            );
            body["actorId"] = json!(ID);
            assert!(crate::supervisor::validate_api_request(&request(route, body)).is_err());
        }
        let mut forged = fixture["command"]["plan"].clone();
        forged["relation"]["evidence"][0]["rights"] = json!("permitted");
        assert!(
            crate::supervisor::validate_api_request(&request(
                "versions/preview",
                json!({"root":"C:/Research/synthetic","plan":forged})
            ))
            .is_err()
        );
        let mut cycle = fixture["command"]["plan"].clone();
        cycle["relation"]["target"] = cycle["relation"]["source"].clone();
        assert!(
            crate::supervisor::validate_api_request(&request(
                "versions/preview",
                json!({"root":"C:/Research/synthetic","plan":cycle})
            ))
            .is_err()
        );
        for (day, admitted) in [("2000-02-29", true), ("1900-02-29", false)] {
            let mut dated = fixture["command"]["plan"].clone();
            dated["relation"]["date"] = json!({"precision":"day","value":day});
            assert_eq!(
                crate::supervisor::validate_api_request(&request(
                    "versions/preview",
                    json!({"root":"C:/Research/synthetic","plan":dated})
                ))
                .is_ok(),
                admitted,
                "{day}"
            );
        }
        for work_ids in [json!([]), Value::Null] {
            let mut empty = fixture["command"]["plan"].clone();
            empty["workIds"] = work_ids;
            assert!(
                crate::supervisor::validate_api_request(&request(
                    "versions/preview",
                    json!({"root":"C:/Research/synthetic","plan":empty})
                ))
                .is_err()
            );
        }
        let mut missing = fixture["command"]["plan"].clone();
        missing.as_object_mut().unwrap().remove("workIds");
        assert!(
            crate::supervisor::validate_api_request(&request(
                "versions/preview",
                json!({"root":"C:/Research/synthetic","plan":missing})
            ))
            .is_err()
        );
        for body in [
            json!({"after":null,"limit":33}),
            json!({"after":0,"limit":1}),
        ] {
            let mut body = body;
            body["root"] = json!("C:/Research/synthetic");
            assert!(
                crate::supervisor::validate_api_request(&request("versions/works", body)).is_err()
            );
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
