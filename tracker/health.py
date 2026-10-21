"""The health report of an ingest run: what each source did, and what looked wrong.

Every part of the pipeline records into `current` as it goes. At the end of a
run the report is stored in `ingest_runs.health`, printed by `ghostless
health`, and written to the GitHub Actions run summary when there is one.

Per source ("configured greenhouse", "discovered workday", ...): boards read,
failed and answered 304, seconds spent, and postings seen, new and closed.
Beyond that: boards whose read the suspicious-drop guard didn't trust (a site
returning nothing, or a small fraction of what was open), and how many new
boards the job lists led to.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from pathlib import Path

COUNTS = ("read", "failed", "not_modified", "seen", "new", "closed")


class Health:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.sources: dict[str, dict[str, float]] = defaultdict(
            lambda: dict.fromkeys(COUNTS + ("seconds",), 0)
        )
        self.guarded: list[dict] = []
        self.registered = 0
        self.notes: list[str] = []

    def record(
        self,
        source: str,
        *,
        ok: bool = True,
        not_modified: bool = False,
        seconds: float = 0.0,
        seen: int = 0,
        new: int = 0,
        closed: int = 0,
    ) -> None:
        with self._lock:
            row = self.sources[source]
            row["read" if ok else "failed"] += 1
            row["not_modified"] += int(not_modified)
            row["seconds"] += seconds
            row["seen"] += seen
            row["new"] += new
            row["closed"] += closed

    def guard_caught(self, board: str, found: int, open_before: int) -> None:
        with self._lock:
            self.guarded.append({"board": board, "found": found, "open": open_before})

    def note(self, text: str) -> None:
        """A line for the report, under the table."""
        with self._lock:
            self.notes.append(text)

    def boards_registered(self, count: int) -> None:
        with self._lock:
            self.registered += count

    def report(self) -> dict:
        with self._lock:
            return {
                "sources": {
                    name: {k: (round(v, 1) if k == "seconds" else int(v)) for k, v in row.items()}
                    for name, row in sorted(self.sources.items())
                },
                "guarded": sorted(self.guarded, key=lambda g: -g["open"]),
                "registered": self.registered,
                "notes": list(self.notes),
            }


current = Health()


def render(report: dict, title: str = "Ingest health") -> str:
    """The report as Markdown, for a terminal or the GitHub run summary."""
    lines = [f"### {title}", ""]
    sources = report.get("sources") or {}
    if sources:
        lines += [
            "| Source | Read | Failed | Unchanged (304) | Seconds | Seen | New | Closed |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for name, row in sources.items():
            lines.append(
                f"| {name} | {row['read']} | {row['failed']} | {row['not_modified']} | {row['seconds']:.0f} "
                f"| {row['seen']:,} | {row['new']:,} | {row['closed']:,} |"
            )
    else:
        lines.append("Nothing was read.")
    for text in report.get("notes") or []:
        lines += ["", text]
    guarded = report.get("guarded") or []
    lines += ["", f"New boards found through the job lists: {report.get('registered', 0)}", ""]
    if guarded:
        lines.append(
            f"**{len(guarded)} boards returned far fewer postings than were open, so nothing was closed:**"
        )
        lines.append("")
        for g in guarded[:25]:
            lines.append(f"- {g['board']}: {g['found']} found, {g['open']} open")
        if len(guarded) > 25:
            lines.append(f"- and {len(guarded) - 25} more")
    else:
        lines.append("No board returned suspiciously few postings.")
    if report.get("database"):
        from tracker import dbtraffic

        lines += ["", dbtraffic.render(report["database"])]
    return "\n".join(lines) + "\n"


def write_step_summary(report: dict, title: str) -> None:
    """Append the report to the GitHub Actions run summary, when running there."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as out:
            out.write(render(report, title) + "\n")
