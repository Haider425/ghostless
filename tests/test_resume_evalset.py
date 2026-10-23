"""The resume evaluation set (eval/resume) and the labelling tool."""

import json
import random
import re
from pathlib import Path

import pytest

from tracker.resume import evalset, label
from tracker.resume.evalset import Label, Pair, Target

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def files(tmp_path, monkeypatch):
    """The set's files in a temporary folder, so tests never touch the real ones."""
    private = tmp_path / "private"
    monkeypatch.setattr(evalset, "PAIRS", tmp_path / "pairs.jsonl")
    monkeypatch.setattr(evalset, "LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(evalset, "SPLIT", tmp_path / "split.json")
    monkeypatch.setattr(evalset, "PRIVATE", private)
    return tmp_path


def test_personas_are_synthetic_and_complete():
    personas = evalset.load_personas()
    assert len(personas) == 100  # 40 in tech, 60 in twelve other fields
    ids = [p.id for p in personas]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)
    for p in personas:
        assert p.target.role in evalset.TARGET_ROLES and p.target.level in evalset.LEVELS and p.target.titles
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", p.text)
        assert emails and all(e.endswith("@example.com") for e in emails), p.id
        phones = re.findall(r"\(?\d{3}\)?[\s.-]\d{3}-\d{4}", p.text)
        assert all("555" in phone for phone in phones), p.id
    assert {p.target.role for p in personas} == set(evalset.TARGET_ROLES)
    assert {p.target.level for p in personas} == set(evalset.LEVELS)
    others = [p for p in personas if p.field]
    assert len(others) == 60 and len({p.field for p in others}) >= 12
    assert all(p.pairs in (3, 6) for p in others)  # 3 to label, 6 for those moving into tech


def test_the_held_out_split_is_frozen_and_reproducible():
    personas = [p.id for p in evalset.load_personas()]
    holdout = evalset.load_split()  # raises if the file was edited
    assert holdout == set(evalset.make_split(personas)["holdout"])
    assert 0.2 <= len(holdout) / len(personas) <= 0.4


def test_adding_personas_never_moves_one_across_the_split(files):
    first = evalset.make_split(["a1", "b2", "c3", "d4", "e5", "f6", "g7", "h8"])
    files.joinpath("split.json").write_text(json.dumps(first))
    grown = evalset.extend_split(
        files / "split.json", ["a1", "b2", "c3", "d4", "e5", "f6", "g7", "h8", "new1", "new2"]
    )
    assert set(first["holdout"]) <= set(grown["holdout"])
    files.joinpath("split.json").write_text(
        json.dumps({"holdout": ["zz"], "sha256": evalset.split_hash(["zz"])})
    )
    with pytest.raises(ValueError, match="change sides"):
        evalset.extend_split(files / "split.json", ["a1"])


def test_every_persona_has_pairs_and_every_pair_a_pre_label():
    pairs = evalset.read_jsonl(evalset.PAIRS)
    assert {row["resume"] for row in pairs} == {p.id for p in evalset.load_personas()}
    prelabels = evalset.load_prelabels()
    assert {(row["resume"], row["job"]) for row in pairs} == set(prelabels)
    assert all(pre.fit in evalset.FITS and pre.reason for pre in prelabels.values())


def test_an_edited_split_is_refused(files):
    files.joinpath("split.json").write_text(
        json.dumps({"holdout": ["a", "b"], "sha256": evalset.split_hash(["a"])})
    )
    with pytest.raises(ValueError, match="must not change"):
        evalset.load_split(files / "split.json")


def test_committed_pairs_cover_every_persona_and_hold_no_posting_text():
    rows = evalset.read_jsonl(evalset.PAIRS)
    personas = {p.id for p in evalset.load_personas()}
    assert {r["resume"] for r in rows} == personas
    assert all(set(r) == {"resume", "job", "source", "text_hash", "candidates"} for r in rows)
    assert all(len(r["text_hash"]) == 16 for r in rows)


def test_private_files_are_ignored_by_git():
    assert "eval/resume/private/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_real_resumes_are_always_held_out_and_never_in_a_repr(files):
    folder = files / "private" / "resumes"
    folder.mkdir(parents=True)
    folder.joinpath("Jane Doe CV.txt").write_text("SECRET RESUME TEXT")
    folder.joinpath("Jane Doe CV.yaml").write_text(
        "target: {role: data, level: mid, location: Toronto, country: CA, remote_ok: true, titles: [analyst]}\n"
    )
    (resume,) = evalset.load_real_resumes(folder, read_file=lambda path: path.read_text())
    assert resume.id == "real-jane-doe-cv" and resume.real and resume.target.role == "data"
    assert evalset.is_holdout(resume, holdout=set())
    assert "SECRET" not in repr(resume)


def test_a_scanned_resume_without_text_is_skipped_not_fatal(files, capsys):
    from tracker.resume.extract import UnreadableResume

    folder = files / "private" / "resumes"
    folder.mkdir(parents=True)
    folder.joinpath("scan.pdf").write_bytes(b"%PDF image only")
    folder.joinpath("typed.txt").write_text("Typed resume")

    def read(path):
        if path.suffix == ".pdf":
            raise UnreadableResume("Almost no text came out of this file.")
        return path.read_text()

    assert [r.id for r in evalset.load_real_resumes(folder, read_file=read)] == ["real-typed"]
    assert "real-scan: skipped" in capsys.readouterr().out


def test_a_scanned_resume_is_read_once_then_from_its_private_cache(files, monkeypatch):
    from tracker.resume import extract, ocr

    folder = files / "private" / "resumes"
    folder.mkdir(parents=True)
    folder.joinpath("resume-1.pdf").write_bytes(b"%PDF a scan")

    def no_text_layer(data, name="", content_type=""):
        raise extract.UnreadableResume("Almost no text came out of this file.")

    reads = []
    monkeypatch.setattr(extract, "extract_text", no_text_layer)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "pdf_text", lambda data: reads.append(1) or "word " * 40)

    first = evalset.load_real_resumes(folder)
    second = evalset.load_real_resumes(folder)
    assert len(reads) == 1  # the slow part ran once
    assert first[0].text == second[0].text
    assert list((folder / ".text").glob("resume-1.*.txt"))  # kept beside it, in the private folder


def _job(job_id, title, level="intern", role="sde", country="CA", text=True, fingerprint=None):
    return {
        "id": job_id,
        "title": title,
        "company": f"Co{job_id}",
        "level": level,
        "role_type": role,
        "countries": [country],
        "has_text": text,
        "fingerprint": fingerprint or f"fp{job_id}",
    }


def test_pairs_are_pooled_from_several_sources_with_text_only():
    target = Target("sde", "intern", "Toronto, ON", "CA", True, ["frontend"])
    jobs = [
        _job(1, "Software Intern"),
        _job(2, "Frontend Intern", text=False),  # a title from a job list: can't be judged
        _job(3, "Frontend Developer Intern"),
        _job(4, "Frontend Developer Intern (repost)", fingerprint="fp3"),  # the same posting again
        _job(5, "Frontend Engineering Intern"),
        _job(6, "Senior Frontend Engineer", level="senior"),
        _job(7, "Frontend Intern", country="US"),
        _job(8, "Data Analyst", role="data"),
    ]
    chosen = dict(evalset.choose_pairs(target, [2, 1], jobs, random.Random(1)))
    assert 2 not in chosen and not ({3, 4} <= set(chosen))
    assert chosen[1] == "baseline"
    assert chosen[6] == "wrong_level" and chosen[7] == "other_country"
    assert "target" in chosen.values() and "random" in chosen.values()
    assert len(chosen) <= 8


def test_labels_are_saved_at_once_and_the_latest_wins(files):
    evalset.save_label(Label("p1", 10, "weak", {"kubernetes": False}), real=False)
    evalset.save_label(Label("p1", 10, "okay"), real=False)
    evalset.save_label(Label("real-x", 11, "strong"), real=True)
    labels = evalset.load_labels()
    assert labels[("p1", 10)].fit == "okay"
    assert (files / "private" / "labels.jsonl").exists()  # real resumes' labels stay private
    assert "real-x" not in (files / "labels.jsonl").read_text()


def test_labelling_goes_round_robin_across_resumes():
    pairs = [Pair("a", 1, "baseline", ""), Pair("a", 2, "target", ""), Pair("b", 3, "baseline", "")]
    assert [p.job for p in evalset.labelling_order(pairs, ["a", "b"])] == [1, 3, 2]


def test_the_labelling_tool_saves_a_fit_and_term_judgements(files, monkeypatch, capsys):
    persona = evalset.load_personas()[0]
    evalset.write_jsonl(
        evalset.PAIRS, [Pair(persona.id, 7, "target", evalset.text_hash("x"), ["react", "pdt"]).__dict__]
    )
    evalset.write_jsonl(
        evalset.PRIVATE / "postings.jsonl",
        [{"id": 7, "company": "Acme", "title": "Frontend Intern", "level": "intern", "role_type": "sde",
          "location": "Toronto", "description": "Requirements\n- React and TypeScript"}],
    )  # fmt: skip
    answers = iter(["s", "1", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label.label(only=persona.id)
    saved = evalset.load_labels()[(persona.id, 7)]
    assert saved.fit == "strong" and saved.terms == {"react": True, "pdt": False}
    assert "1 of 1 pairs labelled" in capsys.readouterr().out
