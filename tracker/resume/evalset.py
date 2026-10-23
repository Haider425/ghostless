"""The resume evaluation set (docs/resume-model-plan.md, stage 1).

Resumes, resume-job pairs to label, and the labels, in eval/resume/:

    personas.yaml        synthetic resumes, each with the role, level and place it targets (committed)
    split.json           which personas are held out: never used for tuning (committed, frozen)
    pairs.jsonl          the postings chosen for each persona, by id and text hash (committed)
    labels.jsonl         your labels for the persona pairs (committed)
    private/             git-ignored, never committed:
      postings.jsonl     the text of every chosen posting, so labels outlive the posting
      resumes/           real resumes (PDF, Word or text), shared with permission; each is
                         held out, and used only for evaluation, never tuning
      resumes/<id>.yaml  what that resume targets (written with a guess the first time; edit it)
      pairs.jsonl        the postings chosen for real resumes
      labels.jsonl       your labels for them

Resume text is never logged. The labelling tool shows it on screen to the
person labelling, and nothing else ever prints it.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "eval" / "resume"
PERSONAS = ROOT / "personas.yaml"
PERSONAS_FIELDS = ROOT / "personas_fields.yaml"  # 60 more, outside tech
SPLIT = ROOT / "split.json"
PAIRS = ROOT / "pairs.jsonl"
LABELS = ROOT / "labels.jsonl"
PRIVATE = ROOT / "private"

ROLES = ("sde", "data", "data_eng", "ml", "hardware", "security")
TARGET_ROLES = ROLES + ("other",)  # other: someone staying in a field Ghostless doesn't list
LEVELS = ("intern", "new_grad", "mid", "senior")
FITS = ("strong", "okay", "weak")
HOLDOUT_SHARE = 0.3
RESUME_FILES = (".pdf", ".docx", ".txt", ".md")


@dataclass
class Target:
    role: str
    level: str
    location: str = ""
    country: str = ""
    remote_ok: bool = True
    titles: list[str] = field(default_factory=list)


@dataclass
class Resume:
    id: str
    summary: str
    target: Target
    text: str = field(repr=False)  # never in a repr, so never in a log line by accident
    real: bool = False  # a real person's resume from private/: evaluation only, always held out
    notes: str = ""
    field: str = ""  # the person's own field (accounting, healthcare...), for telling fields apart
    pairs: int = 8  # postings to label for this person


@dataclass
class Pair:
    resume: str
    job: int
    source: str  # baseline | target | wrong_level | other_country | random
    text_hash: str  # of the posting's description when it was chosen
    candidates: list[str] = field(default_factory=list)  # terms a system might suggest adding

    def key(self) -> tuple[str, int]:
        return (self.resume, self.job)


@dataclass
class Label:
    resume: str
    job: int
    fit: str  # strong | okay | weak
    terms: dict[str, bool] = field(default_factory=dict)  # fair to suggest adding?
    at: str = ""


# ---------- resumes ----------


def _target(raw: dict) -> Target:
    target = Target(**{k: v for k, v in raw.items() if k in Target.__dataclass_fields__})
    if target.role not in TARGET_ROLES or target.level not in LEVELS:
        raise ValueError(f"unknown target role or level: {target.role}, {target.level}")
    return target


def load_personas(paths: tuple[Path, ...] | None = None) -> list[Resume]:
    """Every synthetic resume: the 40 in tech, then the 60 in other fields."""
    items = []
    for path in paths or (PERSONAS, PERSONAS_FIELDS):
        if path.exists():
            items += yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [
        Resume(
            id=item["id"],
            summary=item["summary"],
            target=_target(item["target"]),
            text=item["resume"],
            notes=item.get("notes", ""),
            field=item.get("field", ""),
            pairs=int(item.get("pairs", 8)),
        )
        for item in items
    ]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "resume"


def load_real_resumes(folder: Path | None = None, read_file=None) -> list[Resume]:
    """Real resumes from private/resumes, each with its target from <id>.yaml.
    A resume without one gets None for now: `guess_target` writes it."""
    folder = folder or PRIVATE / "resumes"
    if not folder.is_dir():
        return []
    if read_file is None:
        from tracker.resume.extract import extract_text

        def read_file(path: Path) -> str:
            from tracker.resume import ocr
            from tracker.resume.extract import UnreadableResume

            data = path.read_bytes()
            try:
                return extract_text(data, path.name)
            except UnreadableResume:
                # a scanned PDF: read the picture of the text, locally (tracker/resume/ocr.py)
                if path.suffix.lower() != ".pdf" or not ocr.available():
                    raise
                text = ocr.pdf_text(data)
                if len(text.split()) < 30:
                    raise UnreadableResume(
                        "Even text recognition found almost no text in this file."
                    ) from None
                return text

    from tracker.resume.extract import UnreadableResume

    resumes = []
    for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in RESUME_FILES):
        rid = f"real-{slug(path.stem)}"
        try:
            text = read_file(path)
        except UnreadableResume as exc:  # a scanned image with no text layer, say: skipped, by id only
            print(f"{rid}: skipped ({exc})")
            continue
        meta_path = path.with_suffix(".yaml")
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
        target = _target(meta["target"]) if meta and meta.get("target") else None
        resumes.append(
            Resume(
                id=rid,
                summary=(meta or {}).get("summary") or "Real resume (private)",
                target=target,  # type: ignore[arg-type]
                text=text,
                real=True,
            )
        )
    return resumes


def guess_target(resume: Resume, folder: Path | None = None) -> Target:
    """A first guess at what a real resume targets, from its profile, written
    next to it as <id>.yaml for the person to correct."""
    from tracker.api.resumes import analyze_text

    profile = analyze_text(resume.text)["profile"]
    level = {"student": "intern", "new_grad": "new_grad", "experienced": "mid", "senior": "senior"}.get(
        profile.get("level") or "", "new_grad"
    )
    role = profile.get("top_role") if profile.get("top_role") in ROLES else "sde"
    target = Target(role=role, level=level, location="", country="CA", remote_ok=True, titles=[])
    folder = folder or PRIVATE / "resumes"
    stem = resume.id.removeprefix("real-")
    meta = {
        "summary": "Real resume (private). Edit the target below, then run `ghostless label-resume pool` again.",
        "target": target.__dict__,
    }
    for path in folder.iterdir():
        if path.suffix.lower() in RESUME_FILES and slug(path.stem) == stem:
            path.with_suffix(".yaml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")
    return target


# ---------- the held-out split ----------


def _hashed_share(resume_id: str) -> float:
    return int(hashlib.sha256(resume_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def make_split(persona_ids: list[str]) -> dict:
    """About 30% of the personas, chosen by a hash of their id, never by hand."""
    holdout = sorted(i for i in persona_ids if _hashed_share(i) < HOLDOUT_SHARE)
    return {"holdout": holdout, "sha256": split_hash(holdout)}


def split_hash(holdout: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(holdout)).encode()).hexdigest()


def extend_split(path: Path, persona_ids: list[str]) -> dict:
    """The split with personas added since it was written. The hash decides each
    persona once, so a persona never changes sides; adding personas only adds ids."""
    split = make_split(persona_ids)
    if path.exists():
        before = load_split(path)
        if not before <= set(split["holdout"]):
            raise ValueError("held-out personas would change sides: the split must not change")
    return split


def load_split(path: Path = SPLIT) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if split_hash(data["holdout"]) != data["sha256"]:
        raise ValueError("eval/resume/split.json was edited: the held-out set must not change")
    return set(data["holdout"])


def is_holdout(resume: Resume, holdout: set[str]) -> bool:
    return resume.real or resume.id in holdout


# ---------- pairs, postings and labels ----------


def text_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def load_pairs() -> list[Pair]:
    return [Pair(**row) for row in read_jsonl(PAIRS) + read_jsonl(PRIVATE / "pairs.jsonl")]


def load_postings() -> dict[int, dict]:
    return {row["id"]: row for row in read_jsonl(PRIVATE / "postings.jsonl")}


def load_labels() -> dict[tuple[str, int], Label]:
    """The latest label for each pair (relabelling appends; the last one wins)."""
    labels: dict[tuple[str, int], Label] = {}
    for row in read_jsonl(LABELS) + read_jsonl(PRIVATE / "labels.jsonl"):
        labels[(row["resume"], row["job"])] = Label(**row)
    return labels


def save_label(label: Label, real: bool) -> None:
    """Appended at once, so quitting at any point loses nothing."""
    label.at = label.at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = PRIVATE / "labels.jsonl" if real else LABELS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(label.__dict__, ensure_ascii=False) + "\n")


def labelling_order(pairs: list[Pair], resume_ids: list[str]) -> list[Pair]:
    """One pair per resume in turn, so stopping early still covers every resume."""
    by_resume: dict[str, list[Pair]] = {rid: [] for rid in resume_ids}
    for pair in pairs:
        by_resume.setdefault(pair.resume, []).append(pair)
    order: list[Pair] = []
    for i in range(max((len(v) for v in by_resume.values()), default=0)):
        for rid in by_resume:
            if i < len(by_resume[rid]):
                order.append(by_resume[rid][i])
    return order


# ---------- choosing postings to label ----------


def _in_country(job: dict, country: str) -> bool:
    countries = job.get("countries") or []
    if country and countries:
        return country in countries
    if country == "CA":
        return bool(job.get("is_canada"))
    return True


def _title_fits(job: dict, target: Target) -> bool:
    title = (job.get("title") or "").lower()
    return job.get("role_type") == target.role and any(t.lower() in title for t in target.titles)


def choose_pairs(
    target: Target, baseline: list[int], jobs: list[dict], rng: random.Random, per_resume: int = 8
) -> list[tuple[int, str]]:
    """(job id, why it was chosen) for one resume, pooled so no one system decides
    what gets judged: today's top results, postings that fit the target, and
    deliberate near misses (the right role at the wrong level, or in another
    country), plus one random posting. Duplicates of a chosen posting are skipped.

    Only postings with a description are chosen (`has_text`): half of all open
    postings come from the job lists with a title only, and fit can't be judged
    from a title. `baseline` can be longer than 3; its first 3 with text are taken."""
    jobs = [j for j in jobs if j.get("has_text", True)]
    by_id = {j["id"]: j for j in jobs}
    chosen: list[tuple[int, str]] = []
    seen_prints: set[str] = set()

    def take(candidates: list[dict], source: str, count: int) -> None:
        for job in candidates:
            if sum(1 for _, s in chosen if s == source) >= count or len(chosen) >= per_resume:
                return
            fingerprint = job.get("fingerprint") or f"{job.get('company')}|{job.get('title')}"
            if job["id"] in {i for i, _ in chosen} or fingerprint in seen_prints:
                continue
            chosen.append((job["id"], source))
            seen_prints.add(fingerprint)

    shuffled = jobs[:]
    rng.shuffle(shuffled)
    fits_title = [j for j in shuffled if _title_fits(j, target)]
    # few postings for someone (3 for people outside tech): today's top two and one random
    take([by_id[i] for i in baseline if i in by_id], "baseline", min(3, per_resume - 1))
    take(
        [j for j in fits_title if j.get("level") == target.level and _in_country(j, target.country)],
        "target",
        2,
    )
    take(
        [j for j in fits_title if j.get("level") != target.level and _in_country(j, target.country)],
        "wrong_level",
        1,
    )
    take(
        [j for j in fits_title if j.get("level") == target.level and not _in_country(j, target.country)],
        "other_country",
        1,
    )
    take(shuffled, "random", 1)
    # short of postings somewhere: more that fit the target, then the same role
    # and level in the country (titles vary: "Avionics Software" for robotics),
    # then the same role anywhere
    take([j for j in fits_title if _in_country(j, target.country)], "target", per_resume)
    same_role = [j for j in shuffled if j.get("role_type") == target.role]
    take(
        [j for j in same_role if j.get("level") == target.level and _in_country(j, target.country)],
        "target",
        per_resume,
    )
    take(same_role, "target", per_resume)
    # people outside tech: postings at their level in their country, as plain near misses
    take(
        [j for j in shuffled if j.get("level") == target.level and _in_country(j, target.country)],
        "random",
        per_resume,
    )
    return chosen
