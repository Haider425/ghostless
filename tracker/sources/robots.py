"""robots.txt compliance (RFC 9309).

Python's built-in urllib.robotparser does not support `*` and `$` wildcards,
which real sites use (for example Google's careers rules), so this module
implements the matching rules itself:

  * the group naming our user agent wins over the `*` group
  * a rule's path pattern may contain `*` (any characters) and a trailing `$` (end)
  * the longest matching pattern wins; on a tie, Allow wins
  * robots.txt missing (4xx): everything allowed
  * robots.txt unreachable (5xx / network error): everything disallowed
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# fetcher(url) -> (status_code, body). status_code 0 means a network error.
Fetcher = Callable[[str], tuple[int, str]]


@dataclass
class Rules:
    allow_all: bool = False
    disallow_all: bool = False
    rules: list[tuple[bool, str, re.Pattern]] = field(default_factory=list)  # (allow, raw, regex)

    def allowed(self, path: str) -> bool:
        if self.allow_all:
            return True
        if self.disallow_all:
            return False
        best: tuple[int, bool] | None = None  # (pattern length, allow)
        for allow, raw, regex in self.rules:
            if regex.match(path):
                candidate = (len(raw), allow)
                if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                    best = candidate
        return True if best is None else best[1]


def _pattern_to_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(regex + ("$" if anchored else ""))


def parse(text: str, agent: str) -> Rules:
    """Parse robots.txt and return the rules that apply to `agent`."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    current_agents: list[str] = []
    current_rules: list[tuple[bool, str]] = []
    in_rules = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:  # a new group starts
                groups.append((current_agents, current_rules))
                current_agents, current_rules, in_rules = [], [], False
            current_agents.append(value.lower())
        elif key in ("allow", "disallow"):
            in_rules = True
            if value:  # an empty Disallow means "allow everything"
                current_rules.append((key == "allow", value))
    if current_agents:
        groups.append((current_agents, current_rules))

    agent = agent.lower()
    specific = [r for agents, r in groups if any(a != "*" and a in agent for a in agents)]
    chosen = specific or [r for agents, r in groups if "*" in agents]
    merged = [rule for rules in chosen for rule in rules]
    return Rules(rules=[(allow, p, _pattern_to_regex(p)) for allow, p in merged])


class RobotsCache:
    """Fetches each host's robots.txt once per run and answers `allowed(url)`."""

    def __init__(self, agent: str, fetcher: Fetcher):
        self.agent = agent
        self.fetcher = fetcher
        self._cache: dict[str, Rules] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _rules_for(self, scheme: str, host: str) -> Rules:
        key = f"{scheme}://{host}"
        if key in self._cache:
            return self._cache[key]
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:  # requests running at once fetch a host's robots.txt only once
            return self._fetch(key)

    def _fetch(self, key: str) -> Rules:
        if key not in self._cache:
            status, body = self.fetcher(f"{key}/robots.txt")
            if 200 <= status < 300:
                self._cache[key] = parse(body, self.agent)
            elif 400 <= status < 500:
                self._cache[key] = Rules(allow_all=True)
            else:
                self._cache[key] = Rules(disallow_all=True)
        return self._cache[key]

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        if path == "/robots.txt":
            return True
        return self._rules_for(parts.scheme, parts.netloc).allowed(path)
