"""`ghostless label-resume`: build and label the resume evaluation set.

    ghostless label-resume pool --db URL   choose postings for every resume that has none yet,
                                           and save their text locally (reads the database only)
    ghostless label-resume                 label pairs: strong, okay or weak, and which
                                           suggested words are fair to add
    ghostless label-resume status          how many pairs are labelled

See tracker/resume/evalset.py for the files. Resume text is shown on screen
while labelling and never written to a log.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
import textwrap

from tracker.resume import evalset
from tracker.resume.evalset import Label, Pair, Resume

SEED = 20261022


def _all_resumes() -> list[Resume]:
    return evalset.load_personas() + evalset.load_real_resumes()


def _candidates(match, limit: int = 12) -> list[str]:
    """What today's system would tell this person to add, for the labeller to judge:
    the key terms they don't use and the required skills they don't show."""
    seen: dict[str, str] = {}
    for term in list(match.terms_missing) + list(match.skills_missing):
        seen.setdefault(term.lower(), term)
    return list(seen.values())[:limit]


def pool(dsn: str, per_resume: int = 8, only: str | None = None, seed: int = SEED) -> None:
    from tracker import db
    from tracker.api import queries
    from tracker.api.resumes import analyze_text
    from tracker.resume.match import recommend, score_job

    resumes = [r for r in _all_resumes() if not only or r.id == only]
    guessed = []
    for resume in resumes:
        if resume.target is None:  # a real resume without its <id>.yaml yet
            resume.target = evalset.guess_target(resume)
            guessed.append(resume.id)
            print(f"{resume.id}: wrote a guess at its target ({resume.target.role}, {resume.target.level}) "
                  f"to private/resumes/{resume.id.removeprefix('real-')}.yaml. Check it, then run pool again.")  # fmt: skip
    resumes = [r for r in resumes if r.id not in guessed]  # chosen only once the target is confirmed

    split = evalset.extend_split(evalset.SPLIT, [r.id for r in evalset.load_personas()])
    if not evalset.SPLIT.exists() or evalset.load_split() != set(split["holdout"]):
        evalset.SPLIT.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
        print(f"held out {len(split['holdout'])} personas (eval/resume/split.json)")

    existing = evalset.load_pairs()
    have = {p.resume for p in existing}
    todo = [r for r in resumes if r.id not in have]
    if not todo:
        print("every resume already has postings to label")
        return

    texts: dict[int, str] = {}
    with db.connect(dsn) as conn:
        jobs = queries.matching_pool(conn, "any", include_high_risk=False)
        extra = {
            row[0]: (row[1], row[2], row[3])
            for row in conn.execute(
                """SELECT id, countries, fingerprint, length(coalesce(description, '')) > 200
                   FROM jobs WHERE id = ANY(%s)""",
                ([j["id"] for j in jobs],),
            ).fetchall()
        }
        for job in jobs:
            job["countries"], job["fingerprint"], job["has_text"] = extra.get(job["id"], ([], "", False))

        def describe(ids: list[int]) -> dict[int, str]:
            missing = [i for i in ids if i not in texts]
            if missing:
                texts.update(queries.descriptions(conn, missing))
            return {i: texts[i] for i in ids if i in texts}

        rng = random.Random(seed)
        by_id = {j["id"]: j for j in jobs}
        new_pairs: list[Pair] = []
        for n, resume in enumerate(todo, 1):
            profile = analyze_text(resume.text)["profile"]
            # today's top 30, of which the first few with a description are taken
            baseline = [job["id"] for job, _ in recommend(profile, jobs, 30, describe=describe)]
            chosen = evalset.choose_pairs(resume.target, baseline, jobs, rng, min(per_resume, resume.pairs))
            described = describe([job_id for job_id, _ in chosen])
            for job_id, source in chosen:
                job = {**by_id[job_id], "description": described.get(job_id, "")}
                match = score_job(profile, job)
                new_pairs.append(
                    Pair(resume.id, job_id, source, evalset.text_hash(job["description"]), _candidates(match))
                )
            print(f"[{n}/{len(todo)}] {resume.id}: {len(chosen)} postings")

    postings = evalset.load_postings()
    for pair in new_pairs:
        job = by_id[pair.job]
        postings[pair.job] = {
            "id": job["id"],
            "company": job["company"],
            "title": job["title"],
            "location": job.get("location"),
            "level": job.get("level"),
            "role_type": job.get("role_type"),
            "countries": job.get("countries") or [],
            "url": job.get("url"),
            "description": texts.get(job["id"], ""),
        }
    evalset.write_jsonl(evalset.PRIVATE / "postings.jsonl", list(postings.values()))
    real_ids = {r.id for r in resumes if r.real}
    for path, mine in ((evalset.PAIRS, False), (evalset.PRIVATE / "pairs.jsonl", True)):
        rows = evalset.read_jsonl(path) + [p.__dict__ for p in new_pairs if (p.resume in real_ids) == mine]
        evalset.write_jsonl(path, rows)
    print(f"added {len(new_pairs)} pairs; posting text saved in eval/resume/private/postings.jsonl")


# ---------- labelling ----------


def _width() -> int:
    return min(100, shutil.get_terminal_size((100, 30)).columns - 2)


def _wrap(text: str, max_lines: int | None = None) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        lines.extend(textwrap.wrap(line, _width()) or [""])
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… ({len(lines) - max_lines} more lines: press f for the full posting)"]
    return "\n".join(lines)


def _show_resume(resume: Resume) -> None:
    t = resume.target or evalset.Target("?", "?")
    where = t.location + (" or remote" if t.remote_ok and "remote" not in t.location.lower() else "")
    print(f"RESUME  {resume.id}{'  (real, held out)' if resume.real else ''}")
    field = f" · field: {resume.field}" if resume.field else ""
    print(f"Wants:  {t.role} · {t.level} · {where}{field}")
    print(f"        {resume.summary}")
    print("-" * _width())
    print(_wrap(resume.text.strip()))


def _asks(posting: dict) -> str:
    from tracker.resume.posting import split_posting

    parts = split_posting(posting.get("description") or "")
    shown = [
        f"[{name}]\n{parts[key]}"
        for key, name in (("required", "Requirements"), ("preferred", "Nice to have"))
        if parts.get(key)
    ]
    if not shown:
        shown = [f"[Description]\n{parts.get('general') or parts.get('duties') or '(no description)'}"]
    return "\n\n".join(shown)


def _show_posting(posting: dict, full: bool = False) -> None:
    where = posting.get("location") or "?"
    print(f"POSTING #{posting['id']}  {posting['company']} | {posting['title']}")
    print(f"        {posting.get('level')} · {posting.get('role_type')} · {where}")
    print("-" * _width())
    text = (posting.get("description") or "") if full else _asks(posting)
    print(_wrap(text, None if full else 30))


def _ask(prompt: str, choices: str, default: str | None = None) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if not answer and default:
            return default
        if answer[:1] in choices and answer:
            return answer[:1]
        print(f"  Type one of: {', '.join(choices)}")


def _terms(candidates: list[str], before: dict[str, bool]) -> dict[str, bool] | None:
    if not candidates:
        return {}
    print("\nWords a system might tell this person to add. Which are FAIR to suggest?")
    print("(a real requirement of the posting AND something this person plausibly has)")
    for i, term in enumerate(candidates, 1):
        mark = {True: " (yes before)", False: " (no before)"}.get(before.get(term), "")
        print(f"  {i:2}. {term}{mark}")
    while True:
        raw = (
            input("Numbers that are fair (e.g. 1 4), Enter for none, a for all, b to go back: ")
            .strip()
            .lower()
        )
        if raw == "b":
            return None
        if raw == "a":
            return {t: True for t in candidates}
        try:
            picked = {int(n) for n in raw.replace(",", " ").split()}
        except ValueError:
            print("  Numbers only, separated by spaces.")
            continue
        if all(1 <= n <= len(candidates) for n in picked):
            return {t: (i in picked) for i, t in enumerate(candidates, 1)}
        print(f"  Numbers from 1 to {len(candidates)}.")


PARTS = ("all", "holdout", "tuning")


def pairs_to_label(
    resumes: dict[str, Resume], postings: dict[int, dict], part: str = "all", only: str | None = None
) -> list[Pair]:
    """The pairs in labelling order, narrowed to held-out or tuning pairs, or one resume."""
    holdout = evalset.load_split() if evalset.SPLIT.exists() else set()
    pairs = [
        p
        for p in evalset.load_pairs()
        if p.resume in resumes
        and p.job in postings
        and (not only or p.resume == only)
        and (part == "all" or (part == "holdout") == evalset.is_holdout(resumes[p.resume], holdout))
    ]
    return evalset.labelling_order(pairs, list(resumes))


def label(only: str | None = None, part: str = "all", review: bool = False) -> None:
    """Label pairs one at a time. Blind unless `review`: then only tuning pairs,
    each shown with its pre-label and reason, accepted with Enter."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    print("Loading the resumes and postings…", flush=True)
    resumes = {r.id: r for r in _all_resumes()}
    postings = evalset.load_postings()
    if review:
        part = "tuning"  # never for held-out pairs
    order = pairs_to_label(resumes, postings, part, only)
    if not order:
        print("No pairs to label here. Run: ghostless label-resume pool --db <local database URL>")
        return
    prelabels = evalset.load_prelabels() if review else {}
    labels = evalset.load_labels()
    i = next((n for n, p in enumerate(order) if p.key() not in labels), len(order))
    print(__doc__.split("\n\n")[0])
    if review:
        print("Review: Enter or a accepts the pre-label · s o w to correct it · f r k b q as usual\n")
    else:
        print(
            "Keys: s strong · o okay · w weak · f full posting · r resume again · k skip · b back · q quit\n"
        )
    while i < len(order):
        pair = order[i]
        resume, posting = resumes[pair.resume], postings[pair.job]
        done = sum(1 for p in order if p.key() in labels)
        print("\n" + "=" * _width())
        print(f"Pair {i + 1} of {len(order)} · {done} labelled · chosen as: {pair.source}")
        print("=" * _width())
        _show_resume(resume)
        print()
        _show_posting(posting)
        previous = labels.get(pair.key())
        if previous:
            print(f"\n(labelled before: {previous.fit})")
        if evalset.text_hash(posting.get("description")) != pair.text_hash:
            print("\n(note: this posting's saved text differs from when it was chosen)")
        pre = prelabels.get(pair.key())
        if pre:
            print(f"\nPre-label: {pre.fit.upper()} · {pre.reason}")
        keys = "sowfrkbqa" if pre else "sowfrkbq"
        prompt = (
            "\n[Enter/a] accept · [s]trong [o]kay [w]eak · [f]ull [r]esume [k]skip [b]ack [q]uit: "
            if pre
            else "\nFit? [s]trong [o]kay [w]eak · [f]ull [r]esume [k]skip [b]ack [q]uit: "
        )
        while True:
            key = _ask(prompt, keys, default="a" if pre else None)
            if key == "f":
                print()
                _show_posting(posting, full=True)
            elif key == "r":
                print()
                _show_resume(resume)
            else:
                break
        if key == "q":
            break
        if key == "k":
            i += 1
            continue
        if key == "b":
            i = max(0, i - 1)
            continue
        if key == "a":
            fit, via = pre.fit, "review-accepted"
        else:
            fit = {"s": "strong", "o": "okay", "w": "weak"}[key]
            via = ("review-accepted" if fit == pre.fit else "review-corrected") if pre else ""
        terms = _terms(pair.candidates, previous.terms if previous else {})
        if terms is None:
            continue  # back to the fit question for this pair
        record = Label(pair.resume, pair.job, fit, terms, via=via)
        evalset.save_label(record, real=resume.real)
        labels[pair.key()] = record
        i += 1
    done = sum(1 for p in order if p.key() in labels)
    print(f"\nSaved. {done} of {len(order)} pairs labelled. Run the same command to continue.")


def agreement_report(examples: int = 12) -> None:
    """How often your labels agree with the pre-labels, overall and per label,
    on held-out and tuning pairs, with examples of where you differ."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    resumes = {r.id: r for r in _all_resumes()}
    holdout = evalset.load_split() if evalset.SPLIT.exists() else set()
    labels = list(evalset.load_labels().values())
    prelabels = evalset.load_prelabels()
    postings = evalset.load_postings()
    for name, keep in (
        ("held out (labelled blind)", lambda r: evalset.is_holdout(r, holdout)),
        ("tuning", lambda r: not evalset.is_holdout(r, holdout)),
        ("all", lambda r: True),
    ):
        part = [lab for lab in labels if lab.resume in resumes and keep(resumes[lab.resume])]
        result = evalset.agreement(part, prelabels)
        print(f"\n{name}: {result.pairs} pairs compared")
        if not result.pairs:
            continue
        print(
            f"  agree {result.agree} of {result.pairs} ({result.share:.0%}), Cohen's kappa {result.kappa:.2f}"
        )
        for fit in evalset.FITS:
            agreed, total = result.by_label.get(fit, (0, 0))
            if total:
                print(f"  you said {fit:6}: pre-label agreed {agreed} of {total} ({agreed / total:.0%})")
        print("  pre-label (rows) vs yours (columns):  " + "  ".join(f"{f:>6}" for f in evalset.FITS))
        for fit in evalset.FITS:
            row = result.confusion[fit]
            print(
                f"    {fit:6}                              " + "  ".join(f"{row[f]:>6}" for f in evalset.FITS)
            )
    result = evalset.agreement([lab for lab in labels if lab.resume in resumes], prelabels)
    if result.disagreements:
        print(
            f"\nWhere you differ ({min(examples, len(result.disagreements))} of {len(result.disagreements)}):"
        )
        for lab, pre in result.disagreements[:examples]:
            job = postings.get(lab.job, {})
            print(f"  {lab.resume} × {job.get('company', '?')} | {job.get('title', lab.job)}")
            print(
                f"     you: {lab.fit}{f' ({lab.note})' if lab.note else ''} · pre-label: {pre.fit}, {pre.reason}"
            )


def status() -> None:
    resumes = {r.id: r for r in _all_resumes()}
    pairs = evalset.load_pairs()
    labels = evalset.load_labels()
    holdout = evalset.load_split() if evalset.SPLIT.exists() else set()
    rows = {"tuning": [0, 0], "held out": [0, 0]}
    fits = {f: 0 for f in evalset.FITS}
    for pair in pairs:
        resume = resumes.get(pair.resume)
        if resume is None:
            continue
        part = "held out" if evalset.is_holdout(resume, holdout) else "tuning"
        rows[part][0] += 1
        if pair.key() in labels:
            rows[part][1] += 1
            fits[labels[pair.key()].fit] += 1
    real = sum(1 for r in resumes.values() if r.real)
    print(f"Resumes: {len(resumes) - real} personas, {real} real (private)")
    for part, (total, done) in rows.items():
        print(f"  {part:9} {done:4} of {total:4} pairs labelled")
    print("  labels: " + ", ".join(f"{fit} {n}" for fit, n in fits.items()))
