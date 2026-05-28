# Quy trình chạy Tool Auto Annotation RAG

Tài liệu mô tả chính xác từng bước tool thực hiện để dễ đối chiếu khi bị lỗi.

---

## 1. Chuẩn bị (Trước khi chạy `main.py`)

Chạy `python login_claude.py` để mở Chrome với remote debugging (port 9222).  
Đăng nhập vào Claude.ai một lần trong cửa sổ này. **Không đóng Chrome** trong suốt phiên làm việc.

---

## 2. Quy trình xử lý tự động (Sau khi bấm RUN trên giao diện)

### Bước 1 — Validate đầu vào (trước khi chạy pipeline)

Tool kiểm tra nhiều tầng trước khi bắt đầu xử lý:

1. **Annotator ID** — bắt buộc phải điền, khuyến nghị định dạng `ANT-xx`
2. **File bài viết** — kiểm tra tồn tại, đúng định dạng PDF, không bị mã hóa, không rỗng/hỏng
3. **File Ref PDF** — tùy chọn, nếu không có tool hỏi có muốn tiếp tục không
4. **Không chọn cùng 1 file** cho cả 2 ô drop zone
5. **Chrome CDP** — ping `localhost:9222` để kiểm tra Chrome đang sẵn sàng

Khi kéo thả file bài viết, tool đọc trước để hiện tiêu đề và số claims ngay lập tức (chạy trên thread riêng, không block UI).

---

### Bước 2 — Parse PDF bài viết (`pdf_parser.py`)

**Detect heading size tự động:**
- Duyệt toàn bộ span trong PDF, thu thập tần suất font size
- Font size xuất hiện nhiều nhất = body size
- Heading size = size lớn hơn body size gần nhất (không hardcode ngưỡng)

**Trích xuất section:**
- Bỏ qua toàn bộ nội dung trước phần "Tóm tắt nhanh" (phần tóm tắt, không phải claim)
- Nhóm paragraph theo heading → mỗi heading là 1 section
- Mỗi paragraph ghi nhận citation number `[1]`, `[2]`... nếu có
- Dừng khi gặp footer bắt đầu bằng "Vivipedia"

**Detect domain tự động:**
- Đếm keyword điểm trong tiêu đề + 5 heading đầu
- Gợi ý domain cho user trong UI (user có thể override)

**Kết quả trả về:** `{title, sections, claims_count, domain_key, domain_name, headings}`

---

### Bước 3 — Parse Ref PDF (`ref_parser.py`)

- Chỉ dùng `page.get_links()` của PyMuPDF — lấy hyperlink annotation thật
- Loại bỏ URL thuộc các domain nội bộ/mạng xã hội: `vivipedia.vn`, `facebook.com`, `youtube.com`, v.v.
- Dedup theo URL chính xác, giữ nguyên thứ tự xuất hiện
- Strip dấu câu trailing (`.`, `,`, `;`, `:`)

**Kết quả trả về:** `{urls: [...], url_count: int}`

> Không dùng regex hay pdfplumber để tránh bắt nhầm URL inline trong text bài viết.

---

### Bước 4 — Build Prompt (`prompt_builder.py`)

Tạo 2 prompt:

**System prompt** — toàn bộ nội dung `rule.md` (rubric SF/SC/HR/SQ, JSON schema, hướng dẫn fact-check).

**Article prompt** (~2000-3000 ký tự) gồm:
- Tiêu đề bài + domain gợi ý (Claude xác nhận hoặc sửa)
- Danh sách claim đã trích xuất (Claude không cần extract lại)
- Danh sách URL nguồn — ưu tiên URL được cite trong bài, tối đa 8 URL
- Yêu cầu trả về JSON thuần, không markdown, không giải thích

URL được liệt kê standalone trên mỗi dòng riêng để Claude.ai nhận diện và tự động fetch.

---

### Bước 5 — Gửi Claude qua Chrome (`claude_automation.py`)

**Kết nối:** Playwright CDP connect vào Chrome đang chạy ở `localhost:9222`.  
Tìm tab `claude.ai` đang mở hoặc tạo tab mới, điều hướng đến `claude.ai/new` để có session sạch.

**Gửi text qua clipboard:**
- Đưa text vào clipboard Windows qua PowerShell với encoding UTF-8 BOM
- Paste vào input box bằng `Ctrl+V` → Claude.ai nhận diện URL và trigger web fetch
- Dùng clipboard thay vì `insert_text()` vì chỉ clipboard mới trigger URL detection của Claude UI

**Gửi System Prompt:** Paste → Send → chờ Claude xác nhận (~60s timeout)

**Gửi Article Prompt:** Paste → Send → chờ Claude xử lý + browse URL (~300s timeout)

**Chờ phản hồi (polling thông minh):**
- Poll mỗi 3s bằng JavaScript kiểm tra nút Stop/spinner còn hiện không
- Nếu text không thay đổi 4 lần liên tiếp → coi như Claude đã xong
- Hard timeout 300s — chụp `debug_screenshot.png` nếu timeout
- Retry tối đa 3 lần nếu lỗi không phải lỗi setup

**Lấy response:** JavaScript quét DOM theo thứ tự ưu tiên:
1. Code block `language-json` cuối cùng
2. `[data-message-author-role="assistant"]` cuối cùng
3. Fallback `.prose` cuối cùng

---

### Bước 6 — Parse JSON (`response_parser.py`)

4 chiến lược parse theo thứ tự ưu tiên:
1. Parse trực tiếp toàn bộ response
2. Lấy từ code fence ` ```json ... ``` `
3. Balanced brace scan — tìm `{` đầu tiên, đếm brace đến khi cân bằng
4. Greedy regex fallback — lấy từ `{` đầu đến `}` cuối

**Normalize sau parse:**
- Chuẩn hóa `fact_check_status`: `XAC_NHAN` → `XAC NHAN`, v.v.
- Ép kiểu float cho SF, SC, HR, SQ, rel, comp

**Validate schema:** Kiểm tra tối thiểu có field `article` và `claims`.

---

### Bước 7 — Merge và ghi Excel (`excel_writer.py`)

**Merge dữ liệu:**  
- Flatten paragraph từ tất cả section thành danh sách claim
- Map 1-1 với claim list từ Claude (theo thứ tự)
- Ghép thêm metadata: title, domain, subdomain, annotator ID, ngày

**Cấu trúc Excel:**

| Dòng | Nội dung | Màu |
|------|----------|-----|
| 1 | Title bar merge A1:O1 | Navy `FF1F3864` |
| 2 | Nhãn nhóm cột (IDENTITY / FACT-CHECK / METRICS / ANNOTATION INFO) | Màu theo nhóm |
| 3 | Tên từng cột | Màu theo nhóm |
| 4 | Dòng template hướng dẫn | Vàng nhạt |
| 5+ | Dữ liệu | Trắng xanh nhạt |

Freeze pane tại `C5` (cố định 2 cột đầu + 4 dòng header).

**Append mode:** Không tạo file mới mỗi lần — load workbook cũ và append từ dòng tiếp theo. Nếu file đang bị khóa (mở trong Excel) → lưu vào file backup với timestamp.

Sau khi ghi xong, Windows Explorer tự mở đến file Excel.

---

### Validate claim sau khi parse (cảnh báo, không dừng pipeline)

- `fact_check_status` phải là 1 trong 6 giá trị hợp lệ
- SF, SC, HR, SQ phải là số trong `[0.0, 1.0]`
- `fact_check_source_url` phải bắt đầu bằng `http` nếu có
- `notes` phải có format `SF=... SC=... HR=... SQ=... TXT=...`

---

## 3. Các điểm hay bị lỗi

| Vấn đề | Nguyên nhân | Dấu hiệu | Cách xử lý |
|--------|-------------|----------|------------|
| 0 claims | PDF là file scan ảnh | Log: "Không trích xuất được claim" | Dùng PDF có text layer |
| Chrome không kết nối | Chưa chạy `login_claude.py` | Log: "port 9222" | Chạy lại `login_claude.py` |
| Response rỗng | Timeout hoặc Claude bị lỗi UI | `debug_screenshot.png` | Xem ảnh, thử chạy lại |
| JSON parse thất bại | Claude trả text thay vì JSON | Log preview 200 ký tự đầu | Tool retry 3 lần tự động |
| PermissionError Excel | File Excel đang mở | Log: "file đang mở" | Đóng Excel, chạy lại |
| Màu Excel trong suốt | Dùng 6-ký-tự hex | Cột không có màu | Dùng 8-ký-tự với prefix `FF` |
| Số claim lệch | Claude detect thêm/bớt claim | Log: cảnh báo "lệch N" | Kiểm tra bài viết, chấp nhận nếu lệch < 3 |
