import os

RULE_PATH = os.path.join(os.path.dirname(__file__), "..", "rule.md")


def load_rules() -> str:
    with open(RULE_PATH, encoding="utf-8") as f:
        return f.read()


def build_system_prompt() -> str:
    return load_rules()


def build_article_prompt(article: dict, ref: dict) -> str:
    """
    Build prompt gửi Claude.
    article: dict từ pdf_parser {title, content, claims_count}
    ref: dict từ ref_parser {content, urls, url_count}
    """
    # URLs từ Ref PDF — đánh số để Claude dễ reference
    urls = ref.get("urls", [])
    if urls:
        urls_block = "\n".join(f"[{i+1}] {u}" for i, u in enumerate(urls))
        url_instruction = (
            f"BẮT BUỘC dùng các URL sau (từ Ref PDF) làm fact_check_source_url. "
            f"KHÔNG hallucinate URL khác. Có {len(urls)} URL:"
        )
    else:
        urls_block = "(không có URL nguồn)"
        url_instruction = "Không có URL nguồn — đặt fact_check_source_url = '' và status = 'KHONG TIM THAY' nếu không verify được."

    # Ref content (nguồn tham khảo text)
    ref_content = ref.get("content", "")
    ref_block = ""
    if ref_content:
        ref_block = f"""
---
NỘI DUNG REF (tên nguồn):
{ref_content[:6000]}
"""

    return f"""Bài viết cần annotate:

TIÊU ĐỀ: {article['title']}

NỘI DUNG BÀI:
{article['content'][:12000]}

---
{url_instruction}
{urls_block}
{ref_block}
---
YÊU CẦU:
- fact_check_status phải dùng đúng giá trị: XAC NHAN / LECH / MAU THUAN / OUTDATED / KHONG TIM THAY / BO QUA
- fact_check_source_url phải là URL thật từ danh sách trên, KHÔNG tự bịa URL
- Chỉ trả JSON theo schema. Không markdown. Không giải thích."""
