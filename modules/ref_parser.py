import fitz
import re
import os

_URL_PATTERN = re.compile(r'https?://[^\s\)\]\}\'"<>，。、；：！？]+', re.IGNORECASE)


def _extract_urls_pymupdf(pdf_path: str) -> list:
    """PyMuPDF: lấy hyperlink annotation thật."""
    urls = []
    doc = fitz.open(pdf_path)
    for page in doc:
        for link in page.get_links():
            uri = link.get("uri", "")
            if uri.startswith("http"):
                urls.append(uri)
    doc.close()
    return urls


def _extract_urls_regex(text: str) -> list:
    """Regex: bắt URL plain text trong nội dung."""
    return _URL_PATTERN.findall(text)


def _extract_urls_pdfplumber(pdf_path: str) -> list:
    """pdfplumber: extract hyperlinks từ annotations."""
    urls = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                if hasattr(page, 'hyperlinks'):
                    for link in page.hyperlinks:
                        uri = link.get("uri", "")
                        if uri and uri.startswith("http"):
                            urls.append(uri)
    except Exception:
        pass
    return urls


def _merge_urls(all_urls: list) -> list:
    """Deduplicate, clean trailing punctuation."""
    seen = set()
    result = []
    for url in all_urls:
        url = url.rstrip(".,;:!?\"')")
        if url not in seen and len(url) > 10:
            seen.add(url)
            result.append(url)
    return result


def parse_ref(stt: str, data_dir: str) -> dict:
    """
    Tìm và parse file {stt}-Ref.pdf.
    Extract URLs bằng 3 method: PyMuPDF + regex + pdfplumber.
    Returns: {content, urls, url_count} hoặc {} nếu không có file.
    """
    ref_path = os.path.join(data_dir, f"{stt}-Ref.pdf")
    if not os.path.exists(ref_path):
        return {"content": "", "urls": [], "url_count": 0}

    doc = fitz.open(ref_path)
    pages_text = [p.get_text("text") for p in doc]
    doc.close()
    text = "\n".join(pages_text).strip()

    # Merge URLs từ 3 nguồn
    all_urls = []
    all_urls.extend(_extract_urls_pymupdf(ref_path))
    all_urls.extend(_extract_urls_regex(text))
    all_urls.extend(_extract_urls_pdfplumber(ref_path))
    urls = _merge_urls(all_urls)

    return {
        "content": text,
        "urls": urls,
        "url_count": len(urls),
    }


def check_files(stt: str, data_dir: str) -> dict:
    """
    Kiểm tra file tồn tại trước khi chạy pipeline.
    Returns: {ok, errors, main_pdf, ref_pdf}
    """
    errors = []
    main_pdf = os.path.join(data_dir, f"{stt}.pdf")
    ref_pdf = os.path.join(data_dir, f"{stt}-Ref.pdf")

    if not os.path.exists(main_pdf):
        errors.append(f"Không tìm thấy file chính: {main_pdf}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "main_pdf": main_pdf,
        "ref_pdf": ref_pdf,
    }


def check_url_coverage(url_count: int, claims_count: int) -> dict:
    """
    Kiểm tra số URL có đủ cover claims không.
    Ngưỡng: url_count >= claims_count - 2

    Returns: {ok, warning, message}
    """
    threshold = max(1, claims_count - 2)
    ok = url_count >= threshold

    if url_count == 0:
        return {
            "ok": False,
            "warning": True,
            "message": f"Ref PDF không có URL nào! Claude không thể fact-check.",
        }
    elif not ok:
        missing = threshold - url_count
        return {
            "ok": False,
            "warning": True,
            "message": (
                f"Thiếu nguồn: {url_count} URL / {claims_count} claims "
                f"(cần ít nhất {threshold}). "
                f"Thiếu {missing} URL — {missing} claims có thể không verify được."
            ),
        }
    else:
        return {
            "ok": True,
            "warning": False,
            "message": f"URL đủ: {url_count} URL / {claims_count} claims ✓",
        }
