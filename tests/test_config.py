import pytest

from tracker.cli import load_dotenv
from tracker.config import load_companies, select


def write(tmp_path, text):
    path = tmp_path / "companies.yaml"
    path.write_text(text)
    return path


def test_load_companies(tmp_path):
    path = write(
        tmp_path,
        """
companies:
  - { name: Stripe, platform: greenhouse, slug: stripe }
  - name: Shopify
    platform: sitemap
    slug: "https://example.com/sitemap.xml"
    region: Remote
""",
    )
    stripe, shopify = load_companies(path)
    assert stripe.board_slug == "stripe" and stripe.region is None
    assert shopify.region == "Remote"


def test_unknown_platform_is_a_clear_error(tmp_path):
    path = write(tmp_path, "companies:\n  - { name: X, platform: taleo, slug: x }\n")
    with pytest.raises(SystemExit, match="unknown platform 'taleo'"):
        load_companies(path)


def test_missing_fields_are_a_clear_error(tmp_path):
    path = write(tmp_path, "companies:\n  - { name: X, platform: lever }\n")
    with pytest.raises(SystemExit, match="missing slug"):
        load_companies(path)


def test_select(tmp_path):
    companies = load_companies(
        write(tmp_path, "companies:\n  - { name: Stripe, platform: greenhouse, slug: stripe }\n")
    )
    assert select(companies, "STRIPE") == companies
    assert select(companies, None) == companies
    with pytest.raises(SystemExit, match="no company named"):
        select(companies, "nope")


def test_repo_companies_file_is_valid():
    assert len(load_companies()) >= 50


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nJT_A=from_file\nJT_B='quoted'\n")
    monkeypatch.setenv("JT_A", "already_set")
    monkeypatch.delenv("JT_B", raising=False)
    load_dotenv(env)
    import os

    assert os.environ["JT_A"] == "already_set"
    assert os.environ["JT_B"] == "quoted"
