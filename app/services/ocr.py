"""PDF text extraction with local OCR fallback for scanned decrees."""
import os
import pdfplumber


def extract_pdf(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return '\n'.join(page.extract_text() or '' for page in pdf.pages)


def extract_pdf_with_ocr(path: str) -> tuple[str, float | None]:
    """Return text and mean Tesseract word confidence when OCR was needed."""
    text = extract_pdf(path)
    if len(text.strip()) >= 50:
        return text, None

    try:
        import pytesseract
        from pytesseract import Output
        from pdf2image import convert_from_path, pdfinfo_from_path
    except ImportError as exc:
        raise RuntimeError('Для OCR установите pytesseract и pdf2image') from exc

    page_count = int(pdfinfo_from_path(path).get('Pages') or 0)
    language = os.getenv('TESSERACT_LANG', 'rus+eng')
    chunks: list[str] = []
    confidences: list[float] = []
    for page_number in range(1, page_count + 1):
        images = convert_from_path(path, first_page=page_number, last_page=page_number, dpi=200)
        if not images:
            continue
        try:
            data = pytesseract.image_to_data(images[0], lang=language, output_type=Output.DICT)
            words = [str(word).strip() for word in data.get('text', []) if str(word).strip()]
            chunks.append(' '.join(words))
            for value in data.get('conf', []):
                try:
                    score = float(value)
                    if score >= 0:
                        confidences.append(score / 100)
                except (TypeError, ValueError):
                    continue
        finally:
            images[0].close()
    ocr_text = '\n'.join(chunk for chunk in chunks if chunk).strip()
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return ocr_text, mean_confidence
