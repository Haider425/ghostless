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

from tracker import currency

# ---------- Salary ----------
#
# Pay is written many ways: "$95K-$120K", "CAD $40 - CAD $45 per hour",
# "224,000 USD - 300,000 USD", "£39,000-£43,000 per year", "€111.800",
# a bare "34 - 68, $ per hour" under a "Base Pay Range (USD)" heading, a
# range in words ("between USD 142,500 in the lowest market and USD 228,000
# in the highest"), or a single "Salary: £34k". Each pattern finds candidates,
# ranked: a written range ($X - $Y) first, then a range in words, then a lone
# amount, and within a rank the first plausible one in the text. Ranges with
# no currency symbol, and lone amounts, only count right after a pay word, so
# "200 - 300 engineers" or "a $5 gift card" never become a salary.

# 1,234,567 · 30,00,000 (Indian lakhs) · 120 000 · 111.800 (European thousands: three digits after each dot) · 25.50
_NUMBER = r"\d{1,2}(?:,\d{2})+,\d{3}(?![\d,])|\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?(?![\d,])|\d+(?:\.\d+)?"
# ISO codes Ghostless knows (tracker/currency.py), except those that are also words
# in postings ("PHP" the language, "try", "Ron", French "ils", "CRC" checks): those
# count only from a source's own pay field or their sign (₱, ₺, ₪)
_CODE_IS_A_WORD = {"PHP", "TRY", "RON", "ILS", "PEN", "ARS", "SAR", "COP", "CRC"}
_CODE = "|".join(code for code in currency.TO_USD if code not in _CODE_IS_A_WORD)
_SYMBOL = r"(?:C|CA|US|AU?|SG?|HK|NZ|R|MX)?\$|£|€|₹|₩|₱|₪|₺"
# a symbol (optionally after a code: "CAD $40"), or a code on its own ("CAD 80,000")
_CURRENCY = rf"(?:(?:{_CODE})\s?)?(?:{_SYMBOL})|\b(?:{_CODE})\b"
_TO = r"\s*(?:-|–|—|to|and|à)\s*"
_K = r"\s?(?P<{}>[kK]\b)?"
_UNIT = r"(?:\s?/\s?(?:hr|hour|yr|year))?"  # "$33/hour to $40/hour"
_AFTER = r"(?=(?P<after>.{0,60}))"  # lookahead: never consume text a later match needs

_SALARY = re.compile(  # $90,000 - $110,000 · CAD $40 - CAD $45 · £39k to £43k
    rf"(?P<cur1>{_CURRENCY})\s?(?P<min>{_NUMBER}){_K.format('k1')}{_UNIT}(?:\s?\(?(?P<code1>{_CODE})\)?)?{_TO}"
    rf"(?P<cur2>{_CURRENCY})?\s?(?P<max>{_NUMBER}){_K.format('k2')}{_AFTER}",
    re.S,
)
_SALARY_CODE_AFTER = re.compile(  # 224,000 USD - 300,000 USD
    rf"(?<![\d.,])(?P<min>{_NUMBER}){_K.format('k1')}\s?(?:(?P<cur1>{_CODE})\b)?{_TO}"
    rf"(?P<max>{_NUMBER}){_K.format('k2')}\s?(?P<cur2>{_CODE})\b{_AFTER}",
    re.S,
)
_PAY_WORDS = r"salary|salaries|pay|paid|wages?|compensation|stipend|hourly\s+rate|rate\s+of\s+pay|offering"
_SALARY_BARE = re.compile(  # Base Pay Range (USD)\n\n34 - 68, $ per hour
    rf"(?<![\d.,$£€])(?P<min>{_NUMBER}){_K.format('k1')}{_TO}(?P<max>{_NUMBER}){_K.format('k2')}{_AFTER}",
    re.S,
)
_PAY_BEFORE = re.compile(rf"\b(?:{_PAY_WORDS})\b", re.I)
# one amount that says its own currency code and period, with no pay word needed:
# "Toronto, ON, CAN - 50,405.00 CAD Annually", "$7,000 CAD per month", "Canada: $120000 (CAD)"
_SALARY_STATED = re.compile(
    rf"(?:(?:(?P<cur1>{_SYMBOL})\s?(?P<min>{_NUMBER})\s?\(?(?P<code1>{_CODE})?\)?"
    rf"|(?<![\d.,$£€])(?P<min2>{_NUMBER})\s?(?P<code2>{_CODE})\b)"
    r"(?=\s*(?:annually|per\s+(?:year|annum|hour|month)|a\s+(?:year|month)|hourly|monthly"
    r"|/\s*(?:hour|hr|month|mo|year|yr)\b))"
    rf"|(?P<cur3>{_SYMBOL})\s?(?P<min3>{_NUMBER})\s?\((?P<code3>{_CODE})\)){_AFTER}",
    re.I,
)
_MONTHLY = re.compile(r"(?:\bper\s+month|\ba\s+month|/\s*mo(?:nth)?|\bmonthly)\b", re.I)
_SALARY_SINGLE = re.compile(  # Salary: £34k · Pay rate: 19.50 USD/hour
    rf"\b(?:{_PAY_WORDS})\b[^\n\d$£€]{{0,30}}?"
    rf"(?:(?P<cur1>{_CURRENCY})\s?(?P<min>{_NUMBER}){_K.format('k1')}"
    rf"|(?P<min2>{_NUMBER}){_K.format('k2')}\s?(?P<cur2>{_CODE})\b){_AFTER}",
    re.I | re.S,
)
_SALARY_SPAN = re.compile(  # between USD 168,750 in the lowest market and USD 270,000 in the highest
    rf"\b(?:between|from|starts?\s+at|starting\s+at)\s+(?P<cur1>{_CURRENCY})\s?(?P<min>{_NUMBER}){_K.format('k1')}"
    rf"[^.\n$£€\d]{{0,60}}?\b(?:and|to|up\s+to)\s+(?P<cur2>{_CURRENCY})\s?(?P<max>{_NUMBER}){_K.format('k2')}{_AFTER}",
    re.I | re.S,
)
_RANGE_NEXT = re.compile(rf"^{_TO}(?:{_CURRENCY})?\s?\d")
# a single amount that is a ceiling ("up to $18/hr per task") or isn't base pay at all
_CEILING_BEFORE = re.compile(r"(?:\bup\s*to(?:\s+of)?|\bmaximum(?:\s+of)?|\bmax\.?)\s*$", re.I)
_NOT_PAY = re.compile(
    r"\b(?:bonus|sign(?:ing|-on)|relocation|stipend|allowance|reimburse\w*|credit|gift|referral|equity|stock)\b",
    re.I,
)
# \b only before words: the "after" text often starts at "/hour", where no word boundary exists
_HOURLY = re.compile(r"(?:\bper\s+hour|\ban\s+hour|/\s*(?:per\s+)?h(?:ou)?r|\bhourly)\b", re.I)
_YEARLY = re.compile(
    r"(?:\bper\s+year|\ba\s+year|/\s*y(?:ea)?r|\bannual(?:ly)?|\bper\s+annum|\bsalary)\b", re.I
)
_SCALE_WORDS = re.compile(r"^\s*(?:million|billion|m\b|bn\b)", re.I)
_CODE_NEARBY = re.compile(rf"^[^.\n]{{0,20}}?\(?\b({_CODE})\b", re.I)
_SPLIT_THOUSANDS = re.compile(r"(\d) ,(\d{3})\b")  # "$202 ,400" as some sites render it


@dataclass(frozen=True)
class Salary:
    minimum: float
    maximum: float
    period: str  # "year" | "month" | "hour"
    currency: str | None  # an ISO code (tracker/currency.py), None when not stated
    text: str = field(default="", compare=False)  # the sentence it came from


def _to_number(raw: str, thousands: bool) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", raw):  # 111.800 or 43.600,00: European
        raw = raw.replace(".", "").replace(",", ".")
    value = float(re.sub(r"[,\s]", "", raw))
    return value * 1000 if thousands else value


# a dollar sign with its country: S$ Singapore, HK$ Hong Kong, NZ$ New Zealand, R$ Brazil
_DOLLARS = {"C$": "CAD", "CA$": "CAD", "US$": "USD", "A$": "AUD", "AU$": "AUD", "S$": "SGD",
            "SG$": "SGD", "HK$": "HKD", "NZ$": "NZD", "R$": "BRL", "MX$": "MXN"}  # fmt: skip
_SIGNS = {"£": "GBP", "€": "EUR", "₹": "INR", "₩": "KRW", "₱": "PHP", "₪": "ILS", "₺": "TRY"}


def _currency(*tokens: str | None) -> str | None:
    for token in tokens:
        if not token:
            continue
        upper = token.upper().replace(" ", "")
        if upper[:3] in currency.TO_USD:
            return upper[:3]
        for sign, code in (*_DOLLARS.items(), *_SIGNS.items()):
            if upper.startswith(sign):
                return code
    return None


# Dollars, pounds and euros (and pay with no currency) are judged in their own
# units, with the bounds the text parser was built and measured with. Other
# currencies are converted to US dollars and get lower floors, since a junior's
# pay in zloty or rupees is lower than anywhere those bounds were set for.
_OWN_UNITS = (None, "USD", "CAD", "AUD", "GBP", "EUR")
_FLOORS = {"hour": 7.25, "month": 1_000, "year": 15_000}  # an hour: the US federal minimum wage
_FLOORS_CONVERTED = {"hour": 7, "month": 700, "year": 10_000}
_CEILINGS = {"hour": 500, "month": 50_000, "year": 1_000_000}


def _in_bounds(low: float, high: float, period: str, code: str | None = None) -> bool:
    """Amounts a tech posting can pay per hour, month or year."""
    floors = _FLOORS
    if code not in _OWN_UNITS:
        low, high, floors = currency.to_usd(low, code), currency.to_usd(high, code), _FLOORS_CONVERTED
    return floors[period] <= low and high <= _CEILINGS[period]


def _plausible(low: float, high: float, period: str, code: str | None = None) -> bool:
    return low <= high <= 3 * low and _in_bounds(low, high, period, code)


def checked_pay(
    low: float, high: float, period: str | None, code: str | None, country: str | None
) -> tuple[float, float, str, str | None] | None:
    """Pay as it will be shown (min, max, period, currency), or None when it can't
    be trusted. Job boards' own pay fields come here unchecked, and employers
    mistype them:

    - no currency named: the posting country's own (rupees in India, zloty in
      Poland). When the country is unknown too, the currency stays unknown (None):
      the amounts are judged like dollars here but never shown as dollars
    - "$200 - $400,000" a year: the low end lost its "k"
    - a period the amounts can't be ($200,000 an hour, $21 a year): the period
      the amounts fit, trying hour, month, then year. In US and Canadian
      dollars a month only from about US$4,000: below that it may as well be an
      intern's week ("$1,925 per week"), so nothing is shown
    - over about US$1M a year (grants), a low end under a fifth of the high end
      (a dropped digit), or a currency Ghostless doesn't know: nothing is shown
    """
    low, high = float(low), float(high)
    code = code or currency.of_country(country)
    if code is None and country and country not in ("US", "CA"):
        return None  # a country with a currency Ghostless doesn't know
    if code is not None and not currency.known(code):
        return None
    if period == "year" and low < 1000 <= high and low * 1000 <= high:
        low *= 1000
    if low <= 0 or high < low or high > 5 * low:
        return None
    if period not in ("hour", "month", "year") or not _in_bounds(low, high, period, code):
        fits = [p for p in ("hour", "month", "year") if _in_bounds(low, high, p, code)]
        weekly_risk = code in (None, "USD", "CAD")  # intern stipends stated per week
        period = next(
            (p for p in fits if p != "month" or not weekly_risk or currency.to_usd(low, code) >= 4_000), None
        )
    return (low, high, period, code) if period else None


def _period(text: str, start: int, after: str, high: float) -> str:
    context = text[max(0, start - 40) : start] + after
    if _HOURLY.search(after) or (_HOURLY.search(context) and not _YEARLY.search(after)):
        return "hour"
    if _MONTHLY.search(after) or (_MONTHLY.search(context) and not _YEARLY.search(after)):
        return "month"
    if _YEARLY.search(context) or high >= 1000:
        return "year"
    return "hour"


def _candidates(text: str):
    """(start, end, low, high, currency tokens, after, explicit_period) for every pattern."""
    for m in _SALARY.finditer(text):
        k = bool(m["k1"] or m["k2"])
        yield (
            m.start(),
            m.end("max"),
            _to_number(m["min"], k),
            _to_number(m["max"], k),
            (m["cur1"], m["code1"], m["cur2"]),
            m["after"],
            False,
        )
    for m in _SALARY_CODE_AFTER.finditer(text):
        k = bool(m["k1"] or m["k2"])
        yield (
            m.start(),
            m.end("max"),
            _to_number(m["min"], k),
            _to_number(m["max"], k),
            (m["cur2"], m["cur1"]),
            m["after"],
            False,
        )
    for m in _SALARY_BARE.finditer(text):
        before = text[max(0, m.start() - 80) : m.start()]
        currency_before = re.search(rf"\b({_CODE})\b|[$£€]", before)
        # a bare range must sit under a pay word, and say its currency or its period
        if not _PAY_BEFORE.search(before) or not (
            currency_before or _HOURLY.search(m["after"]) or _YEARLY.search(m["after"])
        ):
            continue
        k = bool(m["k1"] or m["k2"])
        code = currency_before.group(1) if currency_before and currency_before.group(1) else None
        yield (
            m.start(),
            m.end("max"),
            _to_number(m["min"], k),
            _to_number(m["max"], k),
            (code,),
            m["after"],
            True,
        )


def _ranges_in_words(text: str):
    """Candidates for a range written as a sentence, in the same shape as _candidates."""
    for m in _SALARY_SPAN.finditer(text):
        k = bool(m["k1"] or m["k2"])
        yield (
            m.start(),
            m.end("max"),
            _to_number(m["min"], k),
            _to_number(m["max"], k),
            (m["cur1"], m["cur2"]),
            m["after"],
            False,
        )


def _single_amounts(text: str):
    """Candidates for one stated amount, in the same shape as _candidates."""
    for m in _SALARY_SINGLE.finditer(text):
        if _RANGE_NEXT.match(m["after"]):
            continue  # "Salary $90,000 - $110,000" is a range, found above
        raw, k, cur = (m["min"], m["k1"], m["cur1"]) if m["min"] else (m["min2"], m["k2"], m["cur2"])
        start = m.start("cur1") if m["min"] else m.start("min2")
        lead = text[m.start() : start]
        # "$20,000 signing bonus" is not pay; "£34k + discretionary 10% bonus" is
        if _CEILING_BEFORE.search(lead) or _NOT_PAY.search(lead) or _NOT_PAY.search(m["after"][:15]):
            continue
        value = _to_number(raw, bool(k))
        yield start, m.end("after") - len(m["after"]), value, value, (cur,), m["after"], False
    for m in _SALARY_STATED.finditer(text):
        if m["min"]:
            raw, tokens, start = m["min"], (m["code1"], m["cur1"]), m.start("cur1")
        elif m["min2"]:
            raw, tokens, start = m["min2"], (m["code2"],), m.start("min2")
        else:
            raw, tokens, start = m["min3"], (m["code3"], m["cur3"]), m.start("cur3")
        lead = text[max(0, start - 30) : start]
        if _RANGE_NEXT.match(m["after"]) or _NOT_PAY.search(m["after"][:15]) or _CEILING_BEFORE.search(lead):
            continue
        value = _to_number(raw, False)
        yield start, m.end("after") - len(m["after"]), value, value, tokens, m["after"], False


# where a posting gives pay per country, the words that mark each country's range
_COUNTRY_WORDS = {
    "CA": re.compile(r"\b(?:canada|canadian|can|ontario|quebec|british columbia|alberta)\b", re.I),
    "US": re.compile(r"\b(?:us|usa|u\.s\.|united states|america)\b", re.I),
    "GB": re.compile(r"\b(?:uk|united kingdom|london)\b", re.I),
}
_COUNTRY_CURRENCY = {"CA": "CAD", "US": "USD", "GB": "GBP"}


def parse_salary(text: str, country: str | None = None) -> Salary | None:
    """Return the first plausible written pay range in the text; failing that a
    range in words; failing that a stated amount. A labelled "$X - $Y" is the
    most specific statement, so it beats "between $X in the lowest market...".

    With `country` (the posting's own, ISO code), a posting that gives a range
    per country ("US: $147,000 - $210,000 ... Canada: $150,000 - $153,000 CAD")
    gives that country's range."""
    if not text:
        return None
    text = _SPLIT_THOUSANDS.sub(r"\1,\2", text)
    ranked = [
        *((0, *c) for c in _candidates(text)),
        *((1, *c) for c in _ranges_in_words(text)),
        *((2, *c) for c in _single_amounts(text)),
    ]
    found: list[tuple[int, Salary, int]] = []
    for rank, start, end, low, high, tokens, after, bare in sorted(ranked, key=lambda c: (c[0], c[1])):
        if _SCALE_WORDS.match(after):
            continue  # "$5 to $10 billion" is not a salary
        period = _period(text, start, after, high)
        if bare and period == "hour" and not _HOURLY.search(after):
            continue  # a bare small range is only pay when it says "per hour"
        code_after = _CODE_NEARBY.match(after)
        code = _currency(*tokens, code_after and code_after.group(1))
        if code is None and country not in (None, "US", "CA") and any(t and t.strip() == "$" for t in tokens):
            code = currency.DOLLAR_COUNTRIES.get(country, "USD")  # "$" in London is the US dollar
        if not _plausible(low, high, period, code or currency.of_country(country)):
            continue
        found.append((rank, Salary(low, high, period, code, _around(text, start, end)), start))
    if not found:
        return None
    first_rank, first, _ = found[0]
    want = _COUNTRY_CURRENCY.get(country or "")
    if want and first.currency != want and len(found) > 1:
        same_rank = [(salary, start) for rank, salary, start in found if rank == first_rank]
        for salary, _ in same_rank:
            if salary.currency == want:
                return salary
        for salary, start in same_rank:
            if salary.currency is None and _COUNTRY_WORDS[country].search(text[max(0, start - 70) : start]):
                return salary
    return first


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
