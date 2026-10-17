"""Keyword-based skill extraction.

Each skill maps to one regex. Ambiguous names (Go, R, C) use stricter
patterns so ordinary English words do not count as skills.
"""

import re

_CI = re.I

SKILL_PATTERNS: dict[str, re.Pattern] = {
    # Languages
    "Python": re.compile(r"\bpython\b", _CI),
    "Java": re.compile(r"\bjava\b(?!\s*script)", _CI),
    "JavaScript": re.compile(r"\bjavascript\b|\bnode(\.js|js)?\b", _CI),
    "TypeScript": re.compile(r"\btypescript\b", _CI),
    "C++": re.compile(r"(?<![\w+])c\+\+(?![\w+])", _CI),
    "C#": re.compile(r"(?<![\w#])c#(?![\w#])|\.net\b", _CI),
    # Case-sensitive "Go", rejected when followed by an ordinary lowercase word
    # ("Go live"), but kept in lists like "Go and Rust" or "Python, Go, Java".
    "Go": re.compile(r"\bgolang\b|\bGo\b(?!\s+(?!and\b|or\b)[a-z])"),
    "Rust": re.compile(r"\brust\b", _CI),
    "Kotlin": re.compile(r"\bkotlin\b", _CI),
    "Swift": re.compile(r"\bswift\b", _CI),
    "Ruby": re.compile(r"\bruby\b|\brails\b", _CI),
    "Scala": re.compile(r"\bscala\b", _CI),
    "SQL": re.compile(r"\bsql\b", _CI),
    # Frameworks
    "React": re.compile(r"\breact(\.js|js)?\b(?!\s+native)", _CI),
    "Angular": re.compile(r"\bangular\b", _CI),
    "Django": re.compile(r"\bdjango\b", _CI),
    "Spring": re.compile(r"\bspring(\s*boot)?\b", _CI),
    "GraphQL": re.compile(r"\bgraphql\b", _CI),
    # Data
    "PostgreSQL": re.compile(r"\bpostgres(ql)?\b", _CI),
    "MySQL": re.compile(r"\bmysql\b", _CI),
    "MongoDB": re.compile(r"\bmongo(db)?\b", _CI),
    "Redis": re.compile(r"\bredis\b", _CI),
    "Spark": re.compile(r"\b(apache\s+)?spark\b|\bpyspark\b", _CI),
    "Kafka": re.compile(r"\bkafka\b", _CI),
    "Airflow": re.compile(r"\bairflow\b", _CI),
    "dbt": re.compile(r"\bdbt\b", _CI),
    "Snowflake": re.compile(r"\bsnowflake\b", _CI),
    "BigQuery": re.compile(r"\bbig\s*query\b", _CI),
    "Pandas": re.compile(r"\bpandas\b", _CI),
    # Cloud and infra
    "AWS": re.compile(r"\baws\b|\bamazon\s+web\s+services\b", _CI),
    "GCP": re.compile(r"\bgcp\b|\bgoogle\s+cloud\b", _CI),
    "Azure": re.compile(r"\bazure\b", _CI),
    "Docker": re.compile(r"\bdocker\b", _CI),
    "Kubernetes": re.compile(r"\bkubernetes\b|\bk8s\b", _CI),
    "Terraform": re.compile(r"\bterraform\b", _CI),
    "Linux": re.compile(r"\blinux\b", _CI),
    "Git": re.compile(r"\bgit\b(?!hub|lab)", _CI),
    "CI/CD": re.compile(r"\bci\s*/\s*cd\b|\bcontinuous\s+(integration|delivery|deployment)\b", _CI),
    # ML
    "PyTorch": re.compile(r"\bpytorch\b", _CI),
    "TensorFlow": re.compile(r"\btensorflow\b", _CI),
    "LLMs": re.compile(r"\bllms?\b|\blarge\s+language\s+models?\b", _CI),
}


def extract_skills(text: str) -> list[str]:
    """Return the sorted list of known skills mentioned in text."""
    if not text:
        return []
    return sorted(name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text))
