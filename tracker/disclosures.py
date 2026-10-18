"""Extract pay and hiring disclosures from posting text.

Since January 1, 2026, Ontario employers with 25+ employees must state in
public job postings:
  * the expected pay or a pay range (at most $50,000 wide)
  * whether the posting is for an existing vacancy
  * whether AI is used to screen, assess or select applicants

Other jurisdictions (several US states, BC, PEI) also require pay ranges.
These parsers turn that text into structured fields. Each returns None when
the posting says nothing, so "not disclosed" is never confused with "no".
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# ---------- Salary ----------

_NUMBER = r"\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CURRENCY = r"CAD|USD|C\$|CA\$|US\$|\$"
_SALARY = re.compile(
    rf"(?P<cur1>{_CURRENCY})\s?(?P<min>{_NUMBER})\s?(?P<k1>[kK]\b)?"
    rf"\s*(?:-|–|—|to|and)\s*"
    rf"(?P<cur2>{_CURRENCY})?\s?(?P<max>{_NUMBER})\s?(?P<k2>[kK]\b)?"
    r"(?=(?P<after>.{0,60}))",  # lookahead: never consume text a later match needs
    re.S,
)
_HOURLY = re.compile(r"\b(?:per\s+hour|an\s+hour|/\s*h(?:ou)?r|hourly)\b", re.I)
_YEARLY = re.compile(r"\b(?:per\s+year|a\s+year|/\s*y(?:ea)?r|annual(?:ly)?|per\s+annum|salary)\b", re.I)
_SCALE_WORDS = re.compile(r"^\s*(?:million|billion|m\b|bn\b)", re.I)


@dataclass(frozen=True)
class Salary:
    minimum: float
    maximum: float
    period: str  # "year" | "hour"
    currency: str | None  # "CAD" | "USD" | None when not stated
    text: str = field(default="", compare=False)  # the sentence it came from


def _to_number(raw: str, thousands: bool) -> float:
    value = float(re.sub(r"[,\s]", "", raw))
    return value * 1000 if thousands else value


def _currency(*tokens: str | None) -> str | None:
    for token in tokens:
        if not token:
            continue
        upper = token.upper()
        if upper in ("CAD", "C$", "CA$"):
            return "CAD"
        if upper in ("USD", "US$"):
            return "USD"
    return None


def _plausible(low: float, high: float, period: str) -> bool:
    if low > high or high > 3 * low:
        return False
    if period == "hour":
        return 10 <= low and high <= 500
    return 15_000 <= low and high <= 1_000_000


def parse_salary(text: str) -> Salary | None:
    """Return the first plausible pay range in the text."""
    if not text:
        return None
    for match in _SALARY.finditer(text):
        after = match["after"]
        if _SCALE_WORDS.match(after):
            continue  # "$5 to $10 billion" is not a salary
        low = _to_number(match["min"], bool(match["k1"] or match["k2"]))
        high = _to_number(match["max"], bool(match["k2"] or match["k1"]))
        context = text[max(0, match.start() - 40) : match.start()] + after
        if _HOURLY.search(after) or (_HOURLY.search(context) and not _YEARLY.search(after)):
            period = "hour"
        elif _YEARLY.search(context) or high >= 1000:
            period = "year"
        else:
            period = "hour"
        if not _plausible(low, high, period):
            continue
        currency_after = re.match(r"\s*\(?\s*(CAD|USD)\b", after, re.I)
        currency = _currency(match["cur1"], match["cur2"], currency_after and currency_after.group(1))
        return Salary(low, high, period, currency, _around(text, match.start(), match.end("max")))
    return None


def _around(text: str, start: int, end: int) -> str:
    """The sentence containing text[start:end]."""
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return _trim(text[left + 1 : right])


# ---------- Existing vacancy ----------
#
# Only explicit statements about THIS posting count. Phrases such as "future
# hiring needs" or "talent pipeline" also appear in ordinary job duties (a
# recruiter "builds pipelines for current and future hiring needs"), and
# "future opportunities" appears in privacy notices, so those alone never
# mark a posting as not a real opening.

_SUBJECT = r"(?:this|the)\s+(?:job\s+)?(?:posting|position|role|requisition|opportunity|opening|advertisement|ad|vacancy)"
_NOT_EXISTING = re.compile(
    r"\b(?:not|isn['’]t|is\s+not)\s+(?:for\s+|to\s+fill\s+)?an?\s+(?:current(?:ly)?\s+)?existing\s+(?:vacancy|position|role|opening)"
    r"|\bexisting\s+vacancy\s*[:?]\s*no\b"
    rf"|\b{_SUBJECT}\s+(?:is|will\s+be\s+used|serves|is\s+being\s+used)\b[^.\n]{{0,60}}?"
    r"\b(?:future|anticipated|upcoming|potential)\s+(?:vacanc|opening|need|position|role|opportunit|hiring)"
    rf"|\b{_SUBJECT}\s+is\s+(?:an?\s+)?(?:evergreen|pipeline|pooled|talent[\s-]+pool|talent[\s-]+community|general\s+application)\b"
    r"|\b(?:evergreen|pipeline|pooled)\s+(?:requisition|job\s+posting|posting)\b"
    r"|\btalent[\s-]+(?:pool|community)\s+(?:posting|requisition)\b"
    r"|\bthere\s+is\s+(?:currently\s+)?no\s+(?:existing\s+|current\s+)?vacancy\b"
    r"|\b(?:accepting|collecting)\s+applications\s+for\s+(?:future|upcoming|anticipated)\s+"
    r"(?:vacanc|opening|opportunit|position|role)",
    re.I,
)
_EXISTING = re.compile(
    r"\b(?:is|for|fill(?:s|ing)?|represents|this\s+is)\s+an?\s+(?:current(?:ly)?\s+)?existing\s+(?:vacancy|position|role|opening)"
    r"|\bexisting\s+vacancy\s*[:?]\s*yes\b",
    re.I,
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


def vacancy_evidence(text: str) -> tuple[str | None, str | None]:
    """The vacancy status and the sentence that states it.

    Returns ('existing' | 'not_existing' | None, sentence | None).
    """
    if not text:
        return None, None
    for pattern, status in ((_NOT_EXISTING, "not_existing"), (_EXISTING, "existing")):
        for sentence in _SENTENCES.split(text):
            if pattern.search(sentence):
                return status, _trim(sentence)
    return None, None


def parse_vacancy(text: str) -> str | None:
    """'existing', 'not_existing', or None when the posting does not say."""
    return vacancy_evidence(text)[0]


def _trim(sentence: str, limit: int = 300) -> str:
    sentence = " ".join(sentence.split()).lstrip("•-* ")
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rsplit(" ", 1)[0] + "…"


# ---------- AI screening ----------

_AI = re.compile(r"\b(?:(?i:artificial\s+intelligence)|AI|A\.I\.)\b")
_HIRING = re.compile(r"\b(?:applica|candidat|hiring|recruit|selection|screening)", re.I)
_SCREEN_VERB = re.compile(r"\b(?:screen|assess|select|evaluat|review|rank|shortlist|sort)", re.I)
_NEGATION = re.compile(
    r"\b(?:do(?:es)?\s+not|don['’]t|doesn['’]t|will\s+not|won['’]t|is\s+not|are\s+not|isn['’]t|aren['’]t|never|no)\b",
    re.I,
)


def ai_screening_evidence(text: str) -> tuple[bool | None, str | None]:
    """(uses_ai, sentence): True if the posting says AI is used to screen
    applicants, False if it says AI is not used, None if it says nothing."""
    if not text:
        return None, None
    for sentence in _SENTENCES.split(text):
        if _AI.search(sentence) and _HIRING.search(sentence) and _SCREEN_VERB.search(sentence):
            return not _NEGATION.search(sentence), _trim(sentence)
    return None, None


def parse_ai_screening(text: str) -> bool | None:
    return ai_screening_evidence(text)[0]


# ---------- Repost fingerprint ----------

_REQ_ID = re.compile(r"\b(?:req(?:uisition)?\s*#?\s*|jr|r|#)\s*-?\d{3,}\b", re.I)
_NON_WORD = re.compile(r"[^a-z0-9]+")


_DATES = re.compile(
    r"\b(?:posted|updated|closing|deadline|apply by)\b[^.]{0,40}"  # date lines change on repost
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)
DESCRIPTION_CHARS = 2000


def _words(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def fingerprint(title: str, location: str = "", description: str = "") -> str:
    """Identity of a role independent of its posting id.

    Two postings at the same company with the same fingerprint are the same
    role, so one closing and another appearing is a repost. The description
    is part of the identity, because large employers post many different
    roles under identical titles; requisition ids and dates are removed so a
    plain repost still matches. Every location counts, so the same role in
    two cities is two roles. Without a description, title and location alone
    are used, and such a fingerprint is too weak to call two open postings
    duplicates (see has_description_hash).
    """
    clean_title = _words(_REQ_ID.sub(" ", title))
    clean_location = ",".join(sorted({_words(part) for part in location.split("|") if _words(part)}))
    key = f"{clean_title}|{clean_location}"
    if description:
        body = _words(_REQ_ID.sub(" ", _DATES.sub(" ", description)))[:DESCRIPTION_CHARS]
        key += "|" + hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    return key


_HASHED = re.compile(r"\|[0-9a-f]{12}$")


def has_description_hash(value: str) -> bool:
    return bool(_HASHED.search(value))
