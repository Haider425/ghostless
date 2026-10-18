"""Describe a resume: skills, level, experience, education, contact details
and the shape of its bullets. Rule based and deterministic, so the same
resume always gets the same result."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from tracker.classify import TECH_ROLE_TYPES, classify_role
from tracker.skills import extract_skills

# ---------- sections ----------

SECTION_NAMES = {
    "summary": ("summary", "profile", "about me", "objective", "professional summary"),
    "education": ("education", "academic background", "education and certifications"),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "relevant experience",
        "technical experience",
        "internships",
    ),
    "projects": (
        "projects",
        "personal projects",
        "technical projects",
        "academic projects",
        "selected projects",
    ),
    "skills": (
        "skills",
        "technical skills",
        "skills and tools",
        "technologies",
        "core competencies",
        "tech stack",
    ),
    "certifications": ("certifications", "certificates", "licenses and certifications"),
    "awards": ("awards", "honours", "honors", "achievements", "awards and honours"),
    "leadership": (
        "leadership",
        "leadership and activities",
        "activities",
        "extracurriculars",
        "volunteer",
        "volunteering",
        "volunteer experience",
        "community involvement",
    ),
}
_HEADING_LOOKUP = {name: key for key, names in SECTION_NAMES.items() for name in names}


def _heading_key(line: str) -> str | None:
    cleaned = re.sub(r"[^a-z& ]", "", line.lower()).replace("&", "and").strip()
    if not cleaned or len(cleaned) > 40:
        return None
    return _HEADING_LOOKUP.get(cleaned)


def split_sections(text: str) -> dict[str, str]:
    """{section: text}. Text before the first heading goes in 'header'."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        key = _heading_key(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip() or k != "header"}


# ---------- dates ----------

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_SEASON = r"(?:spring|summer|fall|autumn|winter)"
_POINT = rf"(?:{_MONTH}\.?,?\s+\d{{4}}|{_SEASON}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_RANGE = re.compile(
    rf"(?P<start>{_POINT})\s*(?:-|–|—|to|until)\s*(?P<end>{_POINT}|present|current|now|ongoing|today)",
    re.I,
)
_SEASON_MONTH = {"spring": 1, "summer": 5, "fall": 9, "autumn": 9, "winter": 1}


def _point(value: str, today: date) -> tuple[int, int] | None:
    value = value.strip().lower().rstrip(".")
    if value in ("present", "current", "now", "ongoing", "today"):
        return today.year, today.month
    if m := re.match(r"(\d{1,2})/(\d{4})", value):
        return int(m[2]), max(1, min(12, int(m[1])))
    if m := re.match(rf"({_SEASON})\s+(\d{{4}})", value):
        return int(m[2]), _SEASON_MONTH[m[1]]
    if m := re.match(r"([a-z]+)\.?,?\s+(\d{4})", value):
        return int(m[2]), _MONTHS.get(m[1][:4] if m[1].startswith("sept") else m[1][:3], 1)
    if m := re.fullmatch(r"\d{4}", value):
        return int(m[0]), 1
    return None


def date_ranges(text: str, today: date | None = None) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    today = today or date.today()
    ranges = []
    for m in _RANGE.finditer(text):
        start, end = _point(m["start"], today), _point(m["end"], today)
        if not start or not end or not (1970 <= start[0] <= today.year + 6):
            continue
        if end < start:
            continue
        ranges.append((start, min(end, (today.year, today.month))))
    return ranges


def months_of_experience(ranges: list[tuple[tuple[int, int], tuple[int, int]]]) -> int:
    """Total months covered, counting overlapping jobs once."""
    spans = sorted((s[0] * 12 + s[1], e[0] * 12 + e[1] + 1) for s, e in ranges)
    total, current_start, current_end = 0, None, None
    for start, end in spans:
        if current_end is None or start > current_end:
            if current_end is not None:
                total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += current_end - current_start
    return total


# ---------- education ----------

_DEGREE = re.compile(
    r"\b(ph\.?\s?d|doctorate|master'?s?|m\.?\s?sc|m\.?\s?eng|m\.?\s?a\.?\s?sc|mba|bachelor'?s?|b\.?\s?sc|"
    r"b\.?\s?eng|b\.?\s?a\.?\s?sc|b\.?\s?comm?|b\.?\s?a\b|b\.?\s?s\b|honou?rs\s+b|diploma|advanced\s+diploma|"
    r"associate'?s?\s+degree|certificate\s+program)",
    re.I,
)
_DEGREE_RANK = [
    ("phd", r"ph\.?\s?d|doctorate"),
    ("masters", r"master|m\.?\s?sc|m\.?\s?eng|m\.?\s?a\.?\s?sc|mba"),
    ("bachelors", r"bachelor|b\.?\s?sc|b\.?\s?eng|b\.?\s?a|b\.?\s?s\b|b\.?\s?comm?|honou?rs"),
    ("diploma", r"diploma|associate|certificate"),
]
_FIELDS = (
    "computer science",
    "software engineering",
    "computer engineering",
    "electrical engineering",
    "data science",
    "mathematics",
    "statistics",
    "information technology",
    "information systems",
    "mechatronics",
    "engineering physics",
    "physics",
    "business",
    "economics",
    "cybersecurity",
    "artificial intelligence",
    "game development",
    "applied science",
)
_EXPECTED = re.compile(
    rf"\b(expected|anticipated|graduating|graduation|class\s+of|candidate)\b[^\n]{{0,25}}?(?P<when>{_POINT})",
    re.I,
)


def education_summary(education: str, today: date) -> dict:
    degree_level = None
    for name, pattern in _DEGREE_RANK:
        if re.search(rf"\b({pattern})", education, re.I):
            degree_level = name
            break
    lower = education.lower()
    fields = [f for f in _FIELDS if f in lower]
    grad = None
    if m := _EXPECTED.search(education):
        grad = _point(m["when"], today)
    else:
        ends = [end for _, end in date_ranges(education, date(today.year + 6, 12, 1))]
        years = re.findall(r"\b(19[89]\d|20[0-4]\d)\b", education)
        if ends:
            grad = max(ends)
        elif years:
            grad = (max(int(y) for y in years), 5)
    studying = bool(grad and (grad[0], grad[1]) >= (today.year, today.month)) or bool(
        re.search(r"\b(expected|anticipated|candidate|in progress|current(ly)? enrolled)\b", education, re.I)
    )
    return {
        "degree": degree_level,
        "fields": fields[:3],
        "graduation": f"{grad[0]:04d}-{grad[1]:02d}" if grad else None,
        "still_studying": studying,
    }


# ---------- bullets ----------

_BULLET = re.compile(r"^\s*(?:[•●▪◦‣∙·\-–*]|\d+[.)])\s+")
_STRONG_VERBS = {
    "built",
    "designed",
    "developed",
    "led",
    "launched",
    "shipped",
    "created",
    "implemented",
    "automated",
    "reduced",
    "improved",
    "increased",
    "optimized",
    "migrated",
    "architected",
    "engineered",
    "delivered",
    "deployed",
    "analyzed",
    "scaled",
    "refactored",
    "integrated",
    "streamlined",
    "owned",
    "drove",
    "founded",
    "mentored",
    "established",
    "accelerated",
    "cut",
    "saved",
    "won",
    "published",
    "trained",
    "modeled",
    "debugged",
    "resolved",
    "spearheaded",
    "redesigned",
    "rebuilt",
    "wrote",
    "tested",
    "configured",
}
_WEAK_OPENERS = re.compile(
    r"^(responsible\s+for|helped|assisted|worked\s+on|participated\s+in|involved\s+in|tasked\s+with|"
    r"duties\s+included|in\s+charge\s+of|was\s+part\s+of|helping|working\s+on|did|handled)\b",
    re.I,
)
_NUMBER = re.compile(r"\d|%|\$|\b(one|two|three|four|five|ten|hundred|thousand|million|billion)\b", re.I)


def bullets(text: str) -> list[str]:
    found = [_BULLET.sub("", line).strip() for line in text.splitlines() if _BULLET.match(line)]
    if len(found) >= 3:
        return [b for b in found if len(b) > 15]
    # PDFs often lose bullet glyphs: fall back to sentence-like lines that start with a verb
    return [
        line.strip()
        for line in text.splitlines()
        if len(line.strip()) > 40
        and re.match(r"^[A-Z][a-z]+(ed|ing)?\b", line.strip())
        and line.split()[0].lower() in _STRONG_VERBS | {"responsible", "helped", "assisted", "worked"}
    ]


# ---------- roles ----------

# How strongly a skill points at each kind of role
_SKILL_ROLES: dict[str, dict[str, float]] = {}
for _skills, _role, _weight in [
    (
        (
            "Java",
            "JavaScript",
            "TypeScript",
            "C#",
            "Go",
            "Rust",
            "Kotlin",
            "Swift",
            "Ruby",
            "PHP",
            "React",
            "Angular",
            "Vue",
            "Next.js",
            "Node.js",
            "Express",
            "Django",
            "Flask",
            "FastAPI",
            "Spring",
            "ASP.NET",
            "GraphQL",
            "REST APIs",
            "gRPC",
            "Microservices",
            "Distributed systems",
            "Docker",
            "Kubernetes",
            "Terraform",
            "AWS",
            "GCP",
            "Azure",
            "CI/CD",
            "GitHub Actions",
            "Jenkins",
            "Linux",
            "Git",
            "Testing",
            "Selenium",
            "Playwright",
            "Cypress",
            "HTML/CSS",
            "React Native",
            "Flutter",
            "Android",
            "iOS",
            "Redis",
            "PostgreSQL",
            "MySQL",
            "MongoDB",
            "Bash",
            "Prometheus",
            "Ansible",
        ),
        "sde",
        1.0,
    ),
    (
        (
            "SQL",
            "Spark",
            "Kafka",
            "Airflow",
            "dbt",
            "Snowflake",
            "BigQuery",
            "Databricks",
            "Hadoop",
            "ETL",
            "SQL Server",
            "Oracle",
            "Cassandra",
            "DynamoDB",
            "Elasticsearch",
            "PostgreSQL",
            "Scala",
        ),
        "data_eng",
        1.0,
    ),
    (
        (
            "SQL",
            "Pandas",
            "NumPy",
            "R",
            "Statistics",
            "A/B testing",
            "Tableau",
            "Power BI",
            "Excel",
            "scikit-learn",
            "MATLAB",
        ),
        "data",
        1.0,
    ),
    (
        (
            "PyTorch",
            "TensorFlow",
            "LLMs",
            "Machine learning",
            "Deep learning",
            "NLP",
            "Computer vision",
            "Hugging Face",
            "CUDA",
            "MLOps",
            "scikit-learn",
        ),
        "ml",
        1.2,
    ),
    (
        (
            "Verilog",
            "SystemVerilog",
            "VHDL",
            "FPGA",
            "UVM",
            "RTL design",
            "PCB design",
            "Embedded systems",
            "RTOS",
            "C",
            "CUDA",
        ),
        "hardware",
        1.2,
    ),
    (("Security", "Penetration testing", "Networking"), "security", 1.2),
    (("Python", "C++"), "sde", 0.6),
    (("Python",), "data", 0.4),
    (("Python",), "ml", 0.4),
    (("C++",), "hardware", 0.3),
]:
    for _skill in _skills:
        _SKILL_ROLES.setdefault(_skill, {})[_role] = _weight

_TITLE_LINE = re.compile(
    r"\b(engineer|developer|analyst|scientist|intern|co-?op|researcher|architect|programmer)\b", re.I
)


def role_affinity(text: str, skills: list[str]) -> dict[str, float]:
    """Share of evidence for each tech role type, summing to 1."""
    scores = dict.fromkeys(TECH_ROLE_TYPES, 0.0)
    for skill in skills:
        for role, weight in _SKILL_ROLES.get(skill, {}).items():
            scores[role] += weight
    for line in text.splitlines():  # job titles are strong evidence
        if len(line) <= 90 and _TITLE_LINE.search(line):
            role = classify_role(line)
            if role in scores:
                scores[role] += 3.0
    total = sum(scores.values())
    if total == 0:
        return {role: round(1 / len(scores), 3) for role in scores}
    return {role: round(value / total, 3) for role, value in scores.items()}


# ---------- contact ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.I)
_GITHUB = re.compile(r"github\.com/[\w-]+", re.I)
_URL = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:dev|io|me|xyz|app|site|page|tech)\b(?:/\S*)?", re.I)

_STOP = set(
    """a an and are as at be by for from has have in is it of on or that the to with will your you our we
    this their they them using use used new role team work working including across within into via per""".split()
)


def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z+#.]{2,}", text.lower())
    return sorted({w.strip(".") for w in words if w not in _STOP})[:2000]


def phrases(text: str) -> list[str]:
    """Stemmed two-word phrases, line by line, for matching a posting's key terms."""
    from tracker.resume.posting import _tokens, stem

    found = set()
    for line in text.splitlines():
        words = [stem(w) for w in _tokens(line)]
        found.update(
            f"{a} {b}" for a, b in zip(words, words[1:], strict=False) if a not in _STOP and b not in _STOP
        )
    return sorted(found)[:4000]


def skill_evidence(sections: dict[str, str], skills: list[str]) -> dict[str, str]:
    """Where each skill shows up: "work" (experience or leadership bullets),
    "project", or "listed" (only a skills list or elsewhere). Skills used in
    real work count for more than skills that are only named."""
    work = "\n".join(sections.get(k, "") for k in ("experience", "leadership"))
    projects = sections.get("projects", "")
    in_work, in_projects = set(extract_skills(work)), set(extract_skills(projects))
    return {s: "work" if s in in_work else "project" if s in in_projects else "listed" for s in skills}


# ---------- the profile ----------


@dataclass
class Profile:
    skills: list[str]
    level: str  # student | new_grad | experienced | senior
    target_levels: list[str]  # job levels this resume fits, best first
    months_experience: int
    education: dict
    roles: dict[str, float]
    top_role: str
    contact: dict[str, bool]
    sections: list[str]
    bullet_count: int
    quantified_bullets: int
    weak_bullets: list[str]
    unquantified_examples: list[str]
    long_bullets: int
    word_count: int
    keywords: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    skill_evidence: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_LEVEL_TARGETS = {
    "student": ["intern", "new_grad"],
    "new_grad": ["new_grad", "intern", "mid"],
    "experienced": ["mid", "new_grad", "senior"],
    "senior": ["senior", "mid"],
}


def estimate_level(months: int, education: dict, today: date) -> str:
    if education["still_studying"]:
        return "student"
    grad = education["graduation"]
    years_since = None
    if grad:
        year, month = (int(x) for x in grad.split("-"))
        years_since = (today.year - year) + (today.month - month) / 12
    if months >= 72:
        return "senior"
    if months >= 24 and (years_since is None or years_since >= 1.5):
        return "experienced"
    return "new_grad"


def build_profile(text: str, today: date | None = None) -> Profile:
    today = today or date.today()
    sections = split_sections(text)
    education = education_summary(sections.get("education", ""), today)
    # experience comes from the experience section when there is one, so
    # school dates don't count as work
    work_text = "\n".join(sections[k] for k in ("experience", "leadership") if k in sections)
    if not work_text:
        work_text = "\n".join(
            line
            for line in text.splitlines()
            if not re.search(r"universit|college|school|bachelor|b\.?sc|expected", line, re.I)
        )
    months = months_of_experience(date_ranges(work_text, today))
    skills = extract_skills(text)
    roles = role_affinity(text, skills)
    level = estimate_level(months, education, today)
    found_bullets = bullets(
        "\n".join(sections.get(k, "") for k in ("experience", "projects", "leadership")) or text
    )
    quantified = [b for b in found_bullets if _NUMBER.search(b)]
    return Profile(
        skills=skills,
        level=level,
        target_levels=_LEVEL_TARGETS[level],
        months_experience=months,
        education=education,
        roles=roles,
        top_role=max(roles, key=roles.get),
        contact={
            "email": bool(_EMAIL.search(text)),
            "phone": bool(_PHONE.search(text)),
            "linkedin": bool(_LINKEDIN.search(text)),
            "github": bool(_GITHUB.search(text)),
            "website": bool(_URL.search(_EMAIL.sub("", _LINKEDIN.sub("", _GITHUB.sub("", text))))),
        },
        sections=sorted(k for k in sections if k != "header"),
        bullet_count=len(found_bullets),
        quantified_bullets=len(quantified),
        weak_bullets=[b for b in found_bullets if _WEAK_OPENERS.match(b)][:5],
        unquantified_examples=[b for b in found_bullets if not _NUMBER.search(b)][:3],
        long_bullets=sum(1 for b in found_bullets if len(b.split()) > 35),
        word_count=len(text.split()),
        keywords=keywords(text),
        phrases=phrases(text),
        skill_evidence=skill_evidence(sections, skills),
    )
