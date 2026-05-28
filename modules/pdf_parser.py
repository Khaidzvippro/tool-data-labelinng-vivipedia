import fitz  # PyMuPDF
import re


_URL_PATTERN = re.compile(r'https?://[^\s\)\]\}\'"<>]+', re.IGNORECASE)


def parse_article(pdf_path: str) -> dict:
    """
    Parse bài chính PDF.
    Returns: {title, content, claims_count, headings}
    """
    doc = fitz.open(pdf_path)
    full_text = []
    headings = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("size", 0) > 13 and span["text"].strip():
                            headings.append(span["text"].strip())
        full_text.append(page.get_text("text"))

    doc.close()
    text = "\n".join(full_text).strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0] if lines else "Unknown"

    claims_count = len(headings) if len(headings) >= 2 else max(1, text.count("\n\n"))

    return {
        "title": title,
        "content": text,
        "claims_count": claims_count,
        "headings": headings,
    }
