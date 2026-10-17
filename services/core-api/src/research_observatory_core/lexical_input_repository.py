"""Lexical input heads retain every raw source and observation history row."""

from .search.run_schema import VALID_OBSERVATION

_CLASSIFIED_OBSERVATION = (
    "EXISTS(SELECT 1 FROM search_observation_events e WHERE e.outbox_id=c.outbox_id "
    "AND e.project_id=c.project_id AND e.revision_id=c.revision_id AND e.record_sha256=c.record_sha256 AND ("
    + VALID_OBSERVATION
    + "))"
)


def lexical_watermark(db, project_id: str) -> int:
    return int(
        db.execute(
            "SELECT coalesce(max(c.sequence),0) FROM search_changes c WHERE c.project_id=? AND NOT ("
            + _CLASSIFIED_OBSERVATION
            + ")",
            (project_id,),
        ).fetchone()[0]
    )


def source_authority_epoch(db, project_id: str) -> int:
    """Actual transactional clock for current import/object authority writes.

    Existing historical data starts at zero and is completely captured before
    a new read proof. Every later material write advances this append-only log.
    Verification timestamps alone do not change source authority.
    """
    return int(
        db.execute(
            "SELECT coalesce(max(sequence),0) FROM search_source_epochs WHERE project_id=?", (project_id,)
        ).fetchone()[0]
    )


def rights_time_partition(db, project_id: str, now: str) -> int:
    """Invalidate across any recorded permission activation/expiry, without writes.

    Including historical policies is conservative: it can require a fresh read,
    never keep an old universe valid. No clock or epoch comes from the client.
    """
    return int(
        db.execute(
            "SELECT coalesce(sum((json_extract(p.value,'$.recordedAt')<=?) + "
            "coalesce(json_extract(p.value,'$.expiresAt')<=?,0)),0) "
            "FROM rights_policy_revisions r,json_each(r.policy_json,'$.permissions') p WHERE r.project_id=?",
            (now, now, project_id),
        ).fetchone()[0]
    )


def is_lexical_observation(db, project_id: str, sequence: int) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM search_changes c WHERE c.project_id=? AND c.sequence=? AND ("
            + _CLASSIFIED_OBSERVATION
            + ")",
            (project_id, sequence),
        ).fetchone()
        is not None
    )
