"""`ghostless evaluate-resume`: measure a resume system on the evaluation set.

Runs offline from the snapshots in eval/resume (no database): each person's
resume against the postings chosen for them, scored by the system and compared
with the answer key (evalset.answer_key). Reports, per docs/resume-model-plan.md:

- ranking: NDCG@10 with graded relevance (strong = 2, okay = 1, weak = 0), and
  precision@3 (strong or okay), per person, then averaged. Each person's judged
  postings are ranked, not the whole pool, so every result is judged;
- fit score: Spearman correlation with the labels, and accuracy and weighted
  kappa after mapping scores to strong/okay/weak with thresholds chosen on the
  tuning split only;
- words to add: the share of suggestions judged fair to add, and how many weren't;
- speed: p95 time to analyse a resume and to score one posting.

Resume text is never printed or written: reports carry ids and numbers only.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from tracker.resume import evalset
from tracker.resume.evalset import FITS, Pair

RESULTS = evalset.ROOT / "results"
GAIN = {"strong": 2, "okay": 1, "weak": 0}
K = 10
TOP = 3  # precision@3: most people have 2 to 8 judged postings, so @10 would count them all
PROVISIONAL = "Claude-labelled, provisional"
SINGLE = "Claude pre-labels, one pass"  # the tuning split: there's no second pass to agree with


# ---------- systems ----------


@dataclass
class Scored:
    score: float  # higher is a better fit
    suggestions: list[str] = field(default_factory=list)  # words to add


@dataclass
class System:
    name: str
    analyse: Callable[[str], object]  # resume text -> whatever score needs
    score: Callable[[object, dict], Scored]  # (analysed resume, posting) -> Scored


def _today() -> System:
    """What the site does today: the resume profile and match.score_job, with
    the posting's skills extracted the way ingest does."""
    from tracker.api.resumes import analyze_text
    from tracker.resume.label import _candidates
    from tracker.resume.match import score_job
    from tracker.skills import extract_skills

    def score(profile, posting: dict) -> Scored:
        job = {
            **posting,
            "skills": extract_skills(f"{posting.get('title') or ''} {posting.get('description') or ''}"),
        }
        match = score_job(profile, job)
        return Scored(match.score, _candidates(match))

    return System("baseline", lambda text: analyze_text(text)["profile"], score)


SYSTEMS: dict[str, Callable[[], System]] = {"baseline": _today}


# ---------- measures ----------


def ndcg(gains_in_order: list[int], k: int = K) -> float | None:
    """Normalised discounted cumulative gain at k; None when nothing is relevant."""
    ideal = sorted(gains_in_order, reverse=True)

    def dcg(gains: list[int]) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))

    best = dcg(ideal)
    return dcg(gains_in_order) / best if best > 0 else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for m in range(i, j + 1):
            ranks[order[m]] = (i + j) / 2 + 1  # ties share their average rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx, vy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx and vy else None


def weighted_kappa(truth: list[str], guess: list[str]) -> float | None:
    """Cohen's kappa with quadratic weights: calling strong weak costs more than calling it okay."""
    n = len(truth)
    if not n:
        return None
    idx = {f: i for i, f in enumerate(FITS)}
    w = [[(i - j) ** 2 / (len(FITS) - 1) ** 2 for j in range(len(FITS))] for i in range(len(FITS))]
    seen = [[0] * len(FITS) for _ in FITS]
    for t, g in zip(truth, guess, strict=True):
        seen[idx[t]][idx[g]] += 1
    rows = [sum(r) for r in seen]
    cols = [sum(seen[i][j] for i in range(len(FITS))) for j in range(len(FITS))]
    observed = sum(w[i][j] * seen[i][j] for i in range(len(FITS)) for j in range(len(FITS)))
    expected = sum(w[i][j] * rows[i] * cols[j] / n for i in range(len(FITS)) for j in range(len(FITS)))
    return 1 - observed / expected if expected else None


def to_fit(score: float, okay_at: float, strong_at: float) -> str:
    return "strong" if score >= strong_at else "okay" if score >= okay_at else "weak"


def choose_thresholds(scored: list[tuple[float, str]]) -> tuple[float, float]:
    """The (okay, strong) cut-offs that agree best (weighted kappa) with these labels."""
    cuts = sorted({s for s, _ in scored} | {0.0, 101.0})
    best, at = -2.0, (50.0, 65.0)  # the site's own "Good fit" and "Strong fit" if nothing better
    truth = [f for _, f in scored]
    for i, okay_at in enumerate(cuts):
        for strong_at in cuts[i:]:
            kappa = weighted_kappa(truth, [to_fit(s, okay_at, strong_at) for s, _ in scored])
            if kappa is not None and kappa > best:
                best, at = kappa, (okay_at, strong_at)
    return at


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)] if ordered else 0.0


# ---------- running ----------


def _split(part: str) -> tuple[list[Pair], list[Pair]]:
    """(pairs to measure, tuning pairs to choose thresholds on)."""
    resumes = {r.id: r for r in evalset.load_personas() + evalset.load_real_resumes()}
    holdout = evalset.load_split()
    pairs = [p for p in evalset.load_pairs() if p.resume in resumes]
    held = [p for p in pairs if evalset.is_holdout(resumes[p.resume], holdout)]
    tuning = [p for p in pairs if not evalset.is_holdout(resumes[p.resume], holdout)]
    return (held if part == "holdout" else tuning), tuning


def _tuning_answers(tuning: list[Pair]) -> dict[tuple[str, int], str]:
    """Labels for choosing thresholds: a person's where there is one, else the
    pre-label (tuning pairs have only the one Claude pass)."""
    labels, pre = evalset.load_labels(), evalset.load_prelabels()
    out = {}
    for p in tuning:
        lab = labels.get(p.key())
        fit = lab.fit if lab else pre[p.key()].fit if p.key() in pre else None
        if fit in FITS:
            out[p.key()] = fit
    return out


def evaluate(system_name: str = "baseline", part: str = "holdout") -> dict:
    system = SYSTEMS[system_name]()
    measured, tuning = _split(part)
    key = evalset.answer_key(measured)
    if part == "tuning":  # only the one pass to go on: the pre-labels, unless a person labelled it
        key.answers = {k: evalset.Answer(f, "claude-single") for k, f in _tuning_answers(tuning).items()}
        key.disputed = {}
    resumes = {r.id: r for r in evalset.load_personas() + evalset.load_real_resumes()}
    postings = evalset.load_postings()

    analysed: dict[str, object] = {}
    analyse_times: list[float] = []
    score_times: list[float] = []
    scores: dict[tuple[str, int], Scored] = {}
    for pair in measured + (tuning if part == "holdout" else []):
        if pair.resume not in analysed:
            started = time.perf_counter()
            analysed[pair.resume] = system.analyse(resumes[pair.resume].text)
            analyse_times.append(time.perf_counter() - started)
        started = time.perf_counter()
        scores[pair.key()] = system.score(analysed[pair.resume], postings[pair.job])
        score_times.append(time.perf_counter() - started)

    # ranking, per person
    by_person: dict[str, list[Pair]] = {}
    for pair in measured:
        if pair.key() in key.answers:
            by_person.setdefault(pair.resume, []).append(pair)
    per_person = {}
    for rid, mine in sorted(by_person.items()):
        ranked = sorted(mine, key=lambda p: (-scores[p.key()].score, p.job))  # ties: by posting id
        gains = [GAIN[key.answers[p.key()].fit] for p in ranked]
        value = ndcg(gains)
        if value is not None:
            top = gains[:TOP]
            per_person[rid] = {
                "ndcg@10": value,
                "p@3": sum(g > 0 for g in top) / len(top),
                "pairs": len(mine),
            }
    no_relevant = sorted(set(by_person) - set(per_person))

    # fit score
    judged = [p for p in measured if p.key() in key.answers]
    xs = [scores[p.key()].score for p in judged]
    truth = [key.answers[p.key()].fit for p in judged]
    tuning_truth = _tuning_answers(tuning)
    okay_at, strong_at = choose_thresholds(
        [(scores[k].score, f) for k, f in tuning_truth.items() if k in scores]
    )
    guess = [to_fit(x, okay_at, strong_at) for x in xs]

    # words to add
    fair = unfair = unjudged = 0
    for p in judged:
        verdicts = key.terms.get(p.key(), {})
        for term in scores[p.key()].suggestions:
            verdict = verdicts.get(term)
            if verdict is None:
                unjudged += 1
            elif verdict:
                fair += 1
            else:
                unfair += 1

    def mean(values):
        values = list(values)
        return sum(values) / len(values) if values else None

    return {
        "system": system_name,
        "part": part,
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels": SINGLE if part == "tuning" else PROVISIONAL if key.provisional else "human",
        "pairs": {
            "measured": len(measured),
            "scored": len(judged),
            "disputed": len(key.disputed),
            "by_label": {f: truth.count(f) for f in FITS},
        },
        "ranking": {
            "ndcg@10": mean(v["ndcg@10"] for v in per_person.values()),
            "p@3": mean(v["p@3"] for v in per_person.values()),
            "people": len(per_person),
            "people_with_nothing_relevant": len(no_relevant),
        },
        "fit": {
            "spearman": spearman(xs, [GAIN[f] for f in truth]),
            "thresholds": {"okay": okay_at, "strong": strong_at, "chosen_on": "tuning"},
            "accuracy": mean(a == b for a, b in zip(truth, guess, strict=True)),
            "weighted_kappa": weighted_kappa(truth, guess),
        },
        "words_to_add": {
            "precision": fair / (fair + unfair) if fair + unfair else None,
            "fair": fair,
            "not_fair": unfair,
            "unjudged": unjudged,
        },
        "speed": {"analyse_p95_ms": 1000 * p95(analyse_times), "score_p95_ms": 1000 * p95(score_times)},
        "per_person": per_person,
        "disputed": [
            {"resume": r, "job": j, "pre_label": a, "second": b} for (r, j), (a, b) in key.disputed.items()
        ],
    }


def _fmt(value, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def report(result: dict) -> str:
    r, f, w, s, n = result["ranking"], result["fit"], result["words_to_add"], result["speed"], result["pairs"]
    lines = [
        f"{result['system']} on the {result['part']} set ({result['labels']})",
        f"  pairs: {n['scored']} scored of {n['measured']} "
        f"({', '.join(f'{k} {v}' for k, v in n['by_label'].items())}); "
        f"{n['disputed']} disputed, left out",
        f"  ranking: NDCG@10 {_fmt(r['ndcg@10'])}, precision@3 {_fmt(r['p@3'])} over {r['people']} people "
        f"({r['people_with_nothing_relevant']} with nothing relevant, left out)",
        f"  fit score: Spearman {_fmt(f['spearman'])}; accuracy {_fmt(f['accuracy'])}, weighted kappa "
        f"{_fmt(f['weighted_kappa'])} (okay at {f['thresholds']['okay']:g}, strong at "
        f"{f['thresholds']['strong']:g}, chosen on tuning)",
        f"  words to add: precision {_fmt(w['precision'])} ({w['fair']} fair, {w['not_fair']} not fair, "
        f"{w['unjudged']} unjudged)",
        f"  speed: analyse p95 {s['analyse_p95_ms']:.0f} ms, score one posting p95 {s['score_p95_ms']:.1f} ms",
    ]
    return "\n".join(lines)


def run(system_name: str = "baseline", part: str = "holdout") -> dict:
    result = evaluate(system_name, part)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{system_name}-{part}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(report(result))
    repo = evalset.ROOT.parents[1]
    print(f"  saved {path.relative_to(repo).as_posix() if path.is_relative_to(repo) else path}")
    return result
