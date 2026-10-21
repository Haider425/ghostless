"""Bulk seeding from Common Crawl's URL index (stage B2). The Parquet tests
need the optional `index` extra (pyarrow), which CI installs."""

import gzip
from datetime import datetime, timezone

import pytest

from tracker.discovery import index
from tracker.sources import http
from tracker.sources.http import FetchError


@pytest.mark.parametrize(
    "surt, url",
    [
        ("co,lever,jobs)/acme/123", "https://jobs.lever.co/acme/123"),
        (
            "com,myworkdayjobs,wd5,nvidia)/en-us/external/job/x",
            "https://nvidia.wd5.myworkdayjobs.com/en-us/external/job/x",
        ),
        ("io,greenhouse,boards:443)/figma/jobs/1", "https://boards.greenhouse.io/figma/jobs/1"),
        ("not a surt", None),
    ],
)
def test_surt_to_url(surt, url):
    assert index.surt_to_url(surt) == url


def test_row_groups_that_can_hold_board_urls():
    assert index.overlaps("co,lever)/", "co,lever,jobs)/zzz")  # holds the start of Lever's slice
    assert index.overlaps("com,ashbyhq,a)/", "com,ashbyhq,z)/")  # spans Ashby's slice
    assert index.overlaps("com,myworkdayjobs,wd1,a)/", "com,myworkdayjobs,wd1,b)/")
    assert not index.overlaps("com,blogspot,a)/", "com,blogspot,z)/")
    assert not index.overlaps("cn,gov)/", "cn,weinasi)/")
    assert index.overlaps(None, None)  # no statistics: read it
    assert index.wanted("io,greenhouse,job-boards)/acme/jobs/1") and not index.wanted("io,greenhouse)/blog")


def test_crawl_names_are_iso_weeks_newest_first():
    ids = index.crawl_ids(datetime(2026, 10, 20, tzinfo=timezone.utc), weeks=3)
    assert ids == ["CC-MAIN-2026-43", "CC-MAIN-2026-42", "CC-MAIN-2026-41"]


def test_latest_crawl_takes_the_newest_with_an_index(monkeypatch):
    listing = gzip.compress(
        b"cc-index/table/cc-main/warc/crawl=X/subset=crawldiagnostics/part-0.parquet\n"
        b"cc-index/table/cc-main/warc/crawl=X/subset=warc/part-0.parquet\n"
    )
    asked = []

    def fake(url):
        asked.append(url)
        if "CC-MAIN-2026-41" not in url:
            raise FetchError("not found (404)")
        return listing

    monkeypatch.setattr(index, "crawl_ids", lambda: ["CC-MAIN-2026-43", "CC-MAIN-2026-42", "CC-MAIN-2026-41"])
    monkeypatch.setattr(http, "get_bytes", fake)
    crawl, files = index.latest_crawl()
    assert crawl == "CC-MAIN-2026-41" and len(asked) == 3
    assert files == [index.MIRROR + "cc-index/table/cc-main/warc/crawl=X/subset=warc/part-0.parquet"]


# ---------- reading an index file (pyarrow) ----------


@pytest.fixture
def index_file(tmp_path, monkeypatch):
    """A small index file shaped like Common Crawl's: sorted by url_surtkey, in
    row groups, served through (fake) range requests that are counted."""
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    keys = sorted(
        [f"com,acme)/page{i}" for i in range(50)]
        + [f"co,lever,jobs)/acme/{i}" for i in range(3)]
        + ["co,lever,jobs)/beta-labs/9", "co,lever,jobs)/"]
        + [f"com,myworkdayjobs,wd3,td)/en-us/td_bank_careers/job/{i}" for i in range(2)]
        + [f"org,example)/x{i}" for i in range(50)]
    )
    table = pa.table({"url_surtkey": keys, "url": [index.surt_to_url(k) for k in keys]})
    path = tmp_path / "part-00000.parquet"
    pq.write_table(table, path, row_group_size=20)  # several row groups, most without board URLs
    data = path.read_bytes()
    calls = []

    def get_range(url, start, end):
        calls.append((start, end))
        return data[start : end + 1], len(data)

    monkeypatch.setattr(http, "get_range", get_range)
    return calls, pq.ParquetFile(path).metadata.num_row_groups


def test_reads_only_row_groups_that_can_hold_board_urls(index_file):
    calls, groups = index_file
    links, read, total = index.board_urls_in("https://mirror.example/part-00000.parquet")
    assert total == groups and 0 < read < groups
    assert "https://jobs.lever.co/acme/0" in links and "https://jobs.lever.co/beta-labs/9" in links
    assert all("acme)/page" not in link for link in links)


def test_find_boards_turns_links_into_boards(index_file):
    boards, counts = index.find_boards(["https://mirror.example/part-00000.parquet"])
    assert set(boards) == {
        ("lever", "acme"),
        ("lever", "beta-labs"),
        ("workday", "td.wd3.myworkdayjobs.com/td_bank_careers"),
    }  # "jobs.lever.co/" alone is no board
    assert counts["files"] == 1 and counts["urls"] == 7  # six job links and the bare jobs.lever.co/


def test_an_unreadable_file_is_skipped(monkeypatch):
    def broken(url, start, end):
        raise FetchError("server error (503)")

    pytest.importorskip("pyarrow")
    monkeypatch.setattr(http, "get_range", broken)
    boards, counts = index.find_boards(["https://mirror.example/x.parquet"])
    assert boards == {} and counts["files_failed"] == 1
