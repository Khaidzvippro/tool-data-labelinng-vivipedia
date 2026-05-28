"""
ref_parser.py — Trích xuất URL từ Ref PDF.

Chỉ dùng PyMuPDF hyperlink annotation (không dùng regex hay pdfplumber).
Lý do: regex bắt nhầm URL inline trong text, pdfplumber thêm noise.
"""
import os
import re
import fitz  # PyMuPDF

EXCLUDED_DOMAINS = [
    "portal.v-app.vn",
    "vivipedia.vn",
    "facebook.com",
    "youtube.com",
    "google.com",
    "twitter.com",
    "zalo.me",
]


def parse_ref(pdf_path: str) -> dict:
    """
    Trích xuất URL từ file Ref PDF qua PyMuPDF hyperlink.
    Trả về: {urls: [...], url_count: int}
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return {"urls": [], "url_count": 0}

    seen, urls = set(), []
    doc = fitz.open(pdf_path)
    for page in doc:
        for link in page.get_links():
            uri = link.get("uri", "").strip()
            if not uri or not uri.startswith("http"):
                continue
            # Bỏ domain nội bộ/mạng xã hội
            if any(d in uri for d in EXCLUDED_DOMAINS):
                continue
            # Strip dấu câu trailing
            uri = uri.rstrip(".,;:")
            if uri not in seen and len(uri) > 10:
                seen.add(uri)
                urls.append(uri)
    doc.close()

    return {"urls": urls, "url_count": len(urls)}


# ── Legacy — main cũ gọi parse_ref(stt, data_dir) ───────────────────────────

def _parse_ref_legacy(stt: str, data_dir: str) -> dict:
    ref_path = os.path.join(data_dir, f"{stt}-Ref.pdf")
    result = parse_ref(ref_path)
    # Legacy trả thêm content (để không break code cũ)
    result["content"] = ""
    return result


def check_files(stt: str, data_dir: str) -> dict:
    errors   = []
    main_pdf = os.path.join(data_dir, f"{stt}.pdf")
    ref_pdf  = os.path.join(data_dir, f"{stt}-Ref.pdf")
    if not os.path.exists(main_pdf):
        errors.append(f"Không tìm thấy file chính: {main_pdf}")
    return {
        "ok":       len(errors) == 0,
        "errors":   errors,
        "main_pdf": main_pdf,
        "ref_pdf":  ref_pdf,
    }


def check_url_coverage(url_count: int, claims_count: int) -> dict:
    threshold = max(1, claims_count - 2)
    ok = url_count >= threshold
    if url_count == 0:
        return {"ok": False, "warning": True,
                "message": "Ref PDF không có URL nào! Claude không thể fact-check."}
    elif not ok:
        missing = threshold - url_count
        return {"ok": False, "warning": True,
                "message": (f"Thiếu nguồn: {url_count} URL / {claims_count} claims "
                            f"(cần ít nhất {threshold}). Thiếu {missing} URL.")}
    return {"ok": True, "warning": False,
            "message": f"URL đủ: {url_count} URL / {claims_count} claims ✓"}
