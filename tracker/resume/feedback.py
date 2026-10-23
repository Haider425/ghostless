"""People's feedback on their matches, as labels that can replace the
evaluation set's (docs/resume-model-plan.md, section 8).

The same three grades as the labelled set, so the same measures apply:

- applied (or further: interviewing, an offer, or turned down after applying) -> strong
- saved, not applied -> okay
- not interested -> weak

Only for people who have given training consent (and not withdrawn it), and
only their choices and ids: resume text is never read here. Reads only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg

FIT_FOR_STATUS = {
    "applied": "strong",
    "interviewing": "strong",
    "offer": "strong",
    "rejected": "strong",  # they applied: the posting was worth it to them
    "saved": "okay",
}


@dataclass
class FeedbackLabel:
    user_id: int
    resume_id: int | None  # the resume matched when they said "not interested"; else their primary one
    job_id: int
    fit: str  # strong | okay | weak
    signal: str  # applied, saved, not_interested ...
    at: datetime


def feedback_labels(conn: psycopg.Connection) -> list[FeedbackLabel]:
    """One label per person and posting. "Not interested" wins over a save
    (it's the more deliberate answer); an application wins over both."""
    rows = conn.execute(
        """WITH consenting AS (
               SELECT user_id FROM training_consent WHERE withdrawn_at IS NULL
           ), primary_resume AS (
               SELECT DISTINCT ON (user_id) user_id, id FROM resumes
               ORDER BY user_id, is_primary DESC, updated_at DESC
           )
           SELECT s.user_id, p.id, s.job_id, s.status, coalesce(s.applied_at, s.updated_at), 'saved'
           FROM saved_jobs s JOIN consenting c USING (user_id) LEFT JOIN primary_resume p USING (user_id)
           UNION ALL
           SELECT f.user_id, coalesce(f.resume_id, p.id), f.job_id, 'not_interested', f.created_at, 'feedback'
           FROM match_feedback f JOIN consenting c USING (user_id) LEFT JOIN primary_resume p USING (user_id)"""
    ).fetchall()
    rank = {"strong": 2, "weak": 1, "okay": 0}  # applied > not interested > saved
    best: dict[tuple[int, int], FeedbackLabel] = {}
    for user_id, resume_id, job_id, signal, at, _ in rows:
        fit = "weak" if signal == "not_interested" else FIT_FOR_STATUS.get(signal)
        if fit is None:
            continue
        label = FeedbackLabel(user_id, resume_id, job_id, fit, signal, at)
        key = (user_id, job_id)
        if key not in best or rank[fit] > rank[best[key].fit]:
            best[key] = label
    return sorted(best.values(), key=lambda lab: (lab.user_id, lab.job_id))
