# Vivipedia Annotation Tool

Tool tự động annotation dữ liệu RAG tiếng Việt cho Vivipedia. Đầu vào là 2 file PDF, đầu ra là file Excel chuẩn v10 với đầy đủ các trường annotation.

---

## Yêu cầu

- Python 3.10+
- Google Chrome (bản desktop thường, không cần Chromium riêng)
- Tài khoản Claude.ai đã đăng nhập

---

## Cài đặt

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Cách chạy

### Bước 1 — Mở Chrome với remote debugging (chỉ làm 1 lần mỗi phiên)

```bash
python login_claude.py
```

Cửa sổ Chrome bật lên. Đăng nhập vào [claude.ai](https://claude.ai) nếu chưa. **Không đóng cửa sổ này** trong suốt phiên làm việc.

### Bước 2 — Khởi động giao diện chính

```bash
python main.py
```

### Bước 3 — Sử dụng giao diện

1. Kéo thả (hoặc click chọn) **file bài viết chính** vào ô drop zone bên trái
   - Tool tự đọc tiêu đề, đếm claim, gợi ý domain
2. Kéo thả **file Ref PDF** vào ô drop zone bên phải
3. Kiểm tra/chỉnh **Domain** và **Annotator ID**
4. Bấm **RUN ANNOTATION**

Kết quả được ghi vào `outputs/annotation_output.xlsx`. Windows Explorer tự mở đến file sau khi xong.

---

## Cấu trúc thư mục

```
tool-data-labling/
├── main.py                    # GUI chính (Tkinter)
├── login_claude.py            # Mở Chrome với remote debug port 9222
├── rule.md                    # System prompt cho Claude (rubric + JSON schema)
├── requirements.txt
├── outputs/                   # File Excel kết quả (gitignored)
└── modules/
    ├── pdf_parser.py          # Trích xuất tiêu đề, section, heading, domain
    ├── ref_parser.py          # Trích xuất URL từ Ref PDF (PyMuPDF hyperlink)
    ├── prompt_builder.py      # Build prompt gửi Claude (~2000-3000 ký tự)
    ├── claude_automation.py   # Điều khiển Chrome qua Playwright CDP
    ├── response_parser.py     # Parse JSON từ Claude response
    └── excel_writer.py        # Ghi Excel v10 (4 dòng header, freeze C5)
```

---

## Đầu vào / Đầu ra

| | Chi tiết |
|---|---|
| **Đầu vào** | File PDF bài viết chính + File PDF Ref (chứa hyperlink URL nguồn) |
| **Đầu ra** | `outputs/annotation_output.xlsx` — append mỗi lần chạy |
| **Format Excel** | 4 dòng header, freeze pane tại C5, 15 cột A–O |

### Cột Excel (A–O)

| Cột | Tên | Nguồn |
|-----|-----|-------|
| A | # (STT) | Tự tăng |
| B | Article Title | pdf_parser |
| C | Domain | Claude xác nhận |
| D | Sub-domain | Claude xác nhận |
| E | Sub-domain ID | Claude xác nhận |
| F | Claim | pdf_parser (paragraph) |
| G | Fact-check Status | Claude |
| H | Fact-check Source URL | Claude |
| I | Source Fidelity (SF) | Claude |
| J | Source Coverage (SC) | Claude |
| K | Hallucination Rate (HR) | Claude |
| L | Source Quality (SQ) | Claude |
| M | Annotator Notes | Claude |
| N | Annotator ID | User nhập |
| O | Date | Tự động |

---

## Domain hỗ trợ

| Key | Tên |
|-----|-----|
| law | Pháp luật |
| med | Y tế & Sức khỏe |
| trv | Du lịch |
| fin | Tài chính & Kinh tế |
| gov | Chính trị & Hành chính |
| edu | Giáo dục |
| sci | Khoa học & Công nghệ |
| biz | Kinh doanh & Quản trị |
| cul | Văn hóa & Xã hội |
| his | Lịch sử & Địa lý |
| re | Bất động sản & Xây dựng |
| env | Môi trường & Tài nguyên |
| ent | Thể thao & Giải trí |

---

## Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách fix |
|-----|-------------|----------|
| Không kết nối Chrome (port 9222) | Chrome chưa mở hoặc mở sai cách | Chạy lại `login_claude.py` |
| Không đọc được tiêu đề / 0 claims | PDF là file scan ảnh, không có text layer | Dùng PDF có text layer |
| Claude trả về response rỗng | Timeout hoặc Claude bị lỗi | Xem `debug_screenshot.png`, thử lại |
| Không parse được JSON | Claude trả text thay vì JSON | Tool tự retry 3 lần, nếu vẫn lỗi xem log |
| PermissionError khi ghi Excel | File đang mở trong Excel | Đóng Excel trước khi chạy |
| Màu Excel bị trong suốt | Dùng 6-ký-tự hex thay vì 8-ký-tự | Dùng prefix `FF` (vd: `FF1F3864`) |
