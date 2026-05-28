# PRD — AI Browser Automation System for RAG Annotation Pipeline

# 1. Tổng Quan Sản Phẩm

## Tên hệ thống

AI Browser Automation for RAG Annotation

---

## Mục tiêu

Xây dựng hệ thống tự động hóa quy trình annotation dataset RAG bằng cách sử dụng:

- Claude Web (AI reasoning engine)
- Browser automation
- Python orchestration
- PDF parsing
- URL extraction
- Fact-check automation
- Excel generation

Hệ thống cho phép:

```text
PDF bài viết
→ tự extract claim
→ tự lấy URL nguồn
→ tự mở Claude Web
→ tự gửi prompt
→ tự đọc response
→ tự parse kết quả
→ tự xuất Excel annotation hoàn chỉnh
```

---

# 2. Mục Tiêu Kinh Doanh

## Vấn đề hiện tại

Quy trình annotation thủ công:

- tốn thời gian
- phải copy/paste liên tục
- intern phải fact-check tay
- dễ sai format Excel
- khó scale số lượng lớn bài viết

---

## Giải pháp

Hệ thống tự động:

- đọc PDF
- lấy hyperlink thật
- gửi dữ liệu cho Claude Web
- tự động fact-check
- tự sinh file annotation

Giảm:

- thời gian xử lý
- lỗi nhập liệu
- chi phí nhân sự

---

# 3. Kiến Trúc Tổng Thể

```text
                ┌────────────────┐
                │ Prompt Rules   │
                └──────┬─────────┘
                       │
                       ▼
               ┌─────────────────┐
               │ PDF Parser      │
               │ PyMuPDF         │
               └──────┬──────────┘
                      │
      ┌───────────────┼────────────────┐
      ▼                                ▼
┌──────────────┐              ┌────────────────┐
│ Text Extract │              │ URL Extract    │
└──────┬───────┘              └──────┬─────────┘
       │                              │
       └──────────────┬───────────────┘
                      ▼
             ┌─────────────────┐
             │ Claim Splitter  │
             └──────┬──────────┘
                    ▼
          ┌──────────────────────┐
          │ Claude Input Builder │
          └─────────┬────────────┘
                    ▼
          ┌──────────────────────┐
          │ Browser Automation   │
          │ Playwright           │
          └─────────┬────────────┘
                    ▼
          ┌──────────────────────┐
          │ Claude Web           │
          │ Reasoning + Check    │
          └─────────┬────────────┘
                    ▼
          ┌──────────────────────┐
          │ Response Parser      │
          └─────────┬────────────┘
                    ▼
          ┌──────────────────────┐
          │ Excel Generator      │
          │ openpyxl             │
          └──────────────────────┘
```

---

# 4. Functional Requirements

# FR-01 — Upload PDF

## Input

Người dùng upload:

- PDF bài viết
- prompt markdown rules

## Output

Hệ thống lưu file local.

---

# FR-02 — Parse PDF

## Hệ thống phải:

### Extract:

- title
- headings
- body text
- source list
- hyperlinks thật trong PDF

## Công nghệ

```python
PyMuPDF
```

## Output

```json
{
  "title": "...",
  "content": "...",
  "urls": [...]
}
```

---

# FR-03 — Extract Hyperlinks

## Hệ thống phải:

Lấy hyperlink annotation thật trong PDF:

```python
page.get_links()
```

Không dùng OCR text đơn thuần.

## Output

```json
[
  "https://...",
  "https://..."
]
```

---

# FR-04 — Claim Splitter

## Logic

```text
1 block paragraph dưới 1 heading = 1 claim
```

## Rules

- không tách nhỏ
- không gộp block
- giữ nguyên văn

## Output

```json
[
  {
    "claim_id": 1,
    "heading": "...",
    "text": "..."
  }
]
```

---

# FR-05 — Browser Automation

## Hệ thống phải:

Điều khiển Claude Web tự động:

### Các hành động:

- mở browser
- login session
- mở Claude
- paste prompt
- gửi claim
- chờ response
- copy response

## Công nghệ

```text
Playwright
```

---

# FR-06 — Claude Processing

## Claude phải:

### Thực hiện:

- detect domain
- classify risk
- evaluate:
  - SF
  - SC
  - HR
  - SQ
  - TXT
  - Rel
  - Comp

### Fact-check:

- sử dụng URL nguồn
- reasoning từ source content

## Output format

Claude bắt buộc trả về:

```json
{
  "claims": [...],
  "article_evaluation": {...}
}
```

Không markdown.

---

# FR-07 — Fact-check Automation

## Trạng thái hỗ trợ

| Status | Meaning |
|---|---|
| XAC NHAN | verified |
| LECH | partially incorrect |
| MAU THUAN | contradictory |
| OUTDATED | outdated info |
| KHONG TIM THAY | source missing |
| BO QUA | unverifiable/general |

---

# FR-08 — Excel Generation

## Hệ thống phải tạo:

### Sheet 1

```text
Annotation
```

15 cột theo prompt.

### Sheet 2

```text
Article Evaluation
```

13 cột theo prompt.

## Công nghệ

```python
openpyxl
```

---

# FR-09 — Retry System

## Nếu Claude:

- timeout
- crash
- malformed JSON
- rate limit

Hệ thống phải:

- retry
- reload page
- resend prompt

---

# FR-10 — Session Persistence

## Browser session phải được lưu:

```text
claude_profile/
```

để không login lại mỗi lần.

---

# 5. Non-Functional Requirements

# NFR-01 — Performance

| Metric | Target |
|---|---|
| Parse PDF | < 5s |
| Claude response | < 60s |
| Export Excel | < 3s |

---

# NFR-02 — Reliability

Hệ thống phải:

- retry lỗi browser
- detect empty response
- validate JSON

---

# NFR-03 — Scalability

## MVP:

```text
1 bài / lần
```

## Future:

```text
batch multi-PDF
```

---

# NFR-04 — Maintainability

Code phải module-based:

```text
/modules
/services
/utils
```

---

# 6. Technical Stack

| Component | Technology |
|---|---|
| PDF Parser | PyMuPDF |
| Browser Automation | Playwright |
| AI Engine | Claude Web |
| Excel Export | openpyxl |
| Crawl Parser | trafilatura |
| Language | Python 3.11+ |

---

# 7. Folder Structure

```text
project/
│
├── main.py
├── requirements.txt
│
├── prompts/
│   └── annotation_prompt.md
│
├── uploads/
│
├── outputs/
│
├── browser_profile/
│
├── modules/
│   ├── pdf_parser.py
│   ├── url_extractor.py
│   ├── claim_splitter.py
│   ├── claude_automation.py
│   ├── response_parser.py
│   ├── excel_writer.py
│   └── fact_checker.py
│
└── utils/
```

---

# 8. Claude Automation Workflow

```text
START
 ↓
Open Claude
 ↓
Paste system prompt
 ↓
Upload/Paste article data
 ↓
Wait response
 ↓
Extract JSON
 ↓
Validate JSON
 ↓
Generate Excel
 ↓
DONE
```

---

# 9. JSON Schema

## Claim Object

```json
{
  "claim_id": 1,
  "claim": "...",
  "risk": "STANDARD",
  "fact_check_status": "XAC NHAN",
  "source_url": "...",
  "sf": 0.92,
  "sc": 0.88,
  "hr": 0.93,
  "sq": 0.95,
  "txt": "OK",
  "notes": "..."
}
```

---

# 10. MVP Scope

## Included

- PDF parsing
- URL extraction
- Claude automation
- Claim annotation
- Excel export

---

## Excluded

- Multi-user
- Database
- Dashboard
- Queue system
- Cloud deployment

---

# 11. Future Improvements

## v2

- multi-file batch
- Gemini/OpenAI support
- semantic source matching
- auto screenshot evidence
- vector database
- local LLM fallback

---

# 12. Success Criteria

Hệ thống thành công nếu:

- extract đúng ≥90% URL PDF
- generate đúng format Excel
- claim count chính xác
- automation Claude chạy ổn định
- giảm ≥70% thao tác manual intern