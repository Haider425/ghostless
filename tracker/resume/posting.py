"""What a posting asks for, read from its description.

Postings are split into parts by their headings: requirements ("What you'll
bring", "Basic qualifications", ...), nice-to-haves ("Preferred", "Bonus"),
duties ("What you'll do") and boilerplate (benefits, company blurb, equal
opportunity statements), which is ignored. From those parts come:

  * required and preferred skills
  * years of experience asked for ("3+ years of experience")
  * degree asked for, and its field ("Bachelor's in Computer Science")
  * whether you must be enrolled in school (internships and co-ops)
  * the posting's key terms: the words and phrases it uses most for the
    work itself ("distributed systems", "payments", "data pipelines")

Descriptions stored before structure was kept are one paragraph; they have no
headings, so everything counts as requirements.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from tracker.skills import extract_skills

_HEADING_KINDS = (
    (
        "skip",
        r"benefit|perk|about (us|the company|the team|[a-z]+)$|who we are|our (mission|values|culture|story)|"
        r"equal (employment|opportunity)|accommodation|compensation|salary|pay (range|transparency|and)|"
        r"what we offer|why (join|work)|diversity|inclusion|privacy|life at|our commitment|application process|how to apply",
    ),
    (
        "preferred",
        r"nice[\s-]to[\s-]have|preferred|bonus|plus|good to have|extra credit|would be great|stand out",
    ),
    (
        "required",
        r"requirement|qualification|what you('|’)?ll (need|bring)|what (we('|’)?re|we are) looking for|"
        r"you (have|bring|are|might be)|must[\s-]have|who you are|about you|skills|experience|what you need|"
        r"we('|’)?d love|you should|ideal candidate|minimum|basic",
    ),
    (
        "duties",
        r"responsibilit|what you('|’)?ll (do|work on|be doing)|the role|your role|day[\s-]to[\s-]day|in this role|"
        r"what you will do|the work|your impact|the opportunity|job description|overview",
    ),
)
_HEADING_RE = [(kind, re.compile(pattern, re.I)) for kind, pattern in _HEADING_KINDS]
_BULLET = re.compile(r"^\s*[•\-*–]\s*")


def _heading_kind(line: str) -> str | None:
    text = line.strip().rstrip(":").strip()
    if not text or len(text) > 70 or _BULLET.match(line) or text.endswith((".", "!", "?", ";", ",")):
        return None
    if len(text.split()) > 10:
        return None
    for kind, pattern in _HEADING_RE:
        if pattern.search(text):
            return kind
    return None


def split_posting(description: str) -> dict[str, str]:
    """{kind: text} for kinds general, required, preferred, duties, skip."""
    parts: dict[str, list[str]] = {"general": []}
    kind = "general"
    for line in description.splitlines():
        found = _heading_kind(line)
        if found:
            kind = found
            continue
        # an inline "Preferred qualifications: ..." line
        if re.match(r"^\s*(preferred|nice[\s-]to[\s-]have|bonus)\b[^:]{0,40}:", line, re.I):
            parts.setdefault("preferred", []).append(line)
            continue
        parts.setdefault(kind, []).append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items() if "\n".join(v).strip()}


# ---------- years and degrees ----------

_YEARS = re.compile(
    r"(?P<min>\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*(?P<max>\d{1,2})\s*\+?\s*)?(?:years?|yrs?)\b(?P<after>[^.\n]{0,60})",
    re.I,
)
_DEGREE = (
    ("phd", r"ph\.?\s?d|doctorate|doctoral"),
    ("master", r"master'?s|m\.?\s?sc?\b|m\.?eng|mba"),
    (
        "bachelor",
        r"bachelor'?s|b\.?\s?sc?\b|b\.?eng|b\.?a\.?\b|undergraduate degree|university degree|4-year degree",
    ),
)
DEGREE_RANK = {"bachelor": 1, "master": 2, "phd": 3}
_FIELDS = (
    "computer science",
    "computer engineering",
    "software engineering",
    "electrical engineering",
    "engineering",
    "mathematics",
    "statistics",
    "data science",
    "physics",
    "information technology",
    "information systems",
)
_ENROLLED = re.compile(
    r"currently (enrolled|pursuing|studying)|returning to (school|university|your studies)|"
    r"enrolled (in|at) (a |an )?(university|college|bachelor|master|degree|post-?secondary)|"
    r"pursuing (a |an )?(bachelor|master|ph\.?d|degree|undergraduate)|co-?op program|"
    r"graduating (in|between|by|before)|expected graduation",
    re.I,
)


def years_required(text: str) -> float | None:
    """The smallest "N+ years of experience" the posting asks for (ignoring company ages and the like)."""
    found = []
    for m in _YEARS.finditer(text):
        after = m["after"].lower()
        context = text[max(0, m.start() - 40) : m.start()].lower()
        if "experience" not in after and "experience" not in context:
            continue
        if re.search(r"\b(old|ago|history|company|founded|in business)\b", after):
            continue
        value = int(m["min"])
        if 0 < value <= 20:
            found.append(value)
    return float(min(found)) if found else None


def degree_required(text: str) -> tuple[str | None, list[str], bool]:
    """(lowest degree asked for, fields, whether equivalent experience is accepted)."""
    degree = None
    for name, pattern in sorted(_DEGREE, key=lambda d: DEGREE_RANK[d[0]]):
        if re.search(rf"\b(?:{pattern})", text, re.I):
            degree = name
            break
    lower = text.lower()
    fields = [f for f in _FIELDS if f in lower]
    # "engineering" alone only when no specific engineering field matched
    if any(f.endswith(" engineering") for f in fields):
        fields = [f for f in fields if f != "engineering"]
    equivalent = bool(
        re.search(r"or equivalent|equivalent (practical |work )?experience|or related experience", lower)
    )
    return degree, fields[:3], equivalent


# ---------- key terms ----------

_STOP = set(
    """a about above across after again all also an and any are as at be because been before being below between
    both but by can could did do does doing down during each either etc every few for from further had has have
    having he her here hers how i if in into is it its itself just like may me might more most must my need
    needs no nor not now of off on once only or other our ours out over own per please same she should so some
    such than that the their theirs them then there these they this those through to too under until up upon us
    very via was we were what when where which while who whom why will with within without would you your yours
    able ability strong excellent good great new using use used work working works team teams role roles
    company candidate candidates opportunity opportunities including include includes join help helping make
    making build building well across experience experienced years year knowledge understanding skills skill
    familiarity familiar proficiency proficient plus preferred required requirements responsibilities
    qualifications bonus ideal ideally looking passion passionate love want world best one two three day days
    time part full based highly fast paced environment environments related relevant demonstrated proven track
    record solid deep hands effectively effective communication written verbal collaborate collaborative
    collaboration closely partner partners partnering cross functional stakeholders stakeholder ensure support
    supporting drive driving own owning ownership take taking lead leading problems problem solving solve
    impact impactful high quality customers customer users user products product business teammates
    internship intern interns co-op coop students student graduate graduates degree bachelor master phd
    engineer engineers engineering developer developers software senior junior staff level computer science
    field fields equivalent practical related similar such example etc write writing written
    develop developing implement implementing maintain maintaining create creating improve improving
    contribute contributing learn learning grow growing apply review reviewing deliver delivering
    get getting know new things thing way ways lot lots many much really looking seeking""".split()
)
_TOKEN = re.compile(r"[a-z][a-z0-9+#./-]*[a-z0-9+#]|[a-z]")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) >= 3 and not t.isdigit()]


def key_terms(title: str, parts: dict[str, str], skills: set[str], limit: int = 12) -> list[str]:
    """The phrases a posting leans on most, besides named skills.

    Words from the title count three times, requirements and duties twice,
    general text once; boilerplate isn't read. Two-word phrases win over their
    words when they repeat.
    """
    weights = {"required": 2, "duties": 2, "preferred": 1, "general": 1}
    counts: Counter[str] = Counter()
    title_terms: set[str] = set()
    skill_words = {w for s in skills for w in _tokens(s)}

    def keep(word: str) -> bool:
        return word not in _STOP and word not in skill_words

    for kind, weight in [("title", 3)] + list(weights.items()):
        text = title if kind == "title" else parts.get(kind, "")
        for line in text.splitlines():  # phrases never span two bullet points
            words = _tokens(line)
            for i, word in enumerate(words):
                if keep(word):
                    counts[word] += weight
                    if kind == "title":
                        title_terms.add(word)
                if i + 1 < len(words) and keep(word) and keep(words[i + 1]):
                    phrase = f"{word} {words[i + 1]}"
                    counts[phrase] += weight
                    if kind == "title":
                        title_terms.add(phrase)
    # a term must come from the title or appear more than once in the body
    candidates = [t for t, c in counts.most_common(80) if t in title_terms or c >= 4]
    phrases = [t for t in candidates if " " in t]
    picked: list[str] = []
    seen_stems: set[str] = set()
    for term in candidates:
        stems = tuple(stem(w) for w in term.split())
        if len(stems) == 1 and any(stems[0] in (stem(w) for w in p.split()) for p in phrases):
            continue  # "payment" when "payment processing" is there
        if stems in seen_stems:
            continue  # "payments" when "payment" is there
        seen_stems.add(stems)
        picked.append(term)
        if len(picked) >= limit:
            break
    return picked


def stem(word: str) -> str:
    """A light stem for matching: payments/payment, systems/system, testing/test."""
    for suffix in ("ing", "ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


# ---------- the analysis ----------


@dataclass
class Needs:
    required_skills: list[str]
    preferred_skills: list[str]
    years: float | None
    degree: str | None
    degree_fields: list[str]
    degree_flexible: bool
    enrolled: bool
    key_terms: list[str]
    structured: bool  # the description had headings to go by
    empty: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=4096)
def analyze_posting(title: str, description: str) -> Needs:
    description = description or ""
    if len(description.strip()) < 40:
        return Needs([], [], None, None, [], False, False, key_terms(title, {}, set()), False, empty=True)
    parts = split_posting(description)
    structured = any(k in parts for k in ("required", "preferred", "duties"))
    relevant = "\n".join(parts.get(k, "") for k in ("required", "duties", "general"))
    required = extract_skills(
        f"{title}\n{parts.get('required', '')}\n{parts.get('duties', '')}\n{parts.get('general', '')}"
    )
    preferred = [s for s in extract_skills(parts.get("preferred", "")) if s not in required]
    asking = parts.get("required", "") or relevant
    degree, fields, flexible = degree_required(asking)
    return Needs(
        required_skills=required,
        preferred_skills=preferred,
        years=years_required(asking),
        degree=degree,
        degree_fields=fields,
        degree_flexible=flexible,
        enrolled=bool(_ENROLLED.search(description)),
        key_terms=key_terms(title, parts, set(required) | set(preferred)),
        structured=structured,
    )
