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
    assert "ghostless" in capsys.readouterr().out


def test_the_pipeline_runs_without_the_api_extras():
    """The daily workflow installs only the core package: ingest must not need argon2, FastAPI and so on."""
    import subprocess
    import sys

    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('argon2', 'fastapi', 'uvicorn', 'pypdf', 'docx', 'multipart', 'psycopg_pool'):\n"
        "            raise ImportError(name)\n"
        "sys.meta_path.insert(0, Block())\n"
        "import tracker.ingest, tracker.discovery.run, tracker.cli\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.stdout.strip() == "ok", result.stderr
