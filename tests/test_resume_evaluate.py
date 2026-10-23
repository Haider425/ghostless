"""ghostless evaluate-resume: the measures, and the answer key it scores against."""

import json

import pytest

from tracker.resume import evalset, evaluate
from tracker.resume.evalset import Label, Pair


def test_ndcg_rewards_strong_first_and_okay_as_partial():
    assert evaluate.ndcg([2, 1, 0]) == pytest.approx(1.0)
    assert evaluate.ndcg([0, 1, 2]) < evaluate.ndcg([1, 0, 2]) < evaluate.ndcg([2, 0, 1]) < 1
    assert evaluate.ndcg([0, 0]) is None  # nothing relevant: left out, not scored 0
    assert evaluate.ndcg([0, 1]) > 0  # an okay posting counts as a partial match


def test_spearman_and_weighted_kappa():
    assert evaluate.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert evaluate.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    truth = ["strong", "okay", "weak", "weak"]
    assert evaluate.weighted_kappa(truth, truth) == pytest.approx(1.0)
    near = evaluate.weighted_kappa(truth, ["okay", "okay", "weak", "weak"])
    far = evaluate.weighted_kappa(truth, ["weak", "okay", "weak", "weak"])
    assert near > far  # calling strong weak costs more than calling it okay


def test_thresholds_are_chosen_to_agree_with_the_labels():
    scored = [(90, "strong"), (80, "strong"), (55, "okay"), (50, "okay"), (20, "weak"), (10, "weak")]
    okay_at, strong_at = evaluate.choose_thresholds(scored)
    assert [evaluate.to_fit(s, okay_at, strong_at) for s, _ in scored] == [f for _, f in scored]


@pytest.fixture
def labelled(tmp_path, monkeypatch):
    for name, file in (("PAIRS", "pairs.jsonl"), ("LABELS", "labels.jsonl"), ("PRELABELS", "prelabels.jsonl"),
                       ("SECOND", "second.jsonl")):  # fmt: skip
        monkeypatch.setattr(evalset, name, tmp_path / file)
    pairs = [Pair("p", job, "target", "h") for job in (1, 2, 3, 4)]
    evalset.write_jsonl(evalset.PAIRS, [p.__dict__ for p in pairs])
    evalset.write_jsonl(evalset.PRELABELS, [{"resume": "p", "job": j, "fit": f, "reason": "r"}
                                            for j, f in ((1, "strong"), (2, "okay"), (3, "weak"), (4, "okay"))])  # fmt: skip
    evalset.write_jsonl(evalset.SECOND, [{"resume": "p", "job": j, "fit": f, "reason": "r", "terms": t}
                                         for j, f, t in ((1, "strong", {"Go": True}), (2, "weak", {}),
                                                         (3, "weak", {"Rust": False}))])  # fmt: skip
    return pairs


def test_the_answer_key_uses_agreed_labels_sets_disputes_aside_and_a_person_wins(labelled):
    key = evalset.answer_key()
    assert {k: a.fit for k, a in key.answers.items()} == {("p", 1): "strong", ("p", 3): "weak"}
    assert key.disputed == {("p", 2): ("okay", "weak")}  # left out of scores
    assert ("p", 4) not in key.answers  # only one pass: not in the key
    assert key.provisional and key.terms[("p", 1)] == {"Go": True}

    evalset.save_label(Label("p", 2, "okay"), real=False)  # a person's label settles it
    key = evalset.answer_key()
    assert key.answers[("p", 2)].fit == "okay" and key.answers[("p", 2)].source == evalset.HUMAN
    assert ("p", 2) not in key.disputed


def test_results_carry_ids_and_numbers_never_resume_text(tmp_path, monkeypatch):
    persona = evalset.load_personas()[0]
    pairs = [Pair(persona.id, j, "target", "h") for j in (1, 2)]
    monkeypatch.setattr(evaluate, "_split", lambda part: (pairs, []))
    monkeypatch.setattr(evaluate, "RESULTS", tmp_path)
    monkeypatch.setattr(evalset, "load_postings", lambda: {j: {"id": j, "title": "Engineer", "description": "Python"}
                                                           for j in (1, 2)})  # fmt: skip
    key = evalset.AnswerKey(answers={p.key(): evalset.Answer(f, evalset.CLAUDE_AGREED)
                                     for p, f in zip(pairs, ("strong", "weak"), strict=True)})  # fmt: skip
    monkeypatch.setattr(evalset, "answer_key", lambda measured=None: key)
    result = evaluate.run("baseline", "holdout")
    assert result["labels"] == evaluate.PROVISIONAL and result["pairs"]["scored"] == 2
    saved = (tmp_path / "baseline-holdout.json").read_text(encoding="utf-8")
    assert persona.text[:40] not in saved and json.loads(saved)["system"] == "baseline"
