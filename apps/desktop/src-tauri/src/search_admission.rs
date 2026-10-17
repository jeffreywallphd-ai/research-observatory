//! Closed search transport admission. Core retains all live source authority.

use crate::supervisor::{canonical_project_id, canonical_uuid_v7};
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Validate {
    query: String,
}

#[derive(Default, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Filters {
    year_from: Option<u16>,
    year_to: Option<u16>,
}

impl Filters {
    fn valid(&self) -> bool {
        self.year_from.is_none_or(|year| (1..=9999).contains(&year))
            && self.year_to.is_none_or(|year| (1..=9999).contains(&year))
            && match (self.year_from, self.year_to) {
                (Some(start), Some(end)) => start <= end,
                _ => true,
            }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Run {
    root: String,
    project_id: String,
    command_id: String,
    query: String,
    #[serde(default)]
    filters: Filters,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Address {
    root: String,
    project_id: String,
    job_id: String,
}

fn default_limit() -> u8 {
    50
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Page {
    root: String,
    project_id: String,
    job_id: String,
    after: Option<String>,
    #[serde(default = "default_limit")]
    limit: u8,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Explain {
    root: String,
    project_id: String,
    job_id: String,
    item_id: String,
}

fn query(value: &str) -> bool {
    (1..=8192).contains(&value.chars().count()) && !value.contains('\0')
}

pub(crate) fn validate_public_request(path: &str, body: &str, root: fn(&str) -> bool) -> bool {
    if body.len() > 262_144 {
        return false;
    }
    match path {
        "/projects/search/validate" => {
            serde_json::from_str::<Validate>(body).is_ok_and(|command| query(&command.query))
        }
        "/projects/search/run" => serde_json::from_str::<Run>(body).is_ok_and(|command| {
            root(&command.root)
                && canonical_project_id(&command.project_id)
                && canonical_uuid_v7(&command.command_id)
                && query(&command.query)
                && command.filters.valid()
        }),
        "/projects/search/status" | "/projects/search/cancel" => {
            serde_json::from_str::<Address>(body).is_ok_and(|command| {
                root(&command.root)
                    && canonical_project_id(&command.project_id)
                    && canonical_uuid_v7(&command.job_id)
            })
        }
        "/projects/search/page" => serde_json::from_str::<Page>(body).is_ok_and(|command| {
            root(&command.root)
                && canonical_project_id(&command.project_id)
                && canonical_uuid_v7(&command.job_id)
                && (1..=50).contains(&command.limit)
                && command.after.as_deref().is_none_or(|cursor| {
                    (1..=4096).contains(&cursor.len())
                        && cursor
                            .bytes()
                            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
                })
        }),
        "/projects/search/explain" => serde_json::from_str::<Explain>(body).is_ok_and(|command| {
            root(&command.root)
                && canonical_project_id(&command.project_id)
                && canonical_uuid_v7(&command.job_id)
                && canonical_uuid_v7(&command.item_id)
        }),
        _ => false,
    }
}
