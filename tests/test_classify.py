import pytest

from tracker.classify import classify_level, classify_role, is_canada, is_remote


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineering Intern (Summer 2027)", "intern"),
        ("Co-op Software Developer", "intern"),
        ("Software Engineer, New Grad", "new_grad"),
        ("Junior Backend Developer", "new_grad"),
        ("Software Engineer I", "new_grad"),
        ("Senior Software Engineer", "senior"),
        ("Staff Data Engineer", "senior"),
        ("Engineering Manager, Payments", "senior"),
        ("Software Engineer", "mid"),
        ("Backend Engineer, Ledger", "mid"),
    ],
)
def test_classify_level(title, expected):
    assert classify_level(title) == expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineer, New Grad", "sde"),
        ("Full Stack Developer", "sde"),
        ("Backend Engineer, Ledger", "sde"),
        ("SWE Intern", "sde"),
        ("Data Engineer", "data_eng"),
        ("Analytics Engineer", "data_eng"),
        ("Senior Data Platform Engineer", "data_eng"),
        ("Data Scientist, Growth", "data"),
        ("Machine Learning Engineer", "ml"),
        ("Deep Learning Software Engineer", "ml"),
        ("Research Scientist, Generative AI", "ml"),
        ("Applied Scientist", "ml"),
        ("Senior ASIC Design Engineer", "hardware"),
        ("GPU Architect", "hardware"),
        ("Hardware Verification Engineer", "hardware"),
        ("Firmware Engineer", "hardware"),
        ("Physical Design Engineer", "hardware"),
        ("Security Engineer", "security"),
        ("Senior Manager, Cybersecurity", "security"),
        ("Site Reliability Engineer", "sde"),
        ("DevOps Engineer", "sde"),
        ("QA Automation Engineer", "sde"),
        ("Member of Technical Staff", "sde"),
        ("Senior Developer, Mainframe", "sde"),
        ("Senior Software Engineer, GPU Drivers", "sde"),
        ("Data Analyst", "data"),
        ("Quantitative Analyst", "data"),
        ("Account Executive", "other"),
        ("Product Designer", "other"),
        ("Technical Recruiter", "other"),
        ("Product Manager, AI Platform", "other"),
        ("Solutions Architect", "other"),
        ("Sales Engineer", "other"),
        ("Branch Teller", "other"),
    ],
)
def test_classify_role(title, expected):
    assert classify_role(title) == expected


@pytest.mark.parametrize(
    "location, expected",
    [
        ("Toronto, Canada", True),
        ("Waterloo, ON", True),
        ("Remote - Canada", True),
        ("Montréal", True),
        ("San Francisco, CA", False),
        ("Ontario, California", True),  # known false positive, documented on purpose
        ("", False),
    ],
)
def test_is_canada(location, expected):
    assert is_canada(location) == expected


def test_is_remote():
    assert is_remote("Remote - US")
    assert is_remote("New York", source_remote=True)
    assert not is_remote("New York")
