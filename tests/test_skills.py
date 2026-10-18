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


def test_single_letter_languages_need_context():
    assert {"C", "R"} <= set(extract_skills("Languages: Python, C, R and SQL"))
    assert "C" not in extract_skills("Plan C is our backup")
    assert "R" not in extract_skills("R&D team")


def test_ordinary_words_are_not_skills():
    text = "You'll excel at teamwork. The rest of the team will support you."
    assert extract_skills(text) == []


def test_hardware_ml_and_data_tools():
    text = (
        "RTL design in SystemVerilog with UVM on FPGA; CUDA kernels; Power BI and Microsoft Excel dashboards"
    )
    assert {"SystemVerilog", "UVM", "FPGA", "RTL design", "CUDA", "Power BI", "Excel"} <= set(
        extract_skills(text)
    )
