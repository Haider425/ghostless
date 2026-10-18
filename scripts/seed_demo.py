"""Fill a local database with realistic demo data for frontend development.

    python scripts/seed_demo.py --yes

Simulates 90 days of daily ingest runs at fictional companies: postings open
and close, some are reposted under new ids, some are evergreen talent pools,
some disclose salaries. Company names are invented on purpose, so demo data
can never be mistaken for real postings.

Refuses to run against a database that already has real data unless --force.
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta, timezone

from tracker import db
from tracker.classify import enrich
from tracker.cli import load_dotenv
from tracker.models import Company, Job
from tracker.skills import extract_skills

# Non-tech roles, which the site hides unless asked, as real employers post them too
OTHER_ROLES = [
    ("Technical Recruiter", ["Communication"]),
    ("Account Executive, Mid-Market", ["Salesforce"]),
    ("Product Designer", ["Figma"]),
    ("Financial Analyst", ["Excel"]),
]

COMPANIES = [
    ("Northwind Systems", "greenhouse"),
    ("Maple Ledger Bank", "workday"),
    ("Lakeshore Analytics", "ashby"),
    ("Boreal Cloud", "greenhouse"),
    ("Harbourline Insurance", "workday"),
    ("Pinecrest Robotics", "lever"),
    ("Granite Payments", "greenhouse"),
    ("Aurora Health Data", "ashby"),
    ("Tundra Games", "lever"),
    ("Riverbend Retail Tech", "workday"),
    ("Cobalt Mobility", "greenhouse"),
    ("Juniper Security", "ashby"),
]

ROLES = [
    ("Software Engineer Intern (Summer 2027)", ["Python", "Java", "Git"]),
    ("Software Developer Co-op (Winter 2027)", ["C#", "SQL", "Azure"]),
    ("Data Engineering Intern", ["Python", "SQL", "Airflow", "Spark"]),
    ("Software Engineer, New Grad", ["Java", "Kubernetes", "AWS"]),
    ("Junior Backend Developer", ["Go", "PostgreSQL", "Docker"]),
    ("Data Engineer I", ["Python", "dbt", "Snowflake", "SQL"]),
    ("Frontend Engineer, New Grad", ["TypeScript", "React", "GraphQL"]),
    ("Machine Learning Engineer Intern", ["Python", "PyTorch", "LLMs"]),
    ("Software Engineer", ["TypeScript", "Node.js", "AWS"]),
    ("Data Scientist", ["Python", "SQL", "Pandas"]),
    ("Senior Software Engineer", ["Java", "Kafka", "Kubernetes"]),
    ("Staff Data Engineer", ["Scala", "Spark", "Kafka"]),
    ("Site Reliability Engineer", ["Linux", "Terraform", "Kubernetes"]),
    ("Full Stack Developer", ["React", "Django", "PostgreSQL"]),
]
TEAMS = ["Payments", "Platform", "Growth", "Risk", "Search", "Infrastructure", "Mobile", "Data Platform"]
LOCATIONS = [
    "Toronto, ON",
    "Toronto, ON",
    "Waterloo, ON",
    "Vancouver, BC",
    "Montréal, QC",
    "Ottawa, ON",
    "Remote - Canada",
    "Calgary, AB",
    "Seattle, WA",
    "New York, NY",
]
DAYS = 90


DUTIES = [
    "Design, build and ship features end to end, from the first sketch to production.",
    "Review code and write clear design documents with your teammates.",
    "Improve the reliability and speed of services that handle millions of requests a day.",
    "Work with product managers and designers to decide what to build next.",
    "Write tests and monitoring so problems are caught before customers notice.",
    "Take part in an on-call rotation once you are settled in, with a mentor alongside.",
]


def description(role: str, skills: list[str], team: str, rng: random.Random) -> str:
    """Structured like a real posting: paragraphs, headings and bullet lists."""
    duties = rng.sample(DUTIES, 4)
    sections = [
        f"About the team\nThe {team} team builds the systems behind products used by millions of Canadians. "
        "We are a small group that values clear writing, careful reviews and shipping often.",
        "What you'll do\n" + "\n".join(f"• {d}" for d in duties),
        "What you'll bring\n"
        + "\n".join(f"• Experience with {skill}" for skill in skills)
        + "\n• Curiosity and a habit of asking good questions",
    ]
    pay = None
    if "Intern" in role or "Co-op" in role:
        low, high = rng.choice([(24, 30), (28, 36), (32, 42)])
        pay = f"The hourly rate for this role is ${low} - ${high} per hour."
    elif rng.random() < 0.7:
        low = rng.randrange(70, 150, 5) * 1000
        pay = f"The salary range for this role is ${low:,} - ${low + rng.choice([15, 20, 30]) * 1000:,} per year."
    notes = [pay] if pay else []
    if rng.random() < 0.6:
        notes.append(
            rng.choice(
                [
                    "This posting is for an existing vacancy.",
                    "We use AI-powered tools to screen applications.",
                    "We do not use AI to screen or select applicants.",
                ]
            )
        )
    if notes:
        sections.append("Pay and hiring details\n" + " ".join(notes))
    return "\n\n".join(sections)


class Posting:
    def __init__(self, ext_id, title, location, text, opens, closes, company):
        self.ext_id, self.title, self.location, self.text = ext_id, title, location, text
        self.opens, self.closes, self.company = opens, closes, company

    def job(self) -> Job:
        job = Job(
            external_id=self.ext_id,
            title=self.title,
            url=f"https://example.com/demo/{self.ext_id}",
            location=self.location,
            description=self.text,
        )
        return enrich(job, extract_skills(f"{self.title} {self.text}"))


def plan(rng: random.Random) -> list[Posting]:
    postings: list[Posting] = []
    for c_index, (name, _) in enumerate(COMPANIES):
        typical = rng.choice([14, 21, 28, 35])
        for n in range(rng.randint(34, 52)):
            role, skills = rng.choice(ROLES) if rng.random() < 0.85 else rng.choice(OTHER_ROLES)
            team = rng.choice(TEAMS)
            title = role if rng.random() < 0.5 else f"{role.split(' (')[0]}, {team}"
            text = description(role, skills, team, rng)
            location = rng.choice(LOCATIONS)
            if rng.random() < 0.12:  # some roles are posted for several cities
                location = " | ".join(sorted(set(rng.sample(LOCATIONS[:7], 2))))
            opens = rng.randint(0, DAYS - 1) if rng.random() < 0.75 else 0
            closes = opens + max(3, int(rng.gauss(typical, typical / 3)))
            ext = f"{c_index}-{n}"
            kind = rng.random()
            if kind < 0.06:  # evergreen talent pool: never closes
                text = (
                    "This posting is not for an existing vacancy. We are building a talent pool.\n\n" + text
                )
                postings.append(Posting(ext, title, location, text, 0, None, name))
            elif kind < 0.16:  # taken down and reposted under a new id
                postings.append(Posting(ext, title, location, text, opens, opens + 20, name))
                postings.append(Posting(f"{ext}-r", title, location, text, opens + 22, None, name))
            elif kind < 0.22:  # left up far longer than normal
                postings.append(Posting(ext, title, location, text, 1, None, name))
            elif kind < 0.25:  # the same role posted twice at once
                postings.append(Posting(ext, title, location, text, opens, closes, name))
                postings.append(Posting(f"{ext}-d", title, location, text, opens, closes, name))
            else:
                postings.append(Posting(ext, title, location, text, opens, closes, name))
    return postings


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--yes", action="store_true", help="really replace the demo data")
    parser.add_argument("--force", action="store_true", help="run even if the database has real data")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("This deletes Ghostless data in DATABASE_URL. Rerun with --yes.")
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL") or raise_missing()

    rng = random.Random(args.seed)
    postings = plan(rng)
    # the last simulated run finished an hour ago
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(days=DAYS, hours=1)

    with db.connect(dsn) as conn:
        existing = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'companies'"
        ).fetchone()[0]
        if existing:
            real = conn.execute(
                "SELECT count(*) FROM companies WHERE board_slug NOT LIKE 'demo-%'"
            ).fetchone()[0]
            if real and not args.force:
                raise SystemExit(
                    f"Refusing: the database holds {real} real companies. Use --force to wipe it."
                )
        conn.execute("DROP MATERIALIZED VIEW IF EXISTS job_signals_mv")
        conn.execute("DROP VIEW IF EXISTS job_signals, hiring_calendar")
        conn.execute(
            "DROP TABLE IF EXISTS events, reports, resumes, saved_jobs, email_tokens, sessions, users, "
            "job_skills, skills, jobs, companies, ingest_runs CASCADE"
        )
        conn.commit()
        db.apply_schema(conn)

        ids = {
            name: db.upsert_company(conn, Company(name, platform, f"demo-{i}"))
            for i, (name, platform) in enumerate(COMPANIES)
        }
        conn.commit()
        for day in range(DAYS + 1):
            run_at = start + timedelta(days=day)
            run_id = db.start_run(conn, run_at)
            seen = new = closed = 0
            for name in ids:
                live = [
                    p.job()
                    for p in postings
                    if p.company == name and p.opens <= day and (p.closes is None or p.closes > day)
                ]
                n_new, n_closed = db.save_company_jobs(conn, ids[name], live, run_at)
                seen, new, closed = seen + len(live), new + n_new, closed + n_closed
            conn.commit()
            db.finish_run(
                conn,
                run_id,
                dict(
                    companies_ok=len(ids),
                    companies_failed=0,
                    jobs_seen=seen,
                    jobs_new=new,
                    jobs_closed=closed,
                    duration_seconds=61.0,
                ),
            )
        db.refresh_signals(conn)
        total = conn.execute("SELECT count(*), count(*) FILTER (WHERE is_active) FROM jobs").fetchone()
    print(f"Demo data ready: {total[0]} postings ({total[1]} open) at {len(ids)} fictional companies.")


def raise_missing():
    raise SystemExit("DATABASE_URL is not set.")


if __name__ == "__main__":
    main()
