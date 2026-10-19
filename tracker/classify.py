"""Rule-based classification of job level, role type and location.

Deliberately simple and testable: every rule has a unit test, and
misclassifications are fixed by adding a rule plus a test case.
"""

import re
from datetime import date, datetime, timezone

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


# ---------- Seasons (work terms) ----------
#
# A season is when the work happens: "Summer 2027". Titles name it in many
# ways: "(Summer 2027)", "Co-op, Winter-27", "2027 Summer Internship",
# "Spring/Summer 2027", "Fall/Winter 2026". Many postings only say it in the
# description ("work term beginning January 2027"), so intern and new grad
# descriptions are read too, but only next to start or term wording, so
# "founded in Spring 2016" never counts. A graduation date ("Graduating
# Winter 2026") is about the applicant, not the job, and never counts.
# Months map to the Canadian co-op terms: January-April Winter, May-August
# Summer, September-December Fall.

_SEASON = r"summer|fall|autumn|winter|spring"
_SEASONS = rf"(?:{_SEASON})(?:\s*(?:/|&|,|\+|\band\b|\bor\b)\s*(?:{_SEASON}))*"
_TERM = re.compile(rf"\b({_SEASONS})\s*(?:term\s*)?[-,/]?\s*'?(20\d\d|\d\d)\b", re.I)
_TERM_YEAR_FIRST = re.compile(rf"\b(20\d\d)\s*[-/]?\s*({_SEASONS})\b", re.I)
# "Graduation Date Winter 2026", "graduating in May 2028", "graduated in Winter 2026";
# not "Graduate Internship - Winter 2027", which names a program
_GRADUATION = re.compile(
    r"\bgraduat(?:ion|ing|ed|es)\b|\bgraduate\s+(?:date|in|by|between|before|after|from|no\s+later)\b"
    r"|\bconvocat\w*|\bdegree\s+(?:completion|conferr)\w*",
    re.I,
)
_START_WORDS = (
    r"start(?:s|ing)?|begin(?:s|ning)?|commenc\w*|work[\s-]?terms?|terms?|internships?|co-?ops?|placements?"
    r"|programs?|cohorts?|intakes?|available|from|duration|session"
)
_START_CONTEXT = re.compile(rf"\b(?:{_START_WORDS})\b", re.I)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_START = re.compile(
    r"\b(?:start(?:s|ing)?|begin(?:s|ning)?|commenc\w*)\b(?:\s+(?:date|on|in|of|from|around|early|mid|late|-|:))*\s+"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(20\d\d)\b",
    re.I,
)
_HIRING_STEPS = re.compile(
    r"\b(?:applications?|apply|interviews?|reviewing|deadline|recruiting|closes?)\b", re.I
)
_MORE_MONTHS = re.compile(
    r"\s*(?:,|/|\bor\b|\band\b)\s*(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?\s+(20\d\d)\b",
    re.I,
)
_DESCRIPTION_CHARS = 20_000  # seasons are stated near the top; the rest is boilerplate


def _season_name(season: str) -> str:
    return "Fall" if season.lower() == "autumn" else season.capitalize()


def _month_season(month: int) -> str:
    return "Winter" if month <= 4 else "Summer" if month <= 8 else "Fall"


def _about_graduation(text: str, start: int) -> bool:
    return bool(_GRADUATION.search(text[max(0, start - 40) : start]))


def _named_seasons(text: str) -> list[tuple[int, str, str]]:
    """(position, season, year) for every season and year written together."""
    found = []
    for m in _TERM.finditer(text):
        year = m[2] if len(m[2]) == 4 else f"20{m[2]}"
        found += [(m.start(), _season_name(s), year) for s in re.findall(_SEASON, m[1], re.I)]
    for m in _TERM_YEAR_FIRST.finditer(text):
        found += [(m.start(), _season_name(s), m[1]) for s in re.findall(_SEASON, m[2], re.I)]
    return sorted(found, key=lambda f: f[0])  # stable: "Winter/Spring" keeps its written order


def parse_terms(
    title: str, description: str = "", level: str | None = None, year: int | None = None
) -> list[str]:
    """Seasons a posting is for: from its title, and for intern and new grad
    roles from start dates in its description. `year` is when the posting
    was first seen: description seasons must fall in that year or the next
    two, so an old cohort or a company history never counts. A season in the
    title is authoritative: the description is only read when it names none."""
    out = [f"{season} {y}" for at, season, y in _named_seasons(title) if not _about_graduation(title, at)]
    if description and level in ("intern", "new_grad") and not out:
        text = description[:_DESCRIPTION_CHARS]
        recent = range(year, year + 3) if year else None
        for at, season, y in _named_seasons(text):
            nearby = text[max(0, at - 60) : at + 40]
            if (
                (recent is None or int(y) in recent)
                and _START_CONTEXT.search(nearby)
                and not _about_graduation(text, at)
            ):
                out.append(f"{season} {y}")
        for m in _MONTH_START.finditer(text):
            if _about_graduation(text, m.start()) or _HIRING_STEPS.search(
                text[max(0, m.start() - 60) : m.start()]
            ):
                continue  # "begin reviewing applications starting August 2026" is not the work term
            # "starts in January 2027 or June 2027": every start date offered
            dates, at = [(m[1], m[2])], m.end()
            while more := _MORE_MONTHS.match(text, at):  # matches right where the last date ended
                dates.append((more[1], more[2]))
                at = more.end()
            for month, y in dates:
                if recent is None or int(y) in recent:
                    out.append(f"{_month_season(_MONTHS[month[:3].lower()])} {y}")
    return list(dict.fromkeys(out))


_SEASON_START_MONTH = {"Winter": 1, "Spring": 3, "Summer": 5, "Fall": 9}


def term_start(term: str) -> tuple[int, int]:
    """(year, month) a season starts: "Fall 2026" -> (2026, 9). Sorts terms in time order."""
    season, _, year = term.partition(" ")
    return int(year), _SEASON_START_MONTH.get(season, 13)


def is_upcoming(term: str, today: date) -> bool:
    """A season that has not started yet: in October 2026, Winter 2027 is and
    Fall 2026 is not. A season is under way from its first month (Fall from 1 September)."""
    try:
        return term_start(term) > (today.year, today.month)
    except ValueError:
        return False


def enrich(job: Job, skills: list[str]) -> Job:
    """Fill in every derived field: classification, skills and disclosures."""
    job.level = classify_level(job.title)
    job.role_type = classify_role(job.title)
    job.is_canada = is_canada(job.location)
    job.is_remote = is_remote(job.location, job.source_remote)
    job.skills = skills
    # a job list's own season labels win; otherwise read the title and description
    if not job.terms:
        job.terms = parse_terms(job.title, job.description, job.level, datetime.now(timezone.utc).year)

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
