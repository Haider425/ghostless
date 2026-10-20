"""Conditional reads of the job-board APIs, and Greenhouse's two-step read."""

from datetime import datetime, timezone

import pytest

from tracker.models import Company
from tracker.sources import boards, fetch_jobs, http
from tracker.sources.http import FetchError, Validators

GREENHOUSE = Company("Acme", "greenhouse", "acme")
LIST_URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
FULL_URL = LIST_URL + "?content=true"
OLD = "2026-10-01T10:00:00-04:00"
NEW = "2026-10-15T15:24:46-04:00"


def listed(key, updated=OLD, title="Software Engineer"):
    return {
        "id": key,
        "title": title,
        "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{key}",
        "location": {"name": "Toronto"},
        "updated_at": updated,
        "first_published": OLD,
    }


def with_content(item, text="Build things."):
    return {**item, "content": f"&lt;p&gt;{text}&lt;/p&gt;", "departments": [{"name": "Engineering"}]}


def stored(*keys, updated=OLD):
    when = datetime.fromisoformat(updated)
    return {str(k): (when, f"stored {k}", "Engineering") for k in keys}


class FakeApi:
    """Answers the Greenhouse URLs from a listing; records what was asked."""

    def __init__(self, items, fail=()):
        self.items = items
        self.fail = set(fail)
        self.calls = []

    def get_json_if_changed(self, url, cached=None):
        self.calls.append(url)
        if cached and cached.etag == '"same"':
            return http.NOT_MODIFIED, cached
        return {"jobs": self.items}, Validators(url, '"same"')

    def get_json(self, url):
        self.calls.append(url)
        if url == FULL_URL:
            return {"jobs": [with_content(i, f"full {i['id']}") for i in self.items]}
        key = int(url.split("/jobs/")[1].split("?")[0])
        if key in self.fail:
            raise FetchError("simulated failure")
        return with_content(next(i for i in self.items if i["id"] == key), f"detail {key}")


@pytest.fixture
def api(monkeypatch):
    def install(items, fail=()):
        fake = FakeApi(items, fail)
        monkeypatch.setattr(http, "get_json_if_changed", fake.get_json_if_changed)
        monkeypatch.setattr(http, "get_json", fake.get_json)
        return fake

    return install


def test_plan_greenhouse_fetches_only_new_and_changed():
    items = [listed(1), listed(2, NEW), listed(3)]
    assert boards.plan_greenhouse(items, stored(1, 2)) == ["2", "3"]  # 2 changed, 3 is new


def test_unchanged_postings_keep_their_stored_description(api):
    fake = api([listed(1), listed(2, NEW), listed(3)])
    jobs = boards.fetch_greenhouse(GREENHOUSE, stored=stored(1, 2))
    assert fake.calls == [
        LIST_URL,
        f"{LIST_URL}/2?pay_transparency=true",
        f"{LIST_URL}/3?pay_transparency=true",
    ]
    by_id = {j.external_id: j for j in jobs}
    assert by_id["1"].description == "stored 1" and by_id["1"].department == "Engineering"
    assert by_id["2"].description == "detail 2" and by_id["3"].description == "detail 3"
    assert by_id["2"].source_updated_at == datetime.fromisoformat(NEW)
    assert all(j.description for j in jobs)  # every posting ends with its full text
    assert jobs.validators == Validators(LIST_URL, '"same"')


def test_many_changes_read_the_whole_board_once(api):
    fake = api([listed(i) for i in range(1, 30)])
    jobs = boards.fetch_greenhouse(GREENHOUSE, stored={})  # a first read
    assert fake.calls == [LIST_URL, FULL_URL]
    assert len(jobs) == 29 and all(j.description.startswith("full") for j in jobs)
    assert jobs[0].source_updated_at == datetime.fromisoformat(OLD)


def test_a_failed_detail_falls_back_to_the_whole_board(api):
    fake = api([listed(1), listed(2, NEW), listed(3, NEW)], fail={3})
    jobs = boards.fetch_greenhouse(GREENHOUSE, stored=stored(1, 2, 3))
    assert fake.calls[-1] == FULL_URL
    assert [j.description for j in jobs] == ["full 1", "full 2", "full 3"]


def test_an_unchanged_board_comes_back_empty_and_marked(api):
    fake = api([listed(1)])
    jobs = fetch_jobs(GREENHOUSE, cached=Validators(LIST_URL, '"same"'), stored=stored(1))
    assert jobs.not_modified and list(jobs) == [] and fake.calls == [LIST_URL]


@pytest.mark.parametrize("platform", ["lever", "ashby"])
def test_lever_and_ashby_are_read_conditionally(monkeypatch, platform):
    asked = []

    def fake(url, cached=None):
        asked.append(cached)
        if cached:
            return http.NOT_MODIFIED, cached
        return ([] if platform == "lever" else {"jobs": []}), Validators(url, '"v"')

    monkeypatch.setattr(http, "get_json_if_changed", fake)
    company = Company("Acme", platform, "acme")
    first = fetch_jobs(company)
    assert not first.not_modified and first.validators.etag == '"v"'
    again = fetch_jobs(company, cached=first.validators)
    assert again.not_modified and asked == [None, first.validators]


def test_keep_relevant_keeps_the_not_modified_flags():
    from tracker.classify import keep_relevant
    from tracker.models import JobList

    jobs = JobList(not_modified=True, validators=Validators("u", '"e"'))
    kept = keep_relevant(jobs)
    assert kept.not_modified and kept.validators == Validators("u", '"e"')


def test_parse_greenhouse_still_reads_full_boards():
    [job] = boards.parse_greenhouse({"jobs": [with_content(listed(7))]})
    assert job.description == "Build things." and job.department == "Engineering"
    assert job.posted_at == datetime(2026, 10, 1, 14, tzinfo=timezone.utc)
