"""The run health report, and when discovered Workday boards get their weekly full read."""

from datetime import datetime, timedelta, timezone

from tracker.discovery.run import FULL_READ_EVERY_DAYS, full_read_due
from tracker.health import Health, render, write_step_summary


def test_report_adds_up_per_source():
    h = Health()
    h.record("configured greenhouse", seconds=2.0, seen=10, new=2, closed=1)
    h.record("configured greenhouse", not_modified=True, seconds=0.5, seen=4)
    h.record("configured greenhouse", ok=False, seconds=1.0)
    h.record("discovered workday", seen=3)
    h.guard_caught("Small Co", 0, 3)
    h.guard_caught("Big Co", 5, 40)
    h.boards_registered(4)
    report = h.report()
    assert report["sources"]["configured greenhouse"] == {
        "read": 2,
        "failed": 1,
        "not_modified": 1,
        "seen": 14,
        "new": 2,
        "closed": 1,
        "seconds": 3.5,
    }
    assert [g["board"] for g in report["guarded"]] == ["Big Co", "Small Co"]  # the biggest drops first
    assert report["registered"] == 4

    h.reset()
    assert h.report() == {"sources": {}, "guarded": [], "registered": 0}


def test_render_names_boards_that_returned_nothing():
    h = Health()
    h.record("discovered lever", seen=0)
    h.guard_caught("Small Co", 0, 3)
    text = render(h.report(), "Ingest health")
    assert "| discovered lever | 1 | 0 | 0 | 0 | 0 | 0 | 0 |" in text
    assert "- Small Co: 0 found, 3 open" in text
    assert "No board returned" in render(Health().report())


def test_step_summary_only_on_github(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    write_step_summary(Health().report(), "x")  # nothing to write to: no error
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    write_step_summary(Health().report(), "Ingest health, part 1 of 4")
    assert out.read_text(encoding="utf-8").startswith("### Ingest health, part 1 of 4")


def test_full_reads_are_spread_over_the_week():
    slugs = [f"bank{i}.wd3.myworkdayjobs.com/External" for i in range(700)]
    monday = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
    days = [monday + timedelta(days=d) for d in range(FULL_READ_EVERY_DAYS)]
    per_day = [sum(full_read_due(s, None, day) for s in slugs) for day in days]
    assert sum(per_day) == len(slugs)  # each board exactly one day a week
    assert min(per_day) > 70 and max(per_day) < 130  # about 1/7 each day


def test_full_read_waits_a_week_but_catches_up_when_missed():
    slug = "td.wd3.myworkdayjobs.com/TD_Bank_Careers"
    day = next(
        datetime(2026, 10, 19, tzinfo=timezone.utc) + timedelta(days=d)
        for d in range(7)
        if full_read_due(slug, None, datetime(2026, 10, 19, tzinfo=timezone.utc) + timedelta(days=d))
    )
    assert not full_read_due(slug, day - timedelta(days=1), day)  # read yesterday: not again
    assert full_read_due(slug, day - timedelta(days=7), day)  # its day, a week on
    assert not full_read_due(slug, day - timedelta(days=7), day + timedelta(days=1))  # not its day
    assert full_read_due(slug, day - timedelta(days=9), day + timedelta(days=1))  # overdue: any day
