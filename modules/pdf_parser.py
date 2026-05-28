"""
pdf_parser.py — Trích xuất nội dung bài viết từ PDF.

Logic lấy từ script3.py (e:\\a\\toolVsf):
- detect_heading_size: tần suất font size → tự tìm ngưỡng heading
- extract_sections: bỏ "Tóm tắt nhanh", nhóm paragraph theo heading
- extract_article_title: span đầu size >= 14pt trang 1
- detect_domain: keyword scoring từ tiêu đề + heading
"""
import re
from collections import Counter
import fitz  # PyMuPDF

HEADING_SIZE_FALLBACK = 16.5
SKIP_SECTIONS = {"Tóm tắt nhanh"}

DOMAIN_MAP = {
    "law": "Pháp luật",
    "med": "Y tế & Sức khỏe",
    "trv": "Du lịch",
    "fin": "Tài chính & Kinh tế",
    "gov": "Chính trị & Hành chính",
    "edu": "Giáo dục",
    "sci": "Khoa học & Công nghệ",
    "biz": "Kinh doanh & Quản trị",
    "cul": "Văn hóa & Xã hội",
    "his": "Lịch sử & Địa lý",
    "re":  "Bất động sản & Xây dựng",
    "env": "Môi trường & Tài nguyên",
    "ent": "Thể thao & Giải trí",
}

_DOMAIN_KEYWORDS = {
    "law": ["luật","nghị định","thông tư","quyết định","pháp lý","pháp luật",
            "hành chính","khiếu nại","tố cáo","xử phạt","thủ tục","hồ sơ",
            "giấy phép","đăng ký","công chứng","thuế","hải quan","tư pháp",
            "điều khoản","hiệu lực","văn bản","quy định"],
    "med": ["bệnh","triệu chứng","điều trị","thuốc","vaccine","tiêm",
            "bác sĩ","bệnh viện","y tế","sức khỏe","phòng ngừa","chẩn đoán",
            "dược","liều","phẫu thuật","xét nghiệm","ung thư","tiểu đường",
            "huyết áp","tim mạch","nhi khoa","sản khoa"],
    "trv": ["du lịch","điểm đến","tham quan","vé","giờ mở cửa","khách sạn",
            "tour","lữ hành","visa","hộ chiếu","đặt phòng","ẩm thực",
            "đặc sản","di tích","danh lam","thắng cảnh","resort","lịch trình"],
    "fin": ["tài chính","ngân hàng","lãi suất","đầu tư","chứng khoán",
            "cổ phiếu","tín dụng","vay","bảo hiểm","kinh tế vĩ mô"],
    "gov": ["chính phủ","bộ","ủy ban","hội đồng nhân dân","chính trị",
            "ngoại giao","quan hệ quốc tế"],
}


# ─────────────────────────────────────────────────────────────────────────────

def _detect_heading_size(pdf_path: str) -> float:
    doc = fitz.open(pdf_path)
    size_counts: Counter = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    t = span["text"].strip()
                    if not t or ord(t[0]) > 0xE000:
                        continue
                    size_counts[round(span["size"], 1)] += 1
    doc.close()
    if not size_counts:
        return HEADING_SIZE_FALLBACK
    body_size = size_counts.most_common(1)[0][0]
    candidates = sorted(
        [s for s, cnt in size_counts.items() if s > body_size and cnt >= 2],
        reverse=True,
    )
    if candidates:
        return candidates[0]
    candidates = sorted([s for s in size_counts if s > body_size], reverse=True)
    return candidates[0] if candidates else HEADING_SIZE_FALLBACK


def _extract_article_title(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    page = doc[0]
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                if span["size"] >= 14 and span["text"].strip():
                    doc.close()
                    return span["text"].strip()
    doc.close()
    return "Untitled"


def _extract_sections(pdf_path: str) -> list[dict]:
    heading_size = _detect_heading_size(pdf_path)

    def is_heading(span):
        return abs(span["size"] - heading_size) < 0.5

    def is_footer(text):
        return bool(re.match(r"^Vivipedia\s", text))

    doc = fitz.open(pdf_path)
    raw_blocks = []
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            block_text, block_is_heading = "", False
            for line in b["lines"]:
                for span in line["spans"]:
                    t = span["text"].strip()
                    if not t or ord(t[0]) > 0xE000:
                        continue
                    if is_heading(span):
                        block_is_heading = True
                    block_text += t + " "
            block_text = block_text.strip()
            if block_text:
                raw_blocks.append({"text": block_text, "is_heading": block_is_heading})
    doc.close()

    # Bắt đầu sau "Tóm tắt nhanh"
    start_idx = 0
    for i, b in enumerate(raw_blocks):
        if b["is_heading"] and b["text"].strip() in SKIP_SECTIONS:
            start_idx = i + 1
            break

    sections, cur_heading, cur_paras = [], None, []
    para_buffer = ""

    def flush():
        nonlocal para_buffer
        raw = para_buffer.strip()
        if raw:
            citations = [int(x) for x in re.findall(r"\[(\d+)\]", raw)]
            clean = re.sub(r"(\s*\[\d+\])+\s*$", "", raw).strip()
            if clean:
                cur_paras.append({"text": clean, "citations": citations})
        para_buffer = ""

    for b in raw_blocks[start_idx:]:
        if is_footer(b["text"]):
            break
        if b["is_heading"]:
            flush()
            if cur_heading is not None:
                sections.append({"heading": cur_heading, "paragraphs": cur_paras})
            cur_heading = b["text"].strip()
            cur_paras   = []
            para_buffer = ""
        else:
            para_buffer += " " + b["text"]
            if re.search(r"\[\d+\]\s*$", b["text"]):
                flush()

    flush()
    if cur_heading is not None and cur_paras:
        sections.append({"heading": cur_heading, "paragraphs": cur_paras})

    return sections


def _detect_domain(title: str, sections: list[dict]) -> str:
    text = title.lower()
    for sec in sections[:5]:
        text += " " + sec["heading"].lower()
    scores = {dk: 0 for dk in _DOMAIN_KEYWORDS}
    for dk, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[dk] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "law"


# ─────────────────────────────────────────────────────────────────────────────

def parse_article(pdf_path: str) -> dict:
    """
    Parse bài viết chính từ PDF.
    Trả về:
      title       — tiêu đề bài
      sections    — [{heading, paragraphs: [{text, citations}]}]
      claims_count — tổng số paragraph (= số claim)
      domain_key  — law / med / trv / ...
      domain_name — tên hiển thị domain
      headings    — danh sách tiêu đề heading
    """
    title    = _extract_article_title(pdf_path)
    sections = _extract_sections(pdf_path)
    domain_key = _detect_domain(title, sections)

    headings = [s["heading"] for s in sections]
    claims_count = sum(len(s["paragraphs"]) for s in sections)
    if claims_count == 0:
        claims_count = len(headings) if headings else 1

    return {
        "title":        title,
        "sections":     sections,
        "claims_count": claims_count,
        "domain_key":   domain_key,
        "domain_name":  DOMAIN_MAP.get(domain_key, domain_key),
        "headings":     headings,
        # full text cho legacy prompt builder
        "content":      "\n".join(
            s["heading"] + "\n" + "\n".join(p["text"] for p in s["paragraphs"])
            for s in sections
        ),
    }
