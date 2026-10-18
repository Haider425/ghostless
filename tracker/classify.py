"""Rule-based classification of job level, role type and location.

Deliberately simple and testable: every rule has a unit test, and
misclassifications are fixed by adding a rule plus a test case.
"""

import re

from tracker.disclosures import fingerprint, parse_ai_screening, parse_salary, parse_vacancy
from tracker.models import Job

_INTERN = re.compile(r"\b(intern(ship)?|co-?op|student|placement)\b", re.I)
_NEW_GRAD = re.compile(
    r"\b(new\s*grad(uate)?|university\s*grad(uate)?|recent\s*grad(uate)?|"
    r"early\s*career|entry[\s-]*level|junior|jr\.?|graduate)\b"
    r"|\b(engineer|developer)\s*(i|1)\b",
    re.I,
)
_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|architect|vp)\b"
    r"|\b(engineer|developer)\s*(iii|iv|3|4)\b",
    re.I,
)

_DATA_ENG = re.compile(r"\b(data|analytics|etl|big\s*data)\s+(platform\s+)?engineer", re.I)
_DATA = re.compile(
    r"\b(data\s+scien|data\s+analy|machine\s+learning|ml\s+engineer|business\s+intelligence)",
    re.I,
)
_SDE = re.compile(
    r"\b(software|backend|back-end|frontend|front-end|full[\s-]?stack|platform|"
    r"infrastructure|mobile|ios|android|web|devops|site\s+reliability|sre)\b"
    r".*\b(engineer|developer)\b"
    r"|\b(swe|sde)\b"
    r"|\b(software\s+(engineer|developer))\b",
    re.I,
)

_CANADA = re.compile(
    r"\b(canada|canadian|toronto|vancouver|montr[eé]al|waterloo|ottawa|calgary|"
    r"edmonton|winnipeg|halifax|qu[eé]bec|kitchener|mississauga|markham|"
    r"ontario|british\s+columbia|alberta)\b"
    r"|,\s*(on|bc|ab|qc|mb|ns)\b",
    re.I,
)
_REMOTE = re.compile(r"\b(remote|anywhere|distributed|work\s+from\s+home)\b", re.I)


def classify_level(title: str) -> str:
    # Order matters: "Senior Software Engineer Intern" does not exist,
    # but "Intern, Senior Leadership Team" does, so intern wins first.
    if _INTERN.search(title):
        return "intern"
    if _SENIOR.search(title):
        return "senior"
    if _NEW_GRAD.search(title):
        return "new_grad"
    return "mid"


def classify_role(title: str) -> str:
    if _DATA_ENG.search(title):
        return "data_eng"
    if _DATA.search(title):
        return "data"
    if _SDE.search(title):
        return "sde"
    return "other"


def is_canada(location: str) -> bool:
    return bool(location and _CANADA.search(location))


def is_remote(location: str, source_remote: bool = False) -> bool:
    return source_remote or bool(location and _REMOTE.search(location))


def enrich(job: Job, skills: list[str]) -> Job:
    """Fill in every derived field: classification, skills and disclosures."""
    job.level = classify_level(job.title)
    job.role_type = classify_role(job.title)
    job.is_canada = is_canada(job.location)
    job.is_remote = is_remote(job.location, job.source_remote)
    job.skills = skills

    salary = parse_salary(job.description)
    if salary:
        job.salary_min, job.salary_max, job.salary_period = salary.minimum, salary.maximum, salary.period
        # An unlabelled "$" in a Canada-only posting is Canadian dollars.
        job.salary_currency = salary.currency or ("CAD" if job.is_canada and not job.is_remote else None)
    # Text disclosures win, but keep a status the source itself reported
    # (e.g. Apple's pipeline flag) when the description says nothing.
    job.vacancy = parse_vacancy(job.description) or job.vacancy
    ai_screening = parse_ai_screening(job.description)
    if ai_screening is not None:
        job.ai_screening = ai_screening
    job.fingerprint = fingerprint(job.title, job.location, job.description)
    return job