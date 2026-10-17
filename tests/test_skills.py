from tracker.skills import extract_skills


def test_common_stack():
    text = "You will build services in Python and Go, deploy with Docker on AWS, and use PostgreSQL."
    assert extract_skills(text) == ["AWS", "Docker", "Go", "PostgreSQL", "Python"]


def test_java_is_not_javascript():
    assert extract_skills("Strong JavaScript skills") == ["JavaScript"]
    assert extract_skills("Experience with Java and Spring Boot") == ["Java", "Spring"]


def test_symbol_languages():
    assert extract_skills("C++ or C# experience") == ["C#", "C++"]


def test_go_does_not_match_english():
    assert "Go" not in extract_skills("You will go above and beyond to help customers.")
    assert "Go" not in extract_skills("Ready to go live")


def test_git_not_github():
    assert "Git" not in extract_skills("Link your GitHub profile")
    assert "Git" in extract_skills("Comfortable with git and code review")


def test_empty():
    assert extract_skills("") == []


def test_go_in_lists():
    assert "Go" in extract_skills("Go and Rust")
    assert "Go" in extract_skills("Python, Go, Java")
