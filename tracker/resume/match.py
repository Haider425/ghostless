"""Score how well a resume fits a posting, requirement by requirement.

The posting is read in full (tracker.resume.posting): its required and
preferred skills, years of experience, degree, whether you must be in school,
and its key terms. The resume is read in full too (tracker.resume.profile):
where each skill shows up, how much work experience there is, education, and
the phrases it uses. The score adds up six parts:

    35  required skills   each one you have; skills used in work or projects
                          count fully, skills only named in a list count less
    10  nice-to-haves     the preferred skills you have
    15  key terms         the posting's own phrases that your resume uses too
    20  experience        your career stage and years against what it asks for
    10  education         degree, field, and being in school when that's required
    10  role and title    how much of your resume is this kind of work

Every part comes with a plain explanation, and the requirements come back as
a checklist (met, partly met, missing) with what to change. Without a
description only the title, level and role can be compared, so the score is
capped and says so. It's an estimate to guide you, not an applicant tracking
system's verdict.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from tracker.resume.posting import DEGREE_RANK, Needs, analyze_posting, stem

LEVEL_FIT = {
    "student": {"intern": 1.0, "new_grad": 0.7, "mid": 0.3, "senior": 0.05},
    "new_grad": {"intern": 0.55, "new_grad": 1.0, "mid": 0.65, "senior": 0.1},
    "experienced": {"intern": 0.15, "new_grad": 0.6, "mid": 1.0, "senior": 0.6},
    "senior": {"intern": 0.05, "new_grad": 0.3, "mid": 0.85, "senior": 1.0},
}
ROLE_NAMES = {
    "sde": "software",
    "data_eng": "data engineering",
    "data": "data and analytics",
    "ml": "AI and machine learning",
    "hardware": "hardware and embedded",
    "security": "security",
    "other": "this kind of",
}
_GENERIC_TITLE_WORDS = set(
    """engineer engineering developer development software senior junior intern internship co-op coop new grad
    graduate staff lead principal manager summer fall winter spring and the for with team ii iii iv i
    level entry associate full time part term months month remote hybrid onsite canada usa toronto vancouver
    montreal waterloo ottawa calgary sr jr specialist analyst scientist""".split()
)


@dataclass
class Part:
    key: str
    label: str
    points: float
    max: int
    detail: str


@dataclass
class Requirement:
    text: str
    status: str  # met | partial | missing
    detail: str
    kind: str  # skill | preferred | experience | education | enrollment


@dataclass
class Match:
    score: int
    label: str
    skills_matched: list[str]
    skills_missing: list[str]
    components: dict[str, float]  # each part as 0 to 1, for compact displays
    suggestions: list[str]
    limited: bool = False  # no job description: score uses title and level only
    notes: list[str] = field(default_factory=list)
    breakdown: list[Part] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    terms_matched: list[str] = field(default_factory=list)
    terms_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def label_for(score: int) -> str:
    if score >= 80:
        return "Excellent fit"
    if score >= 65:
        return "Strong fit"
    if score >= 50:
        return "Good fit"
    if score >= 35:
        return "Partial fit"
    return "Long shot"


def title_words(title: str) -> list[str]:
    words = re.findall(r"[a-z][a-z+#./-]{2,}", title.lower())
    return [w for w in dict.fromkeys(words) if w not in _GENERIC_TITLE_WORDS and not w.isdigit()]


# how much a skill counts, by where the resume shows it
EVIDENCE = {"work": 1.0, "project": 0.9, "listed": 0.6}
EVIDENCE_WORDS = {
    "work": "shown in your work experience",
    "project": "shown in your projects",
    "listed": "only in your skills list",
}


def MONTHS_WORDS(m: int) -> str:  # noqa: N802
    if m < 1:
        return "no work experience yet"
    return f"about {m} months of experience" if m < 18 else f"about {round(m / 12)} years of experience"


def _needs(job: dict) -> Needs:
    """What the posting asks for; from its skills alone when there's no description."""
    description = job.get("description") or ""
    if description:
        needs = analyze_posting(job.get("title") or "", description)
        if not needs.empty:
            return needs
    skills = list(dict.fromkeys(job.get("skills") or []))
    return Needs(skills, [], None, None, [], False, False, [], False, empty=not skills)


def _has_term(term: str, words: set[str], phrases: set[str]) -> bool:
    parts = [stem(w) for w in term.split()]
    if len(parts) == 1:
        return parts[0] in words
    if not phrases:  # profiles saved before phrases were kept: every word will do
        return all(w in words for w in parts)
    return " ".join(parts) in phrases


def score_job(profile: dict, job: dict) -> Match:
    """`profile` as built by resume.profile (or its dict); `job` needs title,
    level, role_type and skills, and ideally description and signals."""
    resume_skills = set(profile.get("skills") or [])
    evidence: dict[str, str] = profile.get("skill_evidence") or {}
    resume_words = {stem(w) for w in profile.get("keywords") or []}
    resume_phrases = set(profile.get("phrases") or [])
    needs = _needs(job)
    level = profile.get("level") or "new_grad"
    months = int(profile.get("months_experience") or 0)
    education = profile.get("education") or {}
    requirements: list[Requirement] = []
    parts: list[Part] = []

    # --- required skills (35)
    req = needs.required_skills
    weights = []
    for skill in req:
        if skill in resume_skills:
            where = evidence.get(skill, "work")  # older profiles don't say where: give full credit
            weights.append(EVIDENCE[where])
            requirements.append(
                Requirement(
                    skill,
                    "met" if where != "listed" else "partial",
                    EVIDENCE_WORDS[where].capitalize(),
                    "skill",
                )
            )
        else:
            weights.append(0.0)
            requirements.append(Requirement(skill, "missing", "Not on your resume", "skill"))
    if req:
        needed = max(min(len(req), 3), 0.7 * len(req))  # few people have every one of a long list
        skills_fit = min(1.0, sum(weights) / needed)
        have = sum(1 for w in weights if w > 0)
        parts.append(
            Part(
                "skills",
                "Required skills",
                35 * skills_fit,
                35,
                f"You have {have} of the {len(req)} skills it asks for.",
            )
        )
    else:
        skills_fit = 0.0

    # --- nice-to-haves (10)
    pref = needs.preferred_skills
    if pref:
        pref_have = [s for s in pref if s in resume_skills]
        pref_fit = len(pref_have) / len(pref)
        for skill in pref:
            requirements.append(
                Requirement(
                    skill,
                    "met" if skill in resume_skills else "missing",
                    "Nice to have" + (", and you have it" if skill in resume_skills else ""),
                    "preferred",
                )
            )
        parts.append(
            Part(
                "preferred", "Nice-to-haves", 10 * pref_fit, 10, f"You have {len(pref_have)} of {len(pref)}."
            )
        )
    elif req:
        pref_fit = skills_fit  # nothing extra asked: weigh as the required skills
        parts.append(
            Part(
                "preferred",
                "Nice-to-haves",
                10 * pref_fit,
                10,
                "None listed; counted like the required skills.",
            )
        )
    else:
        pref_fit = 0.0

    # --- key terms (15)
    terms = needs.key_terms or title_words(job.get("title") or "")
    terms_matched = [t for t in terms if _has_term(t, resume_words, resume_phrases)]
    terms_missing = [t for t in terms if t not in terms_matched]
    terms_fit = len(terms_matched) / len(terms) if terms else 0.6
    parts.append(
        Part(
            "terms",
            "The posting's key terms",
            15 * terms_fit,
            15,
            f"Your resume uses {len(terms_matched)} of its {len(terms)} key terms."
            if terms
            else "Nothing distinctive to compare, so this counts as average.",
        )
    )

    # --- experience (20)
    level_fit = LEVEL_FIT.get(level, LEVEL_FIT["new_grad"]).get(job.get("level") or "mid", 0.5)
    if needs.years:
        have_years = months / 12
        years_fit = min(1.0, have_years / needs.years)
        exp_fit = 0.5 * level_fit + 0.5 * years_fit
        status = "met" if years_fit >= 1 else "partial" if years_fit >= 0.5 else "missing"
        requirements.append(
            Requirement(
                f"{needs.years:g}+ years of experience",
                status,
                f"You have {MONTHS_WORDS(months)}",
                "experience",
            )
        )
        detail = f"It asks for {needs.years:g}+ years; you have {MONTHS_WORDS(months)}."
    else:
        exp_fit = level_fit
        detail = {
            "intern": "An internship, for current students.",
            "new_grad": "A new grad role, for recent and upcoming graduates.",
            "mid": "A role for people with some full-time experience.",
            "senior": "A senior role, usually several years of full-time experience.",
        }.get(job.get("level") or "mid", "")
    parts.append(Part("experience", "Experience", 20 * exp_fit, 20, detail))

    # --- education (10)
    edu_fit, edu_detail = _education(needs, education, level, requirements)
    parts.append(Part("education", "Education", 10 * edu_fit, 10, edu_detail))

    # --- role and title (10)
    roles = profile.get("roles") or {}
    best = max(roles.values()) if roles else 0
    role = job.get("role_type") or "other"
    role_fit = 0.15 if role == "other" else min(1.0, roles.get(role, 0) / best if best else 0.5)
    words = title_words(job.get("title") or "")
    words_found = [w for w in words if stem(w) in resume_words]
    title_fit = len(words_found) / len(words) if words else 0.6
    rt_fit = 0.6 * role_fit + 0.4 * title_fit
    parts.append(
        Part(
            "role",
            "Role and title",
            10 * rt_fit,
            10,
            f"Your resume reads as {ROLE_NAMES.get(profile.get('top_role') or 'sde', 'tech')} work.",
        )
    )

    limited = needs.empty
    notes: list[str] = []
    if limited:
        # only career stage, role, title and education can be compared: they carry all the points
        reweight = {"experience": 40, "role": 40, "terms": 10, "education": 10}
        parts = [
            Part(p.key, p.label, p.points / p.max * reweight[p.key], reweight[p.key], p.detail)
            for p in parts
            if p.key in reweight
        ]
        score = round(sum(p.points for p in parts))
        cap = (
            70 if role_fit >= 0.3 else 45
        )  # without a description, a different kind of work can't look like a fit
        if score > cap:
            notes.append(f"Capped at {cap} (from {score}) since there's no description to go on.")
            score = cap
        notes.append(
            "Ghostless doesn't have this posting's description, so the score uses its title, level and role only. "
            "Read the posting to see what it asks for."
        )
    else:
        score = round(sum(p.points for p in parts))
        # a great skills match doesn't make a senior role a fit for a student
        cap = round(30 + 60 * level_fit) if level_fit < 0.5 else 100
        if needs.enrolled and not (education.get("still_studying") or level == "student"):
            cap = min(cap, 40)
        if score > cap:
            notes.append(
                f"Capped at {cap} (from {score}) because the role is meant for a different career stage than yours."
            )
            score = cap
        if not needs.structured and job.get("description"):
            notes.append(
                "This description has no clear requirements section, so every skill it mentions counts as required."
            )

    matched = [s for s in req + pref if s in resume_skills]
    missing = [s for s in req if s not in resume_skills] + [s for s in pref if s not in resume_skills]
    return Match(
        score=score,
        label=label_for(score),
        skills_matched=matched,
        skills_missing=missing[:12],
        components={
            "skills": round(skills_fit, 2),
            "terms": round(terms_fit, 2),
            "experience": round(exp_fit, 2),
            "education": round(edu_fit, 2),
            "role": round(rt_fit, 2),
            # kept for older clients
            "level": round(level_fit, 2),
            "title": round(title_fit, 2),
        },
        suggestions=suggest(profile, job, needs, requirements, terms_missing, level_fit, role_fit, limited),
        limited=limited,
        notes=notes,
        breakdown=[Part(p.key, p.label, round(p.points, 1), p.max, p.detail) for p in parts],
        requirements=requirements,
        terms_matched=terms_matched,
        terms_missing=terms_missing,
    )


def _education(
    needs: Needs, education: dict, level: str, requirements: list[Requirement]
) -> tuple[float, str]:
    have = education.get("degree")
    studying = bool(education.get("still_studying"))
    fields = [f.lower() for f in education.get("fields") or []]
    fit, details = 1.0, []
    if needs.degree:
        wanted = f"{needs.degree.capitalize()}'s degree" if needs.degree != "phd" else "PhD"
        if needs.degree_fields:
            wanted += f" in {needs.degree_fields[0].title()}"
        rank_have = DEGREE_RANK.get(have or "", 0)
        rank_need = DEGREE_RANK[needs.degree]
        field_ok = not needs.degree_fields or any(
            f in fields or any(f.split()[0] in g for g in fields) for f in needs.degree_fields
        )
        if rank_have >= rank_need and field_ok:
            status, detail = "met", "Your degree matches" + (" (in progress)" if studying else "")
        elif rank_have >= rank_need:
            status, detail, fit = "partial", "Your degree is in a different field", 0.7
        elif needs.degree_flexible:
            status, detail, fit = "partial", "It accepts equivalent experience instead", 0.6
        else:
            status, detail, fit = "missing", "Your resume doesn't show this degree", 0.2
        requirements.append(Requirement(wanted, status, detail, "education"))
        details.append(f"It asks for a {wanted.lower()}." if needs.degree != "phd" else "It asks for a PhD.")
    if needs.enrolled:
        ok = studying or level == "student"
        requirements.append(
            Requirement(
                "Currently enrolled in school",
                "met" if ok else "missing",
                "You're still in school" if ok else "Your resume doesn't show current studies",
                "enrollment",
            )
        )
        fit = min(fit, 1.0 if ok else 0.2)
        details.append("It's for current students.")
    if not details:
        return (1.0 if have or studying else 0.8), "No specific degree asked for."
    return fit, " ".join(details)


def suggest(
    profile: dict,
    job: dict,
    needs: Needs,
    requirements: list[Requirement],
    terms_missing: list[str],
    level_fit: float,
    role_fit: float,
    limited: bool,
) -> list[str]:
    """What to change, most useful first."""
    out: list[str] = []
    missing = [r.text for r in requirements if r.kind == "skill" and r.status == "missing"]
    listed_only = [r.text for r in requirements if r.kind == "skill" and r.status == "partial"]
    if missing:
        top = missing[:4]
        listed = ", ".join(top[:-1]) + (f" and {top[-1]}" if len(top) > 1 else top[0])
        out.append(
            f"It requires {listed}. If you've used {'them' if len(top) > 1 else 'it'}, add "
            f"{'them' if len(top) > 1 else 'it'} to your skills and show where in a bullet. If not, a small project is "
            "the quickest way to get there."
        )
    if listed_only:
        top = listed_only[:3]
        listed = ", ".join(top[:-1]) + (f" and {top[-1]}" if len(top) > 1 else top[0])
        out.append(
            f"{listed} {'are' if len(top) > 1 else 'is'} only in your skills list. Show {'each' if len(top) > 1 else 'it'} "
            "in a work or project bullet with what you built and the result. That counts for more."
        )
    if terms_missing and not limited:
        top = terms_missing[:3]
        out.append(
            f"The posting keeps coming back to {', '.join(repr(t)[1:-1] for t in top)}. If that matches work you've done, "
            "use the same words in your bullets."
        )
    for r in requirements:
        if r.kind == "experience" and r.status != "met":
            out.append(
                f"It asks for {r.text.lower()}; {r.detail[0].lower() + r.detail[1:]}. Count internships, co-ops and "
                "substantial projects, and give their dates."
            )
        if r.kind == "education" and r.status == "missing":
            out.append(
                f"It asks for a {r.text.lower()}. If you have it or are working toward it, list it with dates."
            )
        if r.kind == "enrollment" and r.status == "missing":
            out.append(
                "It's for current students. If you are one, add your school and expected graduation date."
            )
    job_level = job.get("level")
    level = profile.get("level")
    if level_fit < 0.5:
        if job_level == "senior":
            out.append(
                "This is a senior role, which usually means several years of full-time experience. Treat it as a long shot for now."
            )
        elif job_level == "intern" and level not in ("student", None):
            out.append("This is an internship, usually open only to current students.")
        elif job_level == "mid" and level == "student":
            out.append(
                "This role expects full-time experience. Internship and co-op postings will be a better fit while you're in school."
            )
    if role_fit < 0.4 and job.get("role_type") not in (None, "other"):
        top_role = profile.get("top_role") or "sde"
        out.append(
            f"Your resume reads mostly as {ROLE_NAMES.get(top_role, top_role)} work. If you've done "
            f"{ROLE_NAMES.get(job['role_type'], 'this')} work, move it higher and describe it in more detail."
        )
    if (job.get("signals") or {}).get("risk") == "high":
        out.append(
            "Heads up: this posting is flagged high ghost risk, so your time may go further elsewhere."
        )
    return out[:6]


def recommend(
    profile: dict,
    jobs: list[dict],
    limit: int = 30,
    offset: int = 0,
    describe: Callable[[list[int]], dict[int, str]] | None = None,
    deep: int = 250,
) -> list[tuple[dict, Match]]:
    """Jobs ranked by fit. Every job gets a quick score from its skills; the
    best `deep` are then scored in full against their descriptions (when
    `describe` can supply them) and re-ranked. Ties go to the newer posting."""
    quick = [(job, score_job(profile, job)) for job in jobs]
    quick.sort(key=lambda pair: (-pair[1].score, pair[1].limited, -_freshness(pair[0])))
    if describe:
        head = quick[: max(deep, offset + limit)]
        texts = describe([job["id"] for job, _ in head])
        rescored = [
            (job, score_job(profile, {**job, "description": texts.get(job["id"], "")})) for job, _ in head
        ]
        rescored.sort(key=lambda pair: (-pair[1].score, pair[1].limited, -_freshness(pair[0])))
        quick = rescored + quick[len(head) :]
    return quick[offset : offset + limit]


def _freshness(job: dict) -> float:
    days = (job.get("signals") or {}).get("days_open")
    return -math.log1p(days) if isinstance(days, int) else -10.0
