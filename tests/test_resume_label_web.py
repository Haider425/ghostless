"""The local labelling page (ghostless label-resume --web), the pre-labels, and
the agreement report."""

import json

import pytest

from tracker.resume import evalset, label
from tracker.resume.evalset import Label, Pair, PreLabel

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tracker.resume import label_web  # noqa: E402

PORT = 8765
LOCAL = f"http://127.0.0.1:{PORT}"
POSTING = (
    "About us\nWe make widgets.\n\nRequirements\n- React and TypeScript\n- 2+ years building web apps\n\n"
    "Nice to have\n- GraphQL\n\nBenefits\n- Dental"
)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Two personas, one held out and one for tuning, each with one pair and a pre-label."""
    personas = evalset.load_personas()
    held, tuned = personas[0], personas[1]
    monkeypatch.setattr(evalset, "PAIRS", tmp_path / "pairs.jsonl")
    monkeypatch.setattr(evalset, "LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(evalset, "PRELABELS", tmp_path / "prelabels.jsonl")
    monkeypatch.setattr(evalset, "SPLIT", tmp_path / "split.json")
    monkeypatch.setattr(evalset, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(label, "_all_resumes", lambda: [held, tuned])
    (tmp_path / "split.json").write_text(
        json.dumps({"holdout": [held.id], "sha256": evalset.split_hash([held.id])})
    )
    evalset.write_jsonl(evalset.PAIRS, [Pair(held.id, 1, "target", "h", ["react"]).__dict__,
                                       Pair(tuned.id, 2, "target", "h", ["graphql"]).__dict__])  # fmt: skip
    evalset.write_jsonl(
        evalset.PRIVATE / "postings.jsonl",
        [{"id": i, "company": "Acme", "title": "Frontend Developer", "level": "new_grad", "role_type": "sde",
          "location": "Toronto", "description": POSTING} for i in (1, 2)],
    )  # fmt: skip
    evalset.write_jsonl(evalset.PRELABELS, [
        {"resume": held.id, "job": 1, "fit": "strong", "reason": "SECRET-HELD-OUT-REASON"},
        {"resume": tuned.id, "job": 2, "fit": "okay", "reason": "one real mismatch"},
    ])  # fmt: skip
    client = TestClient(label_web.create_app(PORT), base_url=LOCAL)
    return client, held, tuned


def test_blind_mode_never_sends_a_pre_label(setup):
    client, held, tuned = setup
    for resume, job in ((held.id, 1), (tuned.id, 2)):
        body = client.get("/api/pair", params={"resume": resume, "job": job, "mode": "label"})
        assert body.status_code == 200
        assert body.json()["prelabel"] is None
        assert "SECRET" not in body.text


def test_review_mode_shows_pre_labels_for_tuning_pairs_only(setup):
    client, held, tuned = setup
    listed = client.get("/api/pairs", params={"mode": "review", "part": "holdout"}).json()
    assert [i["resume"] for i in listed["items"]] == [tuned.id]  # held-out pairs are never offered for review
    held_out = client.get("/api/pair", params={"resume": held.id, "job": 1, "mode": "review"})
    assert held_out.json()["prelabel"] is None and "SECRET" not in held_out.text
    tuning = client.get("/api/pair", params={"resume": tuned.id, "job": 2, "mode": "review"}).json()
    assert tuning["prelabel"] == {"fit": "okay", "reason": "one real mismatch"}


def test_a_label_is_saved_to_the_shared_files_with_how_it_was_given(setup):
    client, held, tuned = setup
    ok = client.post(
        "/api/label",
        json={"resume": tuned.id, "job": 2, "fit": "okay", "terms": {"graphql": True}, "note": "  near  miss ",
              "mode": "review"},
    )  # fmt: skip
    assert ok.json() == {"saved": True, "via": "review-accepted"}
    client.post("/api/label", json={"resume": held.id, "job": 1, "fit": "weak", "mode": "review"})
    labels = evalset.load_labels()
    assert labels[(tuned.id, 2)].note == "near miss" and labels[(tuned.id, 2)].terms == {"graphql": True}
    assert labels[(held.id, 1)].via == ""  # a held-out pair can't be "reviewed"
    bad = client.post("/api/label", json={"resume": tuned.id, "job": 2, "fit": "great"})
    assert bad.status_code == 400


def test_only_this_computer_can_use_it(setup):
    client, held, _ = setup
    assert client.get("/", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/", headers={"origin": "https://evil.example"}).status_code == 403
    sneaky = client.post("/api/label", json={"resume": held.id, "job": 1, "fit": "weak"},
                         headers={"origin": "https://evil.example"})  # fmt: skip
    assert sneaky.status_code == 403 and not evalset.load_labels()
    page = client.get("/")
    assert page.status_code == 200 and "Resume labels" in page.text
    assert "http" not in page.text.split("<script>")[1].replace("http://", "")  # no outside scripts or fonts


def test_the_posting_shows_in_full_with_requirements_and_shared_skills_marked():
    shared = {"React", "TypeScript"}
    rendered = label_web.posting_html(POSTING, shared)
    assert (
        '<div class="ln k-required">- <mark class="skill">React</mark> and <mark class="skill">TypeScript</mark></div>'
        in rendered
    )
    assert 'class="ln k-preferred">- GraphQL' in rendered
    assert 'class="ln k-skip">- Dental' in rendered  # nothing is cut off
    assert "&lt;b&gt;" in label_web.resume_html("<b>React</b>", shared)  # text is escaped


def test_agreement_counts_blind_labels_not_accepted_ones():
    pre = {
        ("a", i): PreLabel("a", i, fit, "")
        for i, fit in enumerate(["strong", "okay", "weak", "weak", "okay"])
    }
    labels = [
        Label("a", 0, "strong"),
        Label("a", 1, "weak"),  # disagree
        Label("a", 2, "weak"),
        Label("a", 3, "weak"),
        Label("a", 4, "okay", via="review-accepted"),  # left out: agrees by construction
    ]
    result = evalset.agreement(labels, pre)
    assert (result.pairs, result.agree) == (4, 3)
    assert result.by_label["weak"] == (2, 3) and result.by_label["strong"] == (1, 1)
    assert result.confusion["okay"]["weak"] == 1
    assert 0 < result.kappa < 1
    assert [(lab.job, p.fit) for lab, p in result.disagreements] == [(1, "okay")]


def test_terminal_review_accepts_a_pre_label_with_enter(setup, monkeypatch):
    _, _, tuned = setup
    answers = iter(["", ""])  # Enter accepts; Enter again: no word is fair to add
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label.label(review=True)
    saved = evalset.load_labels()[(tuned.id, 2)]
    assert (saved.fit, saved.via) == ("okay", "review-accepted")


def test_terminal_holdout_labelling_shows_no_pre_label(setup, monkeypatch, capsys):
    _, held, _ = setup
    answers = iter(["w", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label.label(part="holdout")
    assert "SECRET" not in capsys.readouterr().out
    assert evalset.load_labels()[(held.id, 1)].fit == "weak"
