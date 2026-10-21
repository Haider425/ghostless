"""How much the database sends back, per step of a run and per query.

Neon's free plan caps data transfer (what's read out of the database) at 5 GB
a month, so each run logs what it read. Every connection from `db.connect`
uses `CountingCursor`, which adds up each result as the server sends it: the
values in their text form plus the Postgres protocol's fixed cost per message
(row description, one header per row and per field, the closing messages).
Queries are named after the tracker function that ran them, e.g.
"db.stored_details". New connections are counted too: each costs the server's
greeting and, on Neon, password authentication and a TLS handshake with its
certificates (CONNECTION_BYTES, an estimate; locally the greeting is 419 bytes).
"""

from __future__ import annotations

import sys
import threading
from collections import defaultdict
from contextlib import contextmanager

import psycopg

ROW_OVERHEAD = 7  # DataRow: type byte, length, field count
FIELD_OVERHEAD = 4  # each value's length
COLUMN_OVERHEAD = 19  # RowDescription per column, besides its name
QUERY_OVERHEAD = 30  # ParseComplete, BindComplete, CommandComplete, ReadyForQuery
CONNECTION_BYTES = 4000  # greeting, SCRAM authentication and TLS handshake, on Neon


class Traffic:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.step = "start"
            # step -> [queries, rows, bytes]; (step, query) -> [queries, rows, bytes]
            self.by_step: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
            self.connections: dict[str, int] = defaultdict(int)
            self.by_query: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])

    def add(self, query: str, rows: int, size: int) -> None:
        with self._lock:
            for row in (self.by_step[self.step], self.by_query[(self.step, query)]):
                row[0] += 1
                row[1] += rows
                row[2] += size

    def connected(self) -> None:
        with self._lock:
            self.connections[self.step] += 1

    @property
    def total(self) -> int:
        """Bytes of query results (connections not included)."""
        with self._lock:
            return sum(row[2] for row in self.by_step.values())

    def report(self, top: int = 12) -> dict:
        with self._lock:
            connections = sum(self.connections.values())
            results = sum(row[2] for row in self.by_step.values())
            return {
                "bytes": results + connections * CONNECTION_BYTES,
                "result_bytes": results,
                "connections": connections,
                "steps": {
                    step: {
                        "queries": self.by_step[step][0],
                        "rows": self.by_step[step][1],
                        "connections": self.connections[step],
                        "bytes": self.by_step[step][2] + self.connections[step] * CONNECTION_BYTES,
                    }
                    for step in set(self.by_step) | set(self.connections)
                },
                "queries": [
                    {"step": step, "query": query, "queries": q, "rows": r, "bytes": b}
                    for (step, query), (q, r, b) in sorted(self.by_query.items(), key=lambda kv: -kv[1][2])[
                        :top
                    ]
                ],
            }


traffic = Traffic()


@contextmanager
def step(name: str):
    """Count what's read inside the block under `name` (steps run one after
    another; the worker threads inside a step count towards it)."""
    previous, traffic.step = traffic.step, name
    try:
        yield
    finally:
        traffic.step = previous


def result_size(result) -> tuple[int, int]:
    """(rows, bytes on the wire) of one query's result."""
    if result is None:
        return 0, QUERY_OVERHEAD
    rows, fields = result.ntuples, result.nfields
    size = QUERY_OVERHEAD
    if fields:
        size += 7 + sum(len(result.fname(i) or b"") + 1 + COLUMN_OVERHEAD for i in range(fields))
    per_row = ROW_OVERHEAD + FIELD_OVERHEAD * fields
    for r in range(rows):
        size += per_row
        for c in range(fields):
            value = result.get_value(r, c)
            if value is not None:
                size += len(value)
    return rows, size


def _caller() -> str:
    frame = sys._getframe(2)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module.startswith("tracker.") and module != __name__:
            return f"{module.removeprefix('tracker.')}.{frame.f_code.co_name}"
        frame = frame.f_back
    return "other"


class CountingCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        try:
            return super().execute(query, params, **kwargs)
        finally:
            rows, size = result_size(self.pgresult)
            traffic.add(_caller(), rows, size)

    def executemany(self, query, params_seq, **kwargs):
        params_seq = list(params_seq)
        try:
            return super().executemany(query, params_seq, **kwargs)
        finally:
            traffic.add(_caller(), 0, QUERY_OVERHEAD * len(params_seq))


def render(report: dict) -> str:
    """Markdown for the run summary."""
    lines = [
        f"**Read from the database: about {report['bytes'] / 1e6:.1f} MB** "
        f"({report['result_bytes'] / 1e6:.1f} MB of results, {report['connections']:,} connections)",
        "",
    ]
    lines += ["| Step | Connections | Queries | Rows | MB |", "|---|---:|---:|---:|---:|"]
    for name, row in sorted(report["steps"].items(), key=lambda kv: -kv[1]["bytes"]):
        lines.append(
            f"| {name} | {row['connections']:,} | {row['queries']:,} | {row['rows']:,} | {row['bytes'] / 1e6:.2f} |"
        )
    lines += ["", "| Step | Query | Queries | Rows | MB |", "|---|---|---:|---:|---:|"]
    for row in report["queries"]:
        lines.append(
            f"| {row['step']} | {row['query']} | {row['queries']:,} | {row['rows']:,} | {row['bytes'] / 1e6:.2f} |"
        )
    return "\n".join(lines) + "\n"
