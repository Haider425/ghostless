"""Fields read from a posting's text when its source doesn't give them
(crawler plan, stage C2): places and countries, workplace, employment type,
sponsorship, years of experience, and seniority. Heuristics only, with
built-in tables; each returns None (or an empty list) when the posting
doesn't say, so "not stated" is never confused with "no".

Accuracy is measured with `ghostless evaluate` on the labelled postings in
tests/fixtures/labelled.
"""

from __future__ import annotations

import re
import unicodedata

# ---------- places ----------

PROVINCES = {
    "ON": "Ontario", "QC": "Quebec", "BC": "British Columbia", "AB": "Alberta", "MB": "Manitoba",
    "SK": "Saskatchewan", "NS": "Nova Scotia", "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "PE": "Prince Edward Island", "YT": "Yukon", "NT": "Northwest Territories", "NU": "Nunavut",
}  # fmt: skip
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}  # fmt: skip
# country names and codes (ISO 3166 alpha-2 and alpha-3) for the places postings name most
COUNTRIES = {
    "CA": ("canada", "can"), "US": ("united states", "united states of america", "usa", "u.s.", "u.s.a.", "us"),
    "GB": ("united kingdom", "uk", "u.k.", "gbr", "england", "scotland", "wales", "great britain"),
    "IE": ("ireland", "irl"), "FR": ("france", "fra"), "DE": ("germany", "deu", "deutschland"),
    "NL": ("netherlands", "nld"), "ES": ("spain", "esp"), "IT": ("italy", "ita"), "PL": ("poland", "pol"),
    "PT": ("portugal", "prt"), "SE": ("sweden", "swe"), "CH": ("switzerland", "che"), "BE": ("belgium", "bel"),
    "AT": ("austria", "aut"), "DK": ("denmark", "dnk"), "FI": ("finland", "fin"), "NO": ("norway", "nor"),
    "CZ": ("czech republic", "czechia", "cze"), "RO": ("romania", "rou"), "HU": ("hungary", "hun"),
    "IN": ("india", "ind"), "SG": ("singapore", "sgp"), "JP": ("japan", "jpn"), "KR": ("south korea", "korea", "kor"),
    "CN": ("china", "chn"), "TW": ("taiwan", "twn"), "HK": ("hong kong", "hkg"), "PH": ("philippines", "phl"),
    "MY": ("malaysia", "mys"), "ID": ("indonesia", "idn"), "VN": ("vietnam", "vnm"), "TH": ("thailand", "tha"),
    "AU": ("australia", "aus"), "NZ": ("new zealand", "nzl"), "MX": ("mexico", "mex"), "BR": ("brazil", "bra"),
    "AR": ("argentina", "arg"), "CL": ("chile", "chl"), "CO": ("colombia", "col"), "CR": ("costa rica", "cri"),
    "DO": ("dominican republic", "dom"), "IL": ("israel", "isr"), "AE": ("united arab emirates", "uae", "are"),
    "ZA": ("south africa", "zaf"), "EG": ("egypt", "egy"), "NG": ("nigeria", "nga"), "TR": ("turkey", "türkiye", "tur"),
}  # fmt: skip
CITIES = {
    "CA": (
        "toronto", "montreal", "montréal", "vancouver", "calgary", "edmonton", "ottawa", "waterloo", "kitchener",
        "mississauga", "markham", "oakville", "brampton", "burlington", "hamilton", "london, on", "victoria",
        "winnipeg", "halifax", "quebec city", "québec city", "québec", "longueuil", "laval", "bromont", "surrey",
        "burnaby", "richmond, bc", "regina", "saskatoon", "st. john's", "fredericton", "moncton", "guelph",
        "sparwood", "elkford", "georgetown, on", "north york", "scarborough", "etobicoke", "vaughan", "richmond hill",
    ),
    "US": (
        "new york", "nyc", "san francisco", "sf", "bay area", "mountain view", "palo alto", "menlo park",
        "sunnyvale", "san jose", "san mateo", "san carlos", "foster city", "los altos", "redwood city", "oakland",
        "berkeley", "los angeles", "santa monica", "irvine", "costa mesa", "san diego", "seattle", "bellevue",
        "redmond", "portland", "chicago", "boston", "cambridge, ma", "somerville", "austin", "dallas", "houston",
        "plano", "frisco", "fort worth", "san antonio", "denver", "boulder", "phoenix", "atlanta", "miami", "tampa",
        "orlando", "washington, dc", "washington dc", "washington, d.c.", "arlington", "mclean", "reston",
        "herndon", "chantilly", "rosslyn", "philadelphia", "pittsburgh", "baltimore", "detroit", "minneapolis",
        "nashville", "charlotte", "raleigh", "salt lake city", "las vegas", "columbus", "cincinnati", "cleveland",
        "milwaukee", "st. louis", "kansas city", "indianapolis", "richmond, va", "new jersey", "jersey city",
        "brooklyn", "manhattan",
    ),
    "GB": ("london", "manchester", "cheadle", "edinburgh", "glasgow", "bristol", "cambridge, uk", "oxford", "belfast"),
    "IE": ("dublin", "galway", "cork"), "FR": ("paris", "lyon", "saint-etienne", "st. etienne", "grenoble"),
    "DE": ("berlin", "munich", "münchen", "hamburg", "frankfurt", "kassel"), "NL": ("amsterdam", "rotterdam"),
    "PL": ("warsaw", "krakow", "kraków", "wroclaw", "wrocław"), "ES": ("madrid", "barcelona"),
    "IN": ("bangalore", "bengaluru", "hyderabad", "chennai", "pune", "mumbai", "delhi", "gurgaon", "gurugram", "noida"),
    "SG": ("singapore",), "JP": ("tokyo", "osaka"), "KR": ("seoul",), "TW": ("taipei", "hsinchu", "zhubei"),
    "PH": ("manila", "makati", "taguig"), "MX": ("mexico city", "guadalajara", "monterrey", "villahermosa"),
    "AU": ("sydney", "melbourne", "brisbane"), "IL": ("tel aviv",), "DO": ("santo domingo",),
    "AE": ("dubai", "abu dhabi"), "CN": ("shanghai", "beijing", "shenzhen"), "HK": ("hong kong",),
}  # fmt: skip

_NAME_TO_COUNTRY = {name: code for code, names in COUNTRIES.items() for name in names}
_PROVINCE_NAMES = {name.lower(): code for code, name in PROVINCES.items()} | {"québec": "QC"}
_STATE_NAMES = {name.lower(): code for code, name in STATES.items()}
_CITY_TO_COUNTRY = {city: code for code, cities in CITIES.items() for city in cities}
_POSTAL_CA = re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b")
_NOT_A_PLACE = re.compile(r"\bcanada (square|water|place|house|life)\b", re.I)  # London's Canada Square


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[‐‑‒–—]", "-", text)


def _words(piece: str) -> list[str]:
    return [w for w in re.split(r"\s*[,/()\-]\s*|\s{2,}", piece) if w.strip()]


def _place_in(piece: str) -> dict | None:
    """One {city, region, country} from a single location string."""
    raw = _NOT_A_PLACE.sub(" ", piece.strip())
    if not raw:
        return None
    low = raw.lower()
    tokens = [t.strip() for t in re.split(r"\s*,\s*|\s+-\s+|-(?=[A-Z])", raw) if t.strip()]
    country = region = city = None

    # explicit country names or codes anywhere ("United States of America, New York", "GBR-London", "Remote Canada")
    for name, code in sorted(_NAME_TO_COUNTRY.items(), key=lambda kv: -len(kv[0])):
        if len(name) <= 3:
            continue
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            country = code
            break
    upper_tokens = [t for t in re.split(r"[\s,\-/()|]+", raw) if t]
    if country is None:
        for t in upper_tokens:
            if t in (
                "USA",
                "CAN",
                "GBR",
                "FRA",
                "DEU",
                "IND",
                "MEX",
                "SGP",
                "IRL",
                "POL",
                "UK",
                "US",
                "U.S.",
            ):
                country = _NAME_TO_COUNTRY[t.lower()]
                break

    # region: a province or state, as a code after a comma ("Toronto, ON") or by name
    for t in tokens[1:] + tokens[:1]:
        code = t.upper().strip(". ")
        if code in PROVINCES and code != "CA":
            region, country = code, country or "CA"
            break
        if code in STATES and code not in ("CA",):
            if country in (None, "US"):
                region, country = code, "US"
                break
    if region is None:
        for name, code in _PROVINCE_NAMES.items():
            if re.search(rf"\b{re.escape(name)}\b", low) and country in (None, "CA"):
                region, country = code, "CA"
                break
    if region is None:
        for name, code in _STATE_NAMES.items():
            if name in ("washington", "new york", "georgia") and country not in (None, "US"):
                continue
            if re.search(rf"\b{re.escape(name)}\b", low) and country in (None, "US"):
                region, country = code, "US"
                break

    # "City, CA": Canada when a Canadian province, city or postal code is there too, else California
    if "CA" in [t.upper() for t in tokens[1:]] or re.search(r"(^|\s)CA(,|$)", raw):
        canadian = (
            region in PROVINCES
            or _POSTAL_CA.search(raw)
            or any(c in low for c in CITIES["CA"])
            or country == "CA"
        )
        if canadian:
            country = "CA"
        elif region is None:
            region, country = "CA", "US"

    # a two-letter country code at the end of "City, Region, CC[, postcode]" (job feeds)
    if country is None and len(tokens) >= 3:
        for t in reversed(tokens[-2:]):
            if len(t) == 2 and t.upper() in COUNTRIES:
                country = t.upper()
                break

    # a known city
    for name, code in sorted(_CITY_TO_COUNTRY.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            city = name.split(",")[0].title()
            if country is None or (country == "US" and code == "US") or country == code:
                country = country or code
            break
    if (
        city is None
        and tokens
        and country
        and not re.search(r"remote|home|anywhere|worldwide", tokens[0], re.I)
    ):
        first = tokens[0]
        if first.upper() not in COUNTRIES and first.lower() not in _NAME_TO_COUNTRY and len(first) > 2:
            city = first if not re.search(r"\d", first) else None
    if country is None:
        return None
    return {"city": city, "region": region, "country": country}


def parse_locations(location: str, text: str = "") -> list[dict]:
    """Places a posting is in, in the order given: [{city, region, country}].
    When the location line names none, an address in the text ("Ottawa, ON")
    is used."""
    location = _norm(location)
    pieces = re.split(r"\s*(?:\||;|\bor\b|\band\b(?! the)|\n)\s*", location)
    places, seen = [], set()
    for piece in pieces:
        found = _place_in(piece)
        if found is None:
            # a comma list of cities: "Los Angeles, Palo Alto, San Francisco, Toronto"
            for part in piece.split(","):
                found = _place_in(part)
                if found and (found["city"], found["country"]) not in seen:
                    seen.add((found["city"], found["country"]))
                    places.append(found)
            continue
        if found["country"] and len(piece.split(",")) >= 3 and not found["region"]:
            # "Los Angeles, Palo Alto, San Francisco, Toronto" may hold several countries
            for part in piece.split(","):
                sub = _place_in(part)
                if sub and (sub["city"], sub["country"]) not in seen:
                    seen.add((sub["city"], sub["country"]))
                    places.append(sub)
            continue
        key = (found["city"], found["country"])
        if key not in seen:
            seen.add(key)
            places.append(found)
    if not places and text:
        match = re.search(
            r"\b([A-Z][a-zé]+(?: [A-Z][a-zé]+)?),\s*(" + "|".join(PROVINCES) + r")\b,?\s*(?:[A-Z]\d[A-Z])?",
            _norm(text),
        )
        if match and match.group(2) != "CA":
            places.append({"city": match.group(1), "region": match.group(2), "country": "CA"})
    return places


def countries_of(places: list[dict]) -> list[str]:
    out: list[str] = []
    for place in places:
        if place["country"] and place["country"] not in out:
            out.append(place["country"])
    return out


# ---------- workplace ----------

_TAG = re.compile(r"#(?:LI-)?(remote|hybrid|on-?site)\b", re.I)
_LABELLED = re.compile(
    r"\b(?:location|place of performance|work model|work arrangement|workplace(?: type)?|work location type)\s*:\s*"
    r"(?:[^\n,]*?\b)?(remote|hybrid|on-?site)\b",
    re.I,
)
_ONSITE = re.compile(
    r"\bnot (?:a )?(?:hybrid|remote)(?: role| position)?\b|\bthis role is not remote\b|\bfully in[- ]person\b"
    r"|\b(?:in the office|in[- ]office|on[- ]?site)[^.\n]{0,30}\b(?:5|five) days\b|\b(?:5|five) days(?: a|/| per)? ?week\b[^.\n]{0,40}\b(?:office|on[- ]?site|in[- ]person)"
    r"|\bon[- ]?site at [^.\n]{0,40}\bfull[- ]time\b|\bmust be able to work on[- ]?site\b|\b(?:will be |be )?working on[- ]?site\b"
    r"|\bwork on[- ]?site\b|\bconducted in[- ]person\b|\bremote work options are not available\b"
    r"|\blittle to no work from home\b|\blocated on[- ]?site\b|\bprimarily an in[- ]office environment\b"
    r"|\bwork in office,? monday[- ]friday\b|\bfully on[- ]?site\b|\b100% on[- ]?site\b|\bin[- ]office (?:role|position)\b",
    re.I,
)
_HYBRID = re.compile(
    r"\bhybrid[\s/-]+(?:\w+[\s/-]+)?(?:role|position|internship|job|schedule|model|work|working|environment|arrangement|"
    r"approach|basis|setting|workplace|policy)\b|\bworking hybrid\b|\b(?:is|be) (?:a )?hybrid\b|^\s*hybrid\s*$"
    r"|\bremote days? (?:a|per) week\b|\bonsite (?:twice|at least)\b|\b(?:in[- ]office|on[- ]?site) days\b",
    re.I | re.M,
)
_DAYS = re.compile(
    r"\b(?:\d(?:\s*-\s*\d)?|one|two|three|four|1-3)\s*(?:\(\d\)\s*)?days?\s*(?:a|per|/|each)\s*week\b", re.I
)
_OFFICE = re.compile(r"\b(?:office|on[- ]?site|in[- ]office|headquarters|in[- ]person)\b", re.I)
_REMOTE = re.compile(
    r"\b(?:this|the) (?:role|position|opportunity|job) is (?:fully )?remote\b|\bremote (?:opportunity|role|position) "
    r"(?:within|in|open|for)\b|\bremote within\b|\b(?:all of )?our roles are remote\b|\bfully remote\b|\b100% remote\b"
    r"|\bpart[- ]time, remote\b|\bremote work within\b",
    re.I,
)


def parse_workplace(title: str, location: str, text: str) -> str | None:
    """remote, hybrid or onsite, when the posting says."""
    text = _norm(text)
    tag = _TAG.search(text)
    if tag:
        return _workplace_word(tag.group(1))
    labelled = _LABELLED.search(text)
    if labelled:
        return _workplace_word(labelled.group(1))
    for source in (title,):
        word = re.search(r"\b(remote|hybrid|on-?site)\b", source or "", re.I)
        if word:
            return _workplace_word(word.group(1))
    if _ONSITE.search(text):
        return "onsite"
    if _HYBRID.search(text):
        return "hybrid"
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if _DAYS.search(sentence) and _OFFICE.search(sentence):
            return "hybrid"
    if re.search(r"\bremote\b|\bhome[- ]based\b|\bwork from home\b|\banywhere\b", location or "", re.I):
        return "remote"
    if _REMOTE.search(text):
        return "remote"
    return None


def _workplace_word(word: str) -> str:
    word = word.lower().replace("-", "")
    return {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}[word]


# ---------- employment type ----------

_CONTRACT = re.compile(
    r"\bindependent contractor\b|\bcontract (?:position|role|rate|assignment|basis|engagement)\b|\bthis is a contract\b"
    r"|\b(?:\d+|six|twelve|nine|three)[- ]month contract\b|\bB2B\b|\bcontract[- ]to[- ]hire\b|\bfixed[- ]term contract\b"
    r"|\bemployment type\s*:?\s*contract",
    re.I,
)
_PART_TIME = re.compile(
    r"\b(?:this is a|it['’]s a|is a) part[- ]time\b|\bpart[- ]time (?:position|role|job|opportunity)\b"
    r"|\bemployment type\s*:?\s*part[- ]time\b",
    re.I,
)
_TEMPORARY = re.compile(
    r"\btemporary (?:position|role|assignment|employee)\b|\bthis is a temporary\b|\bseasonal (?:position|role)\b"
    r"|\btemporary/seasonal position\b",
    re.I,
)
_FULL_TIME = re.compile(
    r"\b(?:employment|job|position|employee|work|schedule) type\s*:?\s*(?:full[- ]time|permanent|regular)\b"
    r"|\b(?:this is a|is a) (?:full[- ]time|permanent)\b|\bfull[- ]time,?\s+(?:permanent|regular|position|role)\b"
    r"|\bpermanent (?:position|role|basis)\b|^\s*full[- ]time\b(?!\s+(?:employees?|offers?|team|and|/))"
    r"|\bfull[- ]time annual salar(?:y|ies) for this role\b|\b(?:for|start) full[- ]time(?: employment)?\b",
    re.I | re.M,
)


def parse_employment_type(title: str, text: str, seniority: str | None) -> str | None:
    """full_time, part_time, contract, temporary or internship, when the posting says."""
    text = _norm(text)
    if re.search(r"\bnot an internship\b", text, re.I) and _CONTRACT.search(text):
        return "contract"
    if seniority == "intern":
        return "internship"
    for pattern, kind in ((_CONTRACT, "contract"), (_PART_TIME, "part_time"), (_TEMPORARY, "temporary")):
        if pattern.search(title or "") or pattern.search(text):
            return kind
    if re.search(r"\b(contract|contractor)\b", title or "", re.I):
        return "contract"
    if re.search(r"\bpart[- ]time\b", title or "", re.I):
        return "part_time"
    if _FULL_TIME.search(text) or re.search(r"\bfull[- ]time\b", title or "", re.I):
        return "full_time"
    return None


# ---------- sponsorship ----------

_NO_SPONSORSHIP = re.compile(
    r"\b(?:unable|not able|not be able|cannot|can['’]?t|will not|won['’]t|do(?:es)? not|don['’]t|is not able)\s+(?:to\s+)?"
    r"(?:provide\s+|offer\s+|support\s+)?(?:any\s+)?(?:visa\s+|immigration\s+|employment\s+|work\s+)?sponsor"
    r"|\b(?:no|without(?: the need for)?|not eligible for)\s+(?:current or future\s+|employment\s+|visa\s+|"
    r"immigration\s+|employer\s+|work\s+)*sponsorship\b|\bmust not require\b[^.\n]{0,30}sponsorship"
    r"|\bsponsorship is not available\b|\bnot eligible for (?:employment )?(?:visa )?sponsorship"
    r"|\bonly employ those (?:who are )?legally authorized"
    r"|\b(?:u\.?s\.?|united states) citizenship\b|\bmust (?:be|possess) (?:a )?(?:u\.?s\.?|united states) citizen"
    r"|\bcitizenship (?:is )?required\b|\bbritish citizens?\b"
    r"|\b(?:top secret|ts/sci|secret|security) clearance (?:is )?required\b|\bclearance required\b|\bmust have clearance\b"
    r"|\bactive (?:ts/sci|top secret|secret)\b|\bts/sci\b|\btop secret\s*/\s*sci\b|\b(?:eligible for|active or eligible for) dv\b"
    r"|\bdv (?:uk )?security clearance\b|\bsecurity clearance or eligibility\b"
    r"|\bobtain and maintain (?:a |an )?(?:u\.?s\.? )?(?:top secret|secret|ts)\b",
    re.I,
)
_SPONSORSHIP = re.compile(
    r"\b(?:will|may) consider sponsor|\bsponsorship (?:is )?available\b|\bwe sponsor visas?\b|\bvisa sponsorship\s*:\s*yes\b"
    r"|\b(?:we )?offers? visa sponsorship\b|\bable to sponsor\b|\bprovides? visa sponsorship\b",
    re.I,
)
_ITAR = re.compile(r"international traffic in arms|\bITAR\b", re.I)


def parse_sponsorship(text: str) -> str:
    """available, not_available, or unknown."""
    text = _norm(text)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if _ITAR.search(sentence) and not re.search(r"\bcertain positions\b", sentence, re.I):
            return "not_available"
    if _NO_SPONSORSHIP.search(text):
        return "not_available"
    if _SPONSORSHIP.search(text):
        return "available"
    return "unknown"


# ---------- years of experience ----------

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
}  # fmt: skip
_N = r"(?:\d{1,2}(?:\.\d)?|" + "|".join(_NUMBER_WORDS) + r")"
_YEARS = re.compile(
    rf"(?<![\d.])(?P<n>{_N})(?:\s*\(\d+\))?\s*(?:\+|plus)?\s*(?:(?:-|to|or)\s*{_N}\s*\+?\s*)?(?:years?|yrs)\b"
    r"(?=(?P<tail>[^.\n]{0,110}))",  # a lookahead: "BS + 5 years, or MS + 4 years" has two matches
    re.I,
)
_EXPERIENCE = re.compile(r"\bexperience\b|\bas an? \w+|\bin (?:a|an|the) \w+ (?:role|position)\b", re.I)
_NOT_EXPERIENCE = re.compile(r"\b(?:of age|old|history|ago|in business|anniversary|warranty)\b", re.I)
_DEGREES = re.compile(r"\b(?:BS|BA|MS|MA|PhD|bachelor|master|degree)\b", re.I)


def _number(word: str) -> float:
    word = word.lower()
    return float(_NUMBER_WORDS[word]) if word in _NUMBER_WORDS else float(word)


def parse_min_years(text: str) -> float | None:
    """The years of experience the main requirement asks for: the first
    statement of years of experience, and when it gives a track per degree
    ("BS + 5 years, or MS + 4 years"), the smallest."""
    text = _norm(text)
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        found = []
        for match in _YEARS.finditer(sentence):
            tail = match.group("tail")
            if _NOT_EXPERIENCE.match(tail.strip()) or re.match(r"\s*(?:of age|old)\b", tail, re.I):
                continue
            if not (
                _EXPERIENCE.search(tail) or re.search(r"\bexperience\b", sentence[: match.start()], re.I)
            ):
                continue
            found.append(_number(match.group("n")))
        if found:
            return min(found) if _DEGREES.search(sentence) and len(found) > 1 else found[0]
    return None


# ---------- seniority ----------

_INTERN = re.compile(
    r"\b(?:intern(?:ship)?|co-?op|student)\b", re.I
)  # with classify._INTERN's other languages
_SENIOR = re.compile(r"\b(?:senior|sr\.?|lead|manager|director|head|vp|architect)\b", re.I)
_STAFF = re.compile(r"\b(?:staff|principal|distinguished|fellow)\b", re.I)
_GRAD = re.compile(
    r"\b(?:new\s*grad(?:uate)?|university\s*grad(?:uate)?|recent\s*grad(?:uate)?|early[\s-]*careers?|graduate|campus)\b",
    re.I,
)
_JUNIOR = re.compile(r"\b(?:junior|jr\.?|entry[\s-]*level)\b", re.I)
_ROLE_NOUN = r"(?:engineer|developer|analyst|researcher|scientist|designer|specialist|administrator|architect|consultant|technician|programmer|associate)"
_NUMERAL = re.compile(rf"\b{_ROLE_NOUN}\s+(i|ii|iii|iv|v|1|2|3|4|5|6)\b", re.I)
_INTERMEDIATE = re.compile(r"\bintermediate\b", re.I)


def classify_seniority(title: str, years: float | None = None) -> tuple[str, bool]:
    """(intern | new_grad | junior | mid | senior | staff, whether the title said so)."""
    from tracker.classify import _INTERN as INTERN_WORDS
    from tracker.classify import _PROGRAM

    title = _norm(title or "")
    if INTERN_WORDS.search(title) or _INTERN.search(title):
        return "intern", True
    if _SENIOR.search(title):
        return "senior", True
    if _STAFF.search(title):
        return "staff", True
    if _PROGRAM.search(title) or _GRAD.search(title):
        return "new_grad", True
    if _JUNIOR.search(title):
        return "junior", True
    numeral = _NUMERAL.search(title)
    if numeral:
        n = numeral.group(1).lower()
        rank = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}.get(n) or int(n)
        return ("junior" if rank == 1 else "mid" if rank == 2 else "senior"), True
    if _INTERMEDIATE.search(title):
        return "mid", True
    if years is None:
        return "mid", False
    return ("junior" if years <= 2 else "mid" if years < 5 else "senior"), False


def level_of(seniority: str, from_title: bool) -> str:
    """The site's four levels. Only a title makes a posting new grad, so
    asking for few years of experience never turns a role into a student one."""
    if seniority == "junior":
        return "new_grad" if from_title else "mid"
    return {"intern": "intern", "new_grad": "new_grad", "mid": "mid", "senior": "senior", "staff": "senior"}[
        seniority
    ]
