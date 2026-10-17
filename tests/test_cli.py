import pytest

from tracker import cli, verify
from tracker.models import Job
from tracker.sources import FetchError


def test_verify_reports_ok_warn_and_fail(monkeypatch, capsys):
    def fake_fetch(company, details=True):
        assert details is False  # verify must stay fast
        if company.name == "Stripe":
            return [Job(external_id="1", title="SWE", url="u")]
        if company.name == "Apple":
            return []
        raise FetchError("rate limited (429)")

    monkeypatch.setattr(verify, "fetch_jobs", fake_fetch)
    for name, expected in [("Stripe", "OK"), ("Apple", "WARN"), ("Microsoft", "FAIL")]:
        problems = verify.run(name)
        line = capsys.readouterr().out
        assert line.startswith(expected), line
        assert name in line
        assert problems == (0 if expected == "OK" else 1)


def test_cli_exits_nonzero_when_sources_fail(monkeypatch):
    monkeypatch.setattr(verify, "run", lambda only: 2)
    with pytest.raises(SystemExit, match="2 source"):
        cli.main(["verify"])


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert "jobtracker" in capsys.readouterr().out
