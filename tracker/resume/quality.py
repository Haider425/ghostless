"""Resume checks that apply to every job: the fixes that make a resume
stronger before it's tailored to any one posting."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from tracker.resume.profile import Profile

_BUZZWORDS = re.compile(
    r"\b(hard[\s-]?working|team\s+player|detail[\s-]oriented|go[\s-]getter|self[\s-]starter|passionate|"
    r"synergy|results[\s-]driven|think\s+outside\s+the\s+box|dynamic|motivated\s+individual|fast\s+learner)\b",
    re.I,
)
_PRONOUNS = re.compile(r"(?:^|[.•]\s*)(I|my|me)\b", re.M)


@dataclass
class Check:
    id: str
    severity: str  # high | medium | low
    title: str
    detail: str
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_WEIGHT = {"high": 14, "medium": 8, "low": 4}


def check_resume(text: str, profile: Profile) -> tuple[list[Check], int]:
    """(checks, strength 0 to 100). Checks are ordered most important first."""
    checks: list[Check] = []
    c = profile.contact
    early_career = profile.level in ("student", "new_grad")

    if not c["email"]:
        checks.append(
            Check(
                "no_email",
                "high",
                "Add your email address",
                "Recruiters can't reach you without it. Put it at the top.",
            )
        )
    if not c["phone"]:
        checks.append(
            Check(
                "no_phone",
                "low",
                "Consider adding a phone number",
                "Many recruiters call first, especially for co-op and new grad roles.",
            )
        )
    if not c["linkedin"]:
        checks.append(
            Check(
                "no_linkedin",
                "medium",
                "Add your LinkedIn URL",
                "Most tech recruiters check LinkedIn before reaching out.",
            )
        )
    if not c["github"] and not c["website"] and profile.top_role in ("sde", "ml", "data", "data_eng"):
        checks.append(
            Check(
                "no_portfolio",
                "medium",
                "Link your GitHub or portfolio",
                "A link to real code is the fastest way to show what you can build.",
            )
        )

    missing = [s for s in ("experience", "skills", "education") if s not in profile.sections]
    if "experience" in missing and "projects" not in profile.sections:
        checks.append(
            Check(
                "no_experience",
                "high",
                "Add an Experience or Projects section",
                "Employers look for what you've built. Even school or personal projects count.",
            )
        )
    if "skills" in missing:
        checks.append(
            Check(
                "no_skills_section",
                "medium",
                "Add a Skills section",
                "List languages, frameworks and tools in one place. Applicant tracking systems scan for it.",
            )
        )
    if "education" in missing and early_career:
        checks.append(
            Check(
                "no_education",
                "medium",
                "Add your education",
                "For students and new grads, school and graduation date come near the top.",
            )
        )
    if early_career and "projects" not in profile.sections:
        checks.append(
            Check(
                "no_projects",
                "medium",
                "Add two or three projects",
                "Projects carry a lot of weight early in your career. Name the tech, what it does and one result.",
            )
        )

    if profile.bullet_count >= 4:
        share = profile.quantified_bullets / profile.bullet_count
        if share < 0.4:
            checks.append(
                Check(
                    "few_numbers",
                    "high" if share < 0.2 else "medium",
                    "Put numbers in more of your bullets",
                    f"Only {profile.quantified_bullets} of {profile.bullet_count} bullets have a number. Add scale or "
                    "results: users, records, time saved, speedup, percentage.",
                    profile.unquantified_examples,
                )
            )
    elif "experience" in profile.sections or "projects" in profile.sections:
        checks.append(
            Check(
                "few_bullets",
                "medium",
                "Describe your work in bullets",
                "Two to four bullets per role, each starting with what you did and ending with the result.",
            )
        )

    if profile.weak_bullets:
        checks.append(
            Check(
                "weak_verbs",
                "medium",
                "Start bullets with a strong verb",
                "Phrases like “responsible for” or “helped” hide what you did. Start with built, "
                "designed, automated, reduced or led.",
                profile.weak_bullets[:3],
            )
        )
    if profile.long_bullets:
        checks.append(
            Check(
                "long_bullets",
                "low",
                "Tighten long bullets",
                f"{profile.long_bullets} bullet{'s are' if profile.long_bullets > 1 else ' is'} over 35 words. "
                "Aim for one or two lines each.",
            )
        )

    limit = 750 if early_career else 1200
    if profile.word_count > limit:
        checks.append(
            Check(
                "too_long",
                "medium",
                "Shorten it to " + ("one page" if early_career else "two pages"),
                f"It's about {profile.word_count} words. "
                + (
                    "Students and new grads should fit on one page."
                    if early_career
                    else "Two pages is the usual limit."
                ),
            )
        )
    elif profile.word_count < 200:
        checks.append(
            Check(
                "too_short",
                "medium",
                "Add more detail",
                "It's under 200 words, which leaves recruiters little to go on.",
            )
        )

    if len(profile.skills) < 6:
        checks.append(
            Check(
                "few_skills",
                "medium",
                "Name more specific skills",
                f"Only {len(profile.skills)} recognizable tools or languages were found. Name the ones you've used.",
            )
        )

    buzz = sorted({m.group(0).lower() for m in _BUZZWORDS.finditer(text)})
    if buzz:
        checks.append(
            Check(
                "buzzwords",
                "low",
                "Swap buzzwords for evidence",
                "Words like these say little on their own. Show them with a result instead.",
                buzz[:5],
            )
        )
    if len(_PRONOUNS.findall(text)) >= 2:
        checks.append(
            Check(
                "pronouns",
                "low",
                "Drop “I” and “my”",
                "Resumes are written without first person: “Built a...”, not “I built a...”.",
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    checks.sort(key=lambda ch: order[ch.severity])
    strength = max(5, 100 - sum(_WEIGHT[ch.severity] for ch in checks))
    return checks, strength
