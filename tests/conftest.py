import pytest
import requests

from tracker.sources import http


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never hit real sites: fail loudly if anything tries."""

    def blocked(*args, **kwargs):
        raise AssertionError("a test tried to make a real HTTP request")

    monkeypatch.setattr(requests, "request", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(http, "throttle", http.Throttle(0, {}, sleep=lambda s: None))
