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
    # Case-sensitive single letters, only in a list or with "programming"
    "C": re.compile(r"(?<![\w+#/.-])C(?![\w+#])(?=\s*(?:,|/|\)|and\b|or\b|programming|language))|\bC/C\+\+"),
    "R": re.compile(
        r"(?<![\w+#/.-])R(?![\w+#])(?=\s*(?:,|/|\)|and\b|or\b|programming|language|studio))|\bRStudio\b"
    ),
    "PHP": re.compile(r"\bphp\b", _CI),
    "MATLAB": re.compile(r"\bmatlab\b", _CI),
    "Bash": re.compile(r"\bbash\b|\bshell\s+script\w*", _CI),
    "PowerShell": re.compile(r"\bpowershell\b", _CI),
    "HTML/CSS": re.compile(r"\bhtml5?\b|\bcss3?\b", _CI),
    "Verilog": re.compile(r"\bverilog\b", _CI),
    "SystemVerilog": re.compile(r"\bsystem\s*verilog\b", _CI),
    "VHDL": re.compile(r"\bvhdl\b", _CI),
    # Frameworks
    "React": re.compile(r"\breact(\.js|js)?\b(?!\s+native)", _CI),
    "Angular": re.compile(r"\bangular\b", _CI),
    "Django": re.compile(r"\bdjango\b", _CI),
    "Spring": re.compile(r"\bspring(\s*boot)?\b", _CI),
    "GraphQL": re.compile(r"\bgraphql\b", _CI),
    "Vue": re.compile(r"\bvue(\.js|js)?\b", _CI),
    "Next.js": re.compile(r"\bnext\.?js\b", _CI),
    "Node.js": re.compile(r"\bnode(\.js|js)\b|\bnode\b(?=\s*(?:,|/|and\b))", _CI),
    "Express": re.compile(r"\bexpress(\.js|js)\b", _CI),
    "Flask": re.compile(r"\bflask\b", _CI),
    "FastAPI": re.compile(r"\bfast\s*api\b", _CI),
    "ASP.NET": re.compile(r"\basp\.net\b", _CI),
    "React Native": re.compile(r"\breact\s+native\b", _CI),
    "Flutter": re.compile(r"\bflutter\b", _CI),
    "Android": re.compile(r"\bandroid\b", _CI),
    "iOS": re.compile(r"\bios\b"),
    "REST APIs": re.compile(r"\brestful\b|\brest\s*(apis?|services?|endpoints?)\b", _CI),
    "gRPC": re.compile(r"\bgrpc\b", _CI),
    "Microservices": re.compile(r"\bmicro-?services?\b", _CI),
    "Distributed systems": re.compile(r"\bdistributed\s+systems?\b", _CI),
    "Testing": re.compile(
        r"\b(unit|integration|end-to-end|automated)\s+test(s|ing)?\b|\bpytest\b|\bjunit\b|\bjest\b", _CI
    ),
    "Selenium": re.compile(r"\bselenium\b", _CI),
    "Playwright": re.compile(r"\bplaywright\b", _CI),
    "Cypress": re.compile(r"\bcypress\b", _CI),
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
    "NumPy": re.compile(r"\bnumpy\b", _CI),
    "scikit-learn": re.compile(r"\bscikit[\s-]?learn\b|\bsklearn\b", _CI),
    "Databricks": re.compile(r"\bdatabricks\b", _CI),
    "Hadoop": re.compile(r"\bhadoop\b|\bhive\b", _CI),
    "Elasticsearch": re.compile(r"\belastic\s*search\b|\bopensearch\b", _CI),
    "Cassandra": re.compile(r"\bcassandra\b", _CI),
    "DynamoDB": re.compile(r"\bdynamo\s*db\b", _CI),
    "SQL Server": re.compile(r"\bsql\s+server\b|\bssms\b|\bt-sql\b", _CI),
    "Oracle": re.compile(r"\boracle\s+(db|database|sql)\b|\bpl/sql\b", _CI),
    "Tableau": re.compile(r"\btableau\b", _CI),
    "Power BI": re.compile(r"\bpower\s*bi\b", _CI),
    "Excel": re.compile(r"\b(microsoft|ms)\s+excel\b|\bExcel\b(?!\s+(?:at|in|as)\b)"),
    "Statistics": re.compile(r"\bstatistic(s|al)\b", _CI),
    "A/B testing": re.compile(r"\ba/b\s+test\w*|\bexperimentation\b", _CI),
    "ETL": re.compile(r"\betl\b|\belt\b\s+pipelines?", _CI),
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
    "GitHub Actions": re.compile(r"\bgithub\s+actions\b", _CI),
    "Jenkins": re.compile(r"\bjenkins\b", _CI),
    "Ansible": re.compile(r"\bansible\b", _CI),
    "Prometheus": re.compile(r"\bprometheus\b|\bgrafana\b", _CI),
    "Networking": re.compile(r"\btcp/ip\b|\bnetworking\b|\bdns\b|\bhttp/2\b", _CI),
    "Agile": re.compile(r"\bagile\b|\bscrum\b|\bkanban\b", _CI),
    "Jira": re.compile(r"\bjira\b", _CI),
    # ML
    "PyTorch": re.compile(r"\bpytorch\b", _CI),
    "TensorFlow": re.compile(r"\btensorflow\b", _CI),
    "LLMs": re.compile(r"\bllms?\b|\blarge\s+language\s+models?\b", _CI),
    "Machine learning": re.compile(r"\bmachine\s+learning\b|\bML\b"),
    "Deep learning": re.compile(r"\bdeep\s+learning\b|\bneural\s+networks?\b", _CI),
    "NLP": re.compile(r"\bnlp\b|\bnatural\s+language\s+processing\b", _CI),
    "Computer vision": re.compile(r"\bcomputer\s+vision\b|\bopencv\b", _CI),
    "Hugging Face": re.compile(r"\bhugging\s*face\b|\btransformers\s+library\b", _CI),
    "CUDA": re.compile(r"\bcuda\b", _CI),
    "MLOps": re.compile(r"\bmlops\b|\bmlflow\b|\bkubeflow\b", _CI),
    # Hardware and embedded
    "Embedded systems": re.compile(r"\bembedded\s+(systems?|software|c)\b|\bmicrocontrollers?\b", _CI),
    "RTOS": re.compile(r"\brtos\b|\bfreertos\b|\breal-time\s+operating\b", _CI),
    "FPGA": re.compile(r"\bfpgas?\b", _CI),
    "UVM": re.compile(r"\buvm\b", _CI),
    "RTL design": re.compile(r"\brtl\b", _CI),
    "PCB design": re.compile(r"\bpcb\b|\baltium\b|\bkicad\b", _CI),
    # Security
    "Security": re.compile(r"\bcyber\s*security\b|\bowasp\b|\bthreat\s+model\w*|\bsiem\b|\bsplunk\b", _CI),
    "Penetration testing": re.compile(r"\bpenetration\s+test\w*|\bpen\s*test\w*|\bburp\s+suite\b", _CI),
}


def extract_skills(text: str) -> list[str]:
    """Return the sorted list of known skills mentioned in text."""
    if not text:
        return []
    return sorted(name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text))
