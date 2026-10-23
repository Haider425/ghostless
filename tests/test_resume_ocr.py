"""Scanned resumes: putting recognised words back in reading order (tracker/resume/ocr.py).

The OCR itself needs the optional `ocr` extra and a model file, so only the
ordering is tested here; it runs everywhere."""

from tracker.resume import ocr


def box(x, y, w=100, h=20):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_words_come_back_in_lines_top_to_bottom_left_to_right():
    results = [
        (box(300, 52), "Toronto", 0.98),  # same line as the name, a little lower
        (box(10, 50), "Alex Rivera", 0.99),
        (box(10, 120), "SKILLS", 0.97),
        (box(10, 160), "Python, SQL", 0.95),
        (box(200, 85), "alex@example.com", 0.96),
        (box(10, 85), "416-555-0101", 0.96),
    ]
    assert ocr.lines_in_order(results) == [
        "Alex Rivera Toronto",
        "416-555-0101 alex@example.com",
        "SKILLS",
        "Python, SQL",
    ]


def test_low_confidence_and_empty_words_are_dropped():
    results = [(box(10, 10), "Experience", 0.99), (box(10, 40), "~~", 0.2), (box(10, 70), "  ", 0.9)]
    assert ocr.lines_in_order(results) == ["Experience"]


def test_without_the_packages_or_model_scans_stay_unreadable(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "ENGLISH_MODEL", tmp_path / "missing.onnx")
    assert ocr.available() is False
