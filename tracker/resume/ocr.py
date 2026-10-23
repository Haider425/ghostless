"""Read scanned resumes: PDFs that are pictures of text, with no text in them.

Each page is drawn as an image (pypdfium2) and its text recognised by
RapidOCR, a small model that runs on the CPU through ONNX Runtime. Nothing
leaves the machine. The words come back as boxes, which are put back into
lines in reading order.

Optional: `pip install -e ".[ocr]"`. Without it, `available()` is False and
scanned files are reported as unreadable, as before.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

RENDER_SCALE = 2.5  # about 180 dpi: small resume text stays readable
MIN_CONFIDENCE = 0.5
# RapidOCR's English recognition model (Apache-2.0), 9 MB, from
# https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/en_PP-OCRv3_rec_infer.onnx
# The bundled model is the Chinese one, which drops the spaces between English words.
ENGLISH_MODEL = Path.home() / ".cache" / "ghostless" / "ocr" / "en_PP-OCRv3_rec_infer.onnx"


def available() -> bool:
    """The packages and the English model are both here."""
    try:
        import pypdfium2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return ENGLISH_MODEL.exists()


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(rec_model_path=str(ENGLISH_MODEL))


def lines_in_order(boxes: list[tuple[list[list[float]], str, float]]) -> list[str]:
    """OCR results ([corner points], text, confidence) as lines of text, top to
    bottom and left to right. Words whose vertical middles are within half a
    line height of each other share a line."""
    words = []
    for points, text, confidence in boxes:
        if confidence < MIN_CONFIDENCE or not text.strip():
            continue
        ys = [p[1] for p in points]
        xs = [p[0] for p in points]
        words.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text.strip()))
    words.sort()
    lines: list[list[tuple[float, str]]] = []
    centre = height = None
    for middle, h, left, text in words:
        if lines and abs(middle - centre) <= 0.5 * max(height, h):
            lines[-1].append((left, text))
        else:
            lines.append([(left, text)])
            centre, height = middle, h
    return [" ".join(text for _, text in sorted(line)) for line in lines]


def pdf_text(data: bytes) -> str:
    """The text of a scanned PDF, page by page."""
    import pypdfium2 as pdfium

    engine = _engine()
    pages = []
    pdf = pdfium.PdfDocument(data)
    try:
        for page in pdf:
            image = page.render(scale=RENDER_SCALE).to_numpy()
            result, _ = engine(image)
            pages.append("\n".join(lines_in_order(result or [])))
    finally:
        pdf.close()
    return "\n\n".join(pages)
