"""
prompt_builder.py — Build prompt gửi Claude.

Prompt ngắn gọn (~2000-3000 ký tự):
- Tiêu đề + domain gợi ý (script detect, Claude xác nhận/sửa)
- Danh sách claim đã trích xuất (script làm, Claude không cần extract lại)
- Danh sách URL đã check status
- Yêu cầu JSON output
"""
import os

RULE_PATH = os.path.join(os.path.dirname(__file__), "..", "rule.md")


def load_rules() -> str:
    with open(RULE_PATH, encoding="utf-8") as f:
        return f.read()


def build_system_prompt() -> str:
    return load_rules()


def build_article_prompt(article: dict, ref: dict,
                          domain_key: str = "", subdomain: str = "") -> str:
    """
    Build article prompt ngắn gọn.

    article: từ pdf_parser — {title, sections, domain_key, domain_name, ...}
    ref:     từ ref_parser — {urls, url_count}
    domain_key:  script detect (có thể rỗng nếu chưa detect)
    subdomain:   user chọn trong UI (gợi ý, Claude có thể sửa)
    """
    title       = article.get("title", "")
    sections    = article.get("sections", [])
    d_key       = article.get("domain_key") or domain_key or "?"
    d_name      = article.get("domain_name") or d_key
    all_urls    = ref.get("urls", [])

    # Lấy citation numbers từ tất cả paragraph để lọc URL liên quan
    cited_indices = set()
    for sec in sections:
        for para in sec.get("paragraphs", []):
            if isinstance(para, dict):
                for c in para.get("citations", []):
                    if 1 <= c <= len(all_urls):
                        cited_indices.add(c - 1)  # 0-based

    # Nếu có citation → chỉ gửi URL được cite (tối đa 8)
    # Nếu không có citation → gửi tối đa 8 URL đầu
    if cited_indices:
        urls = [all_urls[i] for i in sorted(cited_indices)][:8]
    else:
        urls = all_urls[:8]

    # ── Block domain gợi ý ───────────────────────────────────────────────────
    domain_hint = (
        f"Script tự detect domain: [{d_key}] {d_name}"
        + (f" | Sub-domain gợi ý: {subdomain}" if subdomain else "")
        + "\n→ Xác nhận hoặc sửa lại trong JSON output (domain_key, domain, sub_domain, sub_domain_id)"
    )

    # ── Block claims (script đã trích xuất) ─────────────────────────────────
    claim_lines = []
    claim_idx   = 0
    for sec in sections:
        claim_lines.append(f"\n## {sec['heading']}")
        for para in sec.get("paragraphs", []):
            claim_idx += 1
            text = para["text"] if isinstance(para, dict) else para
            cits = para.get("citations", []) if isinstance(para, dict) else []
            cite_str = f"  [cite: {', '.join(str(c) for c in cits)}]" if cits else ""
            # Giới hạn mỗi claim 400 ký tự để prompt không phình to
            snippet = text[:400] + ("..." if len(text) > 400 else "")
            claim_lines.append(f"[Claim {claim_idx}]{cite_str} {snippet}")

    claims_block = "\n".join(claim_lines) if claim_lines else "(không trích xuất được claim)"
    total_claims = claim_idx

    # ── Block URL nguồn ──────────────────────────────────────────────────────
    if urls:
        # Mỗi URL trên 1 dòng riêng biệt — Claude.ai nhận diện URL standalone để fetch
        url_lines = "\n".join(urls)
        url_section = f"""URL NGUỒN ({len(urls)} URL — hãy mở và đọc từng URL trước khi fact-check):

{url_lines}

Sau khi đọc xong, chỉ dùng các URL trên cho fact_check_source_url — KHÔNG tự bịa URL khác."""
    else:
        url_section = """URL NGUỒN: (không có)
Đặt fact_check_source_url = "" và fact_check_status = "KHONG TIM THAY" cho các claim không verify được."""

    return f"""TIÊU ĐỀ BÀI: {title}

{domain_hint}

---
DANH SÁCH CLAIM ĐÃ TRÍCH XUẤT ({total_claims} claim — dùng đúng danh sách này, KHÔNG trích xuất lại):
{claims_block}

---
{url_section}

---
NHIỆM VỤ: Sau khi đọc các URL trên, trả về JSON theo schema — {total_claims} claim, đúng thứ tự.
Không markdown. Không giải thích. Chỉ JSON thuần."""
