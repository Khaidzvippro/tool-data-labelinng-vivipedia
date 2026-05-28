# Quy trình chạy Tool Auto Annotation RAG

Đây là tài liệu mô tả chính xác từng bước mà Tool thực hiện ngầm để bạn dễ dàng đối chiếu khi bị lỗi.

## 1. Chuẩn bị (Trước khi chạy `main.py`)
- Tool **Chrome thật** được mở qua lệnh `python login_claude.py`.
- Trình duyệt bật lên ở chế độ gỡ lỗi (port 9222). Bạn login vào Claude 1 lần ở cửa sổ này và **không được đóng Chrome**.

---

## 2. Quy trình xử lý tự động (Sau khi bấm RUN trên giao diện)

### Bước 1: Kiểm tra file input
- Đọc số STT bạn nhập (VD: `1`).
- Check xem file `data/1.pdf` và `data/1-Ref.pdf` có tồn tại không. 
- Đếm số lượng Claim (dựa vào cấu trúc heading của 1.pdf).
- Đếm số lượng Link URL (trong file 1-Ref.pdf). 
- *Check cảnh báo*: Nếu số URL < (số Claim - 2) thì bung hộp thoại (Warning Dialog) hỏi bạn có muốn tiếp tục chạy không.

### Bước 2: Tự động ghép Prompt
- **System Prompt:** Gộp toàn bộ nội dung trong file `rule.md` (role, nhiệm vụ, json schema, thang điểm...).
- **Article Prompt:** Gộp Tiêu đề bài viết + Nội dung bài viết + Toàn bộ 16 URLs trích từ file Ref + Nội dung chữ của file Ref.

### Bước 3: Điều khiển Chrome gửi System Prompt (Rule)
- Tool tự động kết nối vào Chrome đã mở ở port 9222.
- Kiểm tra xem tab `claude.ai/new` đang mở chưa, nếu chưa thì tạo tab mới. Đảm bảo đây là 1 session hội thoại hoàn toàn mới, sạch ngữ cảnh.
- Đếm số lượng tin nhắn hiện tại trên màn hình.
- Bôi đen (nếu có text cũ) và dùng API đặc biệt (CDP) gõ thẳng **System Prompt** vào khung chat.
- **Tự động click nút Send** (Dùng Javascript quét tìm nút có `aria-label="Send Message"` hoặc icon Send).
- Chờ Claude trả lời (Nhận biết bằng việc chờ chữ `Stream` kết thúc và lấy kết quả text).

### Bước 4: Điều khiển Chrome gửi Article Prompt (Dữ liệu bài)
- Làm tương tự Bước 3 nhưng nội dung gửi là bài viết và danh sách URL.
- Vì đoạn text này rất dài (hơn 10,000 ký tự), Claude sẽ tự động gom nó lại thành 1 file đính kèm (`.txt`).
- Tool tiếp tục dùng Javascript tìm và click nút **Send**.
- Bắt đầu chế độ chờ đợi thông minh: 
  - Tool liên tục quét xem cái nút **"Copy"** hoặc nút **"Thumbs up/down"** đã hiện ra chưa.
  - Khi nút Copy hiện ra -> Nghĩa là Claude đã gõ xong JSON.
  - Tool chờ dư ra 2 giây cho giao diện hết giật lag rồi mới hút toàn bộ đoạn text (JSON) trên màn hình về Python.

### Bước 5: Bóc tách JSON và Điền Excel
- Tool (file `response_parser.py`) sẽ xóa bỏ các rác do Claude tự thêm vào (ví dụ như ```json ... ```) để lấy ra cục `{ "article": ..., "claims": ... }` thuần khiết nhất.
- Kiểm tra lại các format (chuẩn hóa chữ `XAC_NHAN` bị viết sai thành `XAC NHAN`).
- Gọi module thư viện `openpyxl` mở file `tem1.xlsx`.
- Điền dữ liệu từ JSON vào 2 sheet: `Annotation` và `Article Evaluation` theo đúng hàng/cột tương ứng.
- Lưu ra file mới trong thư mục `outputs/` với tên `1_annotated.xlsx`.
- Bật Windows Explorer mở thẳng thư mục chứa file Excel vừa tạo để bạn xem thành quả.

---

## 3. Các điểm chết (Cần lưu ý)
1. **Lỗi kẹt Send (Response: 0 chars):** Do quên ấn *Accept all* code mới trong VSCode nên Tool chạy code cũ, gõ xong text nhưng không bấm gửi được.
2. **Lỗi format:** Claude trả về sai cấu trúc JSON (Thiếu ngoặc, dư chữ). Tuy nhiên tool đã có cơ chế Retry (tự động thử lại 3 lần) nếu rớt vào trường hợp này.
3. **Mất kết nối Chrome:** Lỡ tay đóng cửa sổ Chrome thật -> Bắt buộc phải chạy lại `login_claude.py`.
