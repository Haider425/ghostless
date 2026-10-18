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

# Role types. Checked in the order of ROLE_RULES: the first match wins.
#   sde       software, web, mobile, infrastructure, DevOps/SRE, QA automation
#   data_eng  data and analytics engineering, data platforms
#   data      data science, analytics, BI, quantitative analysis
#   ml        machine learning, AI, deep learning, applied and research science
#   hardware  silicon, ASIC/FPGA, hardware design and verification, embedded, firmware
#   security  security engineering and analysis
#   other     everything else, including non-engineering roles at tech companies

# Roles that mention tech words but aren't engineering jobs
_NOT_ENGINEERING = re.compile(
    r"\b(recruit\w*|sourcer|talent\s+(acquisition|partner)|account\s+(executive|manager)|sales|"
    r"pre-?sales|marketing|customer\s+success|support\s+(specialist|representative|agent)|"
    r"product\s+(manager|marketing|owner)|program\s+manager|project\s+manager|"
    r"designer|ux\s+researcher|counsel|lawyer|paralegal|accountant|payroll|"
    r"technical\s+writer|business\s+analyst|teller|advisor|financial\s+planner)\b",
    re.I,
)
_SECURITY = re.compile(
    r"\b(security|cyber\s*security|infosec|penetration\s+test\w*|pen\s*tester|red\s+team|"
    r"threat\s+(intelligence|detection|hunter)|soc\s+analyst|detection\s+(and|&)\s+response|"
    r"vulnerability|appsec|identity\s+(and|&)\s+access|iam\s+engineer)\b",
    re.I,
)
_ML = re.compile(
    r"\b(machine\s+learning|ml\s*(engineer|ops|platform|infrastructure|scientist|researcher)|mlops|"
    r"deep\s+learning|artificial\s+intelligence|ai\s+(engineer|researcher|scientist|research|"
    r"infrastructure|platform|developer|software)|generative\s+ai|gen\s*ai|llms?|"
    r"applied\s+scientist|research\s+scientist|research\s+engineer|computer\s+vision|nlp|"
    r"natural\s+language|perception|speech\s+recognition|reinforcement\s+learning|"
    r"inference\s+engineer|ai/ml)\b",
    re.I,
)
_DATA_ENG = re.compile(
    r"\b(data|analytics|etl|big\s*data|data\s+platform|data\s+infrastructure|database)\s+"
    r"(platform\s+|infrastructure\s+|pipeline\s+)?(engineer|developer|architect)"
    r"|\bdatabase\s+administrator\b|\bdba\b|\bdata\s+warehouse\b",
    re.I,
)
_DATA = re.compile(
    r"\b(data\s+scien\w*|data\s+analy\w*|analytics|business\s+intelligence|bi\s+(developer|analyst|engineer)|"
    r"quantitative\s+(analyst|researcher|developer)|quant\b|statistician|decision\s+scien\w*|"
    r"(product|marketing|insights?|reporting|risk|fraud)\s+analyst|data\s+(specialist|steward))",
    re.I,
)
_HARDWARE = re.compile(
    r"\b(hardware|asic|fpga|soc|vlsi|rtl|silicon|semiconductor|chip|cpu|gpu\s+(architect|design|"
    r"verification|validation)|physical\s+design|design\s+verification|dft|analog|mixed[\s-]signal|"
    r"circuit|pcb|board\s+design|signal\s+integrity|power\s+integrity|layout\s+engineer|"
    r"embedded|firmware|electrical\s+engineer|post-?silicon|pre-?silicon|emulation|"
    r"validation\s+engineer|packaging\s+engineer|thermal\s+engineer|optical\s+engineer)\b",
    re.I,
)
_SDE = re.compile(
    r"\b(software|backend|back-end|frontend|front-end|full[\s-]?stack|mobile|ios|android|web|"
    r"platform|infrastructure|cloud|devops|dev\s*ops|site\s+reliability|sre|systems|"
    r"distributed\s+systems|kernel|compiler|graphics|game|gameplay|api|application|"
    r"automation|build|release|tools|test|qa|quality|integration|java|python|\.net|c\+\+|"
    r"golang|react|node|salesforce|mainframe|cobol|sap|servicenow|network|database\s+reliability)\b.*\b(engineer|developer|"
    r"programmer|architect|specialist|lead)\b"
    r"|\b(swe|sde|sdet|sre|developer|programmer|software\s+engineer\w*)\b"
    r"|\bmember\s+of\s+technical\s+staff\b|\bmts\b"
    r"|\b(engineering\s+manager|devops|site\s+reliability)\b",
    re.I,
)

ROLE_RULES = (
    ("security", _SECURITY),
    ("ml", _ML),
    ("data_eng", _DATA_ENG),
    ("data", _DATA),
    ("hardware", _HARDWARE),
    ("sde", _SDE),
)
ROLE_TYPES = ("sde", "data_eng", "data", "ml", "hardware", "security", "other")
TECH_ROLE_TYPES = ROLE_TYPES[:-1]

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
    """The role type for a job title, or "other"."""
    if _NOT_ENGINEERING.search(title) and not re.search(r"\b(engineer|developer|scientist)\b", title, re.I):
        return "other"
    if re.search(
        r"\b(sales|solutions?|pre-?sales|customer)\s+(engineer|architect|consultant)\b", title, re.I
    ):
        return "other"  # customer-facing technical roles
    for role, pattern in ROLE_RULES:
        if pattern.search(title):
            return role
    return "other"


# US places that share a Canadian city's name: "Vancouver, WA", "London, KY"
_US_PLACE = re.compile(r",\s*(wa|washington|usa|us|united states)\b", re.I)


def is_canada(location: str) -> bool:
    """True if any of the posting's places (separated by |) is in Canada."""
    if not location:
        return False
    for place in location.split("|"):
        if _CANADA.search(place) and not _US_PLACE.search(place):
            return True
    return False


def is_remote(location: str, source_remote: bool = False) -> bool:
    return source_remote or bool(location and _REMOTE.search(location))


_TERM = re.compile(r"\b(summer|fall|autumn|winter|spring)\s*(?:term\s*)?[-,/]?\s*'?(20\d\d|\d\d)\b", re.I)


def parse_terms(title: str) -> list[str]:
    """Seasons named in a title: "SWE Intern (Summer 2027)" -> ["Summer 2027"]."""
    out = []
    for season, year in _TERM.findall(title):
        season = "Fall" if season.lower() == "autumn" else season.capitalize()
        year = year if len(year) == 4 else f"20{year}"
        out.append(f"{season} {year}")
    return list(dict.fromkeys(out))


def enrich(job: Job, skills: list[str]) -> Job:
    """Fill in every derived field: classification, skills and disclosures."""
    job.level = classify_level(job.title)
    job.role_type = classify_role(job.title)
    job.is_canada = is_canada(job.location)
    job.is_remote = is_remote(job.location, job.source_remote)
    job.skills = skills
    if not job.terms:
        job.terms = parse_terms(job.title)

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
