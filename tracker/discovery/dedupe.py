"""Merge postings and boards that were stored twice.

Three ways a posting could end up in the database more than once:

  * the same Workday board registered under two spellings of its site
    ("External" and "external" link to the same board), each read in full
  * Workday links that start with a lowercase language code ("/en-us/...")
    registered as a board named after the language
  * a list-only company whose board is read too, under a different spelling
    of its name, so its list entries weren't recognized as covered

Discovery now prevents all three. This cleans up what's already stored: the
extra boards and their companies are removed, and a list entry that's also on
a company's own board is removed in favour of the board's copy. Anyone who
saved or reported a removed posting is moved to the copy that's kept, so
nothing a person did is lost. Safe to run any number of times.
"""

from __future__ import annotations

import logging

import psycopg

log = logging.getLogger("tracker.discovery")

# a URL without its query, fragment, trailing slash or case, for comparing links
_LINK = "rtrim(lower(split_part(split_part({col}, '#', 1), '?', 1)), '/')"


def merge_duplicates(conn: psycopg.Connection) -> dict[str, int]:
    removed_boards = conn.execute(
        """
        WITH ranked AS (
            SELECT platform, board_slug,
                   row_number() OVER (
                       PARTITION BY platform, lower(board_slug)
                       -- byte order on a tie, whatever the database's locale: the
                       -- capitalised spelling Workday's own links use ("External") wins
                       ORDER BY last_ok DESC NULLS LAST, first_seen, board_slug COLLATE "C"
                   ) AS rank,
                   platform = 'workday' AND split_part(board_slug, '/', 2) ~* '^[a-z]{2}-[a-z]{2}$' AS bogus
            FROM discovered_boards
        )
        DELETE FROM discovered_boards d USING ranked r
        WHERE d.platform = r.platform AND d.board_slug = r.board_slug AND (r.rank > 1 OR r.bogus)
        RETURNING d.platform, d.board_slug
        """
    ).fetchall()

    # companies that belonged to those boards, and list companies' copies of board postings
    conn.execute("CREATE TEMP TABLE dup_companies (id INTEGER PRIMARY KEY) ON COMMIT DROP")
    if removed_boards:
        conn.cursor().executemany(
            """INSERT INTO dup_companies SELECT id FROM companies
               WHERE platform = %s AND board_slug = %s AND origin = 'discovered' ON CONFLICT DO NOTHING""",
            removed_boards,
        )
    conn.execute(
        f"""
        CREATE TEMP TABLE dup_jobs ON COMMIT DROP AS
        WITH links AS (
            SELECT j.id, j.company_id, c.origin, {_LINK.format(col="j.url")} AS link,
                   j.company_id IN (SELECT id FROM dup_companies) AS doomed
            FROM jobs j JOIN companies c ON c.id = j.company_id
        ),
        keepers AS (
            -- for each link, the copy to keep: a company's own board over a list, then the oldest
            SELECT DISTINCT ON (link) link, id AS keeper
            FROM links WHERE NOT doomed
            ORDER BY link, (origin = 'list'), id
        )
        SELECT l.id AS loser, k.keeper
        FROM links l JOIN keepers k ON k.link = l.link
        WHERE l.id <> k.keeper AND (l.doomed OR l.origin = 'list')
        """
    )
    conn.execute(
        """INSERT INTO saved_jobs (user_id, job_id, saved_at, status, notes, updated_at)
           SELECT s.user_id, d.keeper, s.saved_at, s.status, s.notes, s.updated_at
           FROM saved_jobs s JOIN dup_jobs d ON d.loser = s.job_id
           ON CONFLICT (user_id, job_id) DO NOTHING"""
    )
    conn.execute("UPDATE reports r SET job_id = d.keeper FROM dup_jobs d WHERE r.job_id = d.loser")
    jobs = conn.execute("DELETE FROM jobs WHERE id IN (SELECT loser FROM dup_jobs)").rowcount
    jobs += conn.execute(
        "DELETE FROM jobs WHERE company_id IN (SELECT id FROM dup_companies)"
    ).rowcount  # the rest of a duplicate board's postings: copies with no keeper elsewhere
    companies = conn.execute("DELETE FROM companies WHERE id IN (SELECT id FROM dup_companies)").rowcount
    result = {"boards": len(removed_boards), "companies": companies, "jobs": jobs}
    if any(result.values()):
        log.info(
            "merged duplicates: %d boards, %d companies and %d postings removed",
            result["boards"],
            result["companies"],
            result["jobs"],
        )
    return result
