"""Configuration: the database URL and the list of companies to track."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from tracker.models import Company

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def companies_path() -> Path:
    """companies.yaml location: $GHOSTLESS_COMPANIES, then the current
    directory, then the repository root."""
    override = os.environ.get("GHOSTLESS_COMPANIES") or os.environ.get("JOB_TRACKER_COMPANIES")
    if override:
        return Path(override)
    local = Path.cwd() / "companies.yaml"
    return local if local.is_file() else PACKAGE_ROOT / "companies.yaml"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return url


def load_companies(path: Path | None = None) -> list[Company]:
    from tracker.sources import PLATFORMS

    path = path or companies_path()
    if not path.is_file():
        raise SystemExit(f"companies file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}

    companies = []
    for number, entry in enumerate(data.get("companies") or [], start=1):
        missing = [key for key in ("name", "platform", "slug") if not entry.get(key)]
        if missing:
            raise SystemExit(f"{path}: company #{number} is missing {', '.join(missing)}")
        if entry["platform"] not in PLATFORMS:
            raise SystemExit(
                f"{path}: {entry['name']} has unknown platform {entry['platform']!r} "
                f"(expected one of: {', '.join(sorted(PLATFORMS))})"
            )
        companies.append(
            Company(
                name=str(entry["name"]),
                platform=entry["platform"],
                board_slug=str(entry["slug"]),
                region=entry.get("region"),
                domain=entry.get("domain"),
            )
        )
    return companies


def select(companies: list[Company], only: str | None) -> list[Company]:
    """Filter by company name or slug (case-insensitive)."""
    if not only:
        return companies
    wanted = only.lower()
    chosen = [c for c in companies if wanted in (c.name.lower(), c.board_slug.lower())]
    if not chosen:
        raise SystemExit(f"no company named {only!r} in companies.yaml")
    return chosen


def load_lists(path: Path | None = None) -> list:
    """Public job lists to read (the `lists:` section of companies.yaml).

    Without the section, the default SimplifyJobs lists are read; `lists: []`
    turns list reading off.
    """
    from tracker.discovery.lists import DEFAULT_LISTS, JobList

    path = path or companies_path()
    data = (yaml.safe_load(path.read_text()) or {}) if path.is_file() else {}
    if "lists" not in data:
        return list(DEFAULT_LISTS)
    out = []
    for number, entry in enumerate(data.get("lists") or [], start=1):
        if not isinstance(entry, dict) or not entry.get("repo") or "/" not in str(entry["repo"]):
            raise SystemExit(f"{path}: list #{number} needs repo: owner/name")
        out.append(
            JobList(
                repo=str(entry["repo"]),
                branch=str(entry.get("branch", "dev")),
                path=str(entry.get("path", ".github/scripts/listings.json")),
                label=str(entry.get("label", "")),
                level=entry.get("level") if entry.get("level") in ("intern", "new_grad") else None,
            )
        )
    return out
