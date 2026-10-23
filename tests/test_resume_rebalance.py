"""Rebalancing the resume evaluation set: likely strong and okay pairs added,
a few clear weak ones kept as a check."""

import contextlib

from tracker.resume import evalset, label
from tracker.resume.evalset import Label, Pair, PreLabel, Target

TORONTO_FE = Target("sde", "intern", "Toronto, ON", "CA", True, ["frontend"])


def job(i, company=None, role="sde", level="intern", location="Toronto, ON", countries=("CA",), remote=False):
    return {"id": i, "company": company or f"Co{i}", "title": f"Job {i}", "role_type": role, "level": level,
            "location": location, "countries": list(countries), "is_remote": remote, "is_canada": "CA" in countries}  # fmt: skip


def test_where_they_want_to_work_is_their_city_or_remote_in_their_country():
    assert evalset.near(job(1), TORONTO_FE)
    assert evalset.near(job(2, location="Remote", remote=True), TORONTO_FE)
    assert not evalset.near(job(3, location="Vancouver, BC"), TORONTO_FE)
    assert not evalset.near(job(4, location="Remote - US", countries=("US",), remote=True), TORONTO_FE)


def test_a_student_abroad_is_one_mismatch_not_a_miss():
    assert evalset.abroad_ok(job(1, location="New York", countries=("US",)), TORONTO_FE)
    assert not evalset.abroad_ok(job(2, level="mid", countries=("US",)), TORONTO_FE)
    senior = Target("sde", "senior", "Toronto, ON", "CA", True, [])
    assert not evalset.abroad_ok(job(3, level="senior", countries=("US",)), senior)


def test_likely_strong_and_likely_okay_are_chosen_from_the_ranking():
    ranked = [
        (job(1), 80),  # right role, level and city, rated well: likely strong
        (job(2, company="Co1"), 78),  # same company as one already chosen: skipped
        (job(3, location="Remote", remote=True), 70),  # remote in Canada: likely strong
        (job(4, location="Vancouver, BC"), 75),  # another city: okay
        (job(5), 40),  # some key skills missing: okay
        (job(6, role="data"), 60),  # a different specialty: okay
        (job(7, location="Seattle", countries=("US",)), 70),  # a student abroad: okay
        (job(8, level="senior"), 90),  # wrong level: never likely
        (job(9), 20),  # a long shot: never likely
        (job(10, company="Taken"), 85),  # the person already has this company
    ]
    chosen = evalset.choose_likely(TORONTO_FE, ranked, [{"id": 99, "company": "Taken", "title": "x"}], 2, 4)
    assert chosen == [
        (1, "likely_strong"), (3, "likely_strong"),
        (4, "likely_okay"), (5, "likely_okay"), (6, "likely_okay"), (7, "likely_okay"),
    ]  # fmt: skip


def test_extra_weak_pairs_are_dropped_keeping_one_of_each_kind_and_anything_labelled():
    sources = ["random", "random", "baseline", "wrong_level", "other_country", "target", "random"]
    pairs = [Pair("p", i, s, "h") for i, s in enumerate(sources)] + [Pair("p", 50, "target", "h")]
    pre = {p.key(): PreLabel("p", p.job, "weak", "r") for p in pairs[:-1]}
    pre[("p", 50)] = PreLabel("p", 50, "strong", "r")
    dropped = evalset.weak_to_drop(pairs, pre, labelled={("p", 6)}, keep=4)
    kept = {p.job for p in pairs} - {p.job for p in dropped}
    assert kept == {6, 2, 3, 4, 50}  # labelled; baseline, wrong level, other country; never the strong one


def test_rebalance_adds_what_is_short_and_is_safe_to_run_twice(tmp_path, monkeypatch):
    persona = evalset.load_personas()[0]  # fe-intern-toronto
    persona.target = TORONTO_FE
    monkeypatch.setattr(evalset, "PAIRS", tmp_path / "pairs.jsonl")
    monkeypatch.setattr(evalset, "LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(evalset, "PRELABELS", tmp_path / "prelabels.jsonl")
    monkeypatch.setattr(evalset, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(label, "_all_resumes", lambda: [persona])
    old = [Pair(persona.id, 900 + i, "random", "h").__dict__ for i in range(6)]
    evalset.write_jsonl(evalset.PAIRS, old)
    evalset.write_jsonl(evalset.PRELABELS, [{"resume": persona.id, "job": r["job"], "fit": "weak", "reason": "r"}
                                            for r in old])  # fmt: skip
    evalset.save_label(Label(persona.id, 905, "weak"), real=False)

    pool = [job(i, location="Remote" if i % 2 else "Vancouver, BC", remote=bool(i % 2)) for i in range(1, 30)]
    for j in pool:
        j["has_text"] = True
    text = "We need React, TypeScript and JavaScript for our frontend web app. " * 5
    monkeypatch.setattr(label, "_job_pool", lambda conn: pool)
    monkeypatch.setattr(label, "_describer", lambda conn, texts: lambda ids: texts.update({i: text for i in ids}) or {i: text for i in ids})  # fmt: skip

    def recommend(profile, jobs, limit, describe, deep):  # every posting rated a good fit
        describe([j["id"] for j in jobs])
        return [(j, type("Match", (), {"score": 70})()) for j in jobs]

    monkeypatch.setattr(label, "recommend", recommend)
    monkeypatch.setattr("tracker.db.connect", lambda dsn: contextlib.nullcontext(None))

    label.rebalance("postgresql://local")
    pairs = evalset.load_pairs()
    sources = [p.source for p in pairs]
    assert sources.count("likely_strong") == 4 and sources.count("likely_okay") == 4
    assert sum(1 for p in pairs if p.source == "random") == 4 and (persona.id, 905) in {
        p.key() for p in pairs
    }
    assert set(evalset.load_prelabels()) <= {p.key() for p in pairs}  # dropped pairs lose their pre-labels
    saved = evalset.load_postings()
    assert all(p.job in saved and saved[p.job]["description"] for p in pairs if p.source in evalset.LIKELY)

    label.rebalance("postgresql://local")  # nothing short, nothing extra: no change
    assert [p.key() for p in evalset.load_pairs()] == [p.key() for p in pairs]
