import time
import os
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

CLAUDE_URL = "https://claude.ai/new"
DEBUG_PORT = 9222  # Chrome phải chạy với --remote-debugging-port=9222

# Các selector Claude dùng cho assistant message
_ASSISTANT_SELECTORS = [
    '[data-testid="assistant-message"]',
    '[data-message-author-role="assistant"]',
    '.font-claude-message',
]

# JS lấy text response cuối của Claude
_JS_GET_LAST_RESPONSE = """
() => {
    // 1. Thử lấy từ block code JSON cuối cùng
    const jsonCodes = Array.from(document.querySelectorAll(
        'code.language-json, [aria-label="json code"] code'
    ));
    if (jsonCodes.length > 0) {
        return jsonCodes[jsonCodes.length - 1].textContent;
    }

    // 2. Selector chuẩn assistant message
    const assistantMsgs = Array.from(document.querySelectorAll(
        '[data-message-author-role="assistant"], .font-claude-message'
    ));
    if (assistantMsgs.length > 0) {
        const lastMsg = assistantMsgs[assistantMsgs.length - 1];
        const prose = lastMsg.querySelector('.prose');
        return prose ? prose.innerText : lastMsg.innerText;
    }

    // 3. Fallback .prose
    const proses = Array.from(document.querySelectorAll('.prose'));
    if (proses.length > 0) {
        return proses[proses.length - 1].innerText;
    }

    return "";
}
"""

# JS kiểm tra Claude đang stream hay đã xong
# Trả về true nếu CÒN đang generate (nút Stop hiện hoặc spinner hiện)
_JS_IS_GENERATING = """
() => {
    // Nút stop/interrupt thường có aria-label "Stop" hoặc data-testid chứa "stop"
    const stopBtn = document.querySelector(
        'button[aria-label="Stop"], button[data-testid*="stop"], button[data-value="stop"]'
    );
    if (stopBtn) return true;

    // Spinner hoặc loading indicator
    const spinner = document.querySelector(
        '[data-testid="streaming-indicator"], .loading-spinner, [aria-label*="loading"]'
    );
    if (spinner) return true;

    // Kiểm tra class animate trên assistant message cuối (cursor nhấp nháy)
    const msgs = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
    if (msgs.length > 0) {
        const last = msgs[msgs.length - 1];
        if (last.querySelector('.animate-pulse, .cursor-blink')) return true;
    }

    return false;
}
"""


def _wait_response(page, timeout: int = 300, log_fn=print) -> str:
    """
    Chờ Claude stream xong bằng polling — không đợi tĩnh.
    - Poll mỗi 3s xem Claude còn generating không
    - Nếu text không thay đổi 3 lần liên tiếp → coi như xong
    - Hard timeout: mặc định 300s (5 phút) để cover cả việc browse nhiều URL
    """
    log_fn(f"  Đang đợi Claude stream xong (timeout {timeout}s)...")

    deadline    = time.time() + timeout
    last_text   = ""
    stable_count = 0
    STABLE_NEEDED = 4   # số lần liên tiếp text không đổi → xong
    POLL_INTERVAL = 3   # giây giữa mỗi lần check

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)

        # Lấy text hiện tại
        try:
            current = page.evaluate(_JS_GET_LAST_RESPONSE) or ""
            current = current.strip()
        except Exception:
            current = ""

        # Kiểm tra còn generating không
        try:
            still_generating = page.evaluate(_JS_IS_GENERATING)
        except Exception:
            still_generating = False

        if still_generating:
            # Còn streaming — reset stable counter, log progress
            if len(current) != len(last_text):
                log_fn(f"  Đang stream... ({len(current)} ký tự)")
            stable_count = 0
            last_text = current
            continue

        # Không còn generating — kiểm tra text có ổn định không
        if current == last_text and len(current) > 50:
            stable_count += 1
            if stable_count >= STABLE_NEEDED:
                elapsed = int(time.time() - (deadline - timeout))
                log_fn(f"  Claude xong sau ~{elapsed}s — {len(current)} ký tự")
                return current
        else:
            stable_count = 0

        last_text = current

    # Hard timeout — lấy bất cứ thứ gì đang có
    log_fn(f"  ⚠ Timeout {timeout}s — lấy text hiện tại ({len(last_text)} ký tự)")
    try:
        page.screenshot(path=os.path.abspath("debug_screenshot.png"), full_page=True)
    except Exception:
        pass
    return last_text



def _get_input_box(page):
    """Lấy input box Claude — thử nhiều selector."""
    for selector in [
        '[contenteditable="true"][data-placeholder]',
        'div[contenteditable="true"]',
        'textarea',
    ]:
        el = page.locator(selector).first
        if el.count() > 0:
            return el
    raise RuntimeError("Không tìm thấy input box của Claude")


def _click_send(page, log_fn=print):
    """Đảm bảo bấm được nút Send (kể cả khi text dài bị biến thành file)."""
    time.sleep(0.5)
    
    try:
        # Dùng native click của Playwright với force=True để bỏ qua check animation/stable
        page.click('button[aria-label="Send message"]', timeout=2000, force=True)
        log_fn("  Đã click nút Send (native Playwright).")
    except Exception as e:
        log_fn(f"  Không tìm thấy nút Send qua Playwright: {e}")
        # Fallback 1: Dùng Enter
        log_fn("  Thử gửi bằng phím Enter...")
        page.keyboard.press("Enter")
        # Log debug nếu cần thiết
        try:
            page.screenshot(path=os.path.abspath("debug_screenshot_send.png"), full_page=True)
            with open("debug_dom_send.html", "w", encoding="utf-8") as f:
                f.write(page.evaluate("() => document.body.innerHTML"))
        except Exception:
            pass



def _send_text(page, text: str, log_fn=print):
    """
    Gửi text vào input box Claude qua clipboard (Ctrl+V).
    Dùng clipboard thật để Claude.ai parse được URL trong text và trigger web fetch.
    insert_text() không trigger URL detection của Claude UI.
    """
    import subprocess, sys

    inp = _get_input_box(page)
    inp.click()
    time.sleep(0.3)

    # Xóa nội dung cũ
    page.keyboard.press("Control+a")
    time.sleep(0.1)
    page.keyboard.press("Backspace")
    time.sleep(0.1)

    # Đưa text vào clipboard qua PowerShell (không cần thư viện ngoài)
    _set_clipboard(text)
    time.sleep(0.3)

    # Paste vào input box
    page.keyboard.press("Control+v")
    time.sleep(1.5)  # Đợi Claude.ai parse URL và trigger web fetch indicator

    # Gõ thêm space để React nhận diện có text (bắt buộc)
    page.keyboard.press("Space")
    time.sleep(0.5)

    current = page.evaluate(
        "() => document.querySelector('[contenteditable=\"true\"]')?.innerText || ''"
    )
    log_fn(f"  Đã paste {len(text)} chars (DOM text len: {len(current.strip())})")


def _set_clipboard(text: str):
    """
    Đưa text vào clipboard Windows qua PowerShell với encoding UTF-8.
    Dùng utf-8-sig (UTF-8 BOM) để PowerShell 5.1 đọc đúng tiếng Việt.
    """
    import subprocess, tempfile, os
    # Ghi file với UTF-8 BOM — PowerShell 5.1 mặc định đọc UTF-16, BOM giúp nó detect UTF-8
    tmp_path = tempfile.mktemp(suffix=".txt")
    with open(tmp_path, "w", encoding="utf-8-sig") as f:
        f.write(text)
    try:
        # -Encoding utf8 để đọc đúng, -Raw để giữ newline
        cmd = f"[System.IO.File]::ReadAllText('{tmp_path}', [System.Text.Encoding]::UTF8) | Set-Clipboard"
        subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            timeout=15,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass




def run_annotation(system_prompt: str, article_prompt: str, log_fn=print) -> str:
    """
    Connect vào Chrome thật qua CDP (port 9222).
    Chrome phải đã mở claude.ai và đã login.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        except Exception as e:
            raise RuntimeError(
                f"Không connect được Chrome (port {DEBUG_PORT}).\n"
                f"Hãy chạy: python login_claude.py\n"
                f"Lỗi: {e}"
            )

        log_fn("Đã connect Chrome thật.")

        # Lấy context và tab Claude
        contexts = browser.contexts
        if not contexts:
            raise RuntimeError("Chrome không có tab nào mở")

        ctx = contexts[0]
        pages = ctx.pages

        # Tìm tab claude.ai hoặc tạo mới
        claude_page = None
        for pg in pages:
            if "claude.ai" in pg.url:
                claude_page = pg
                break

        if claude_page is None:
            log_fn("Mở tab Claude mới...")
            claude_page = ctx.new_page()
            claude_page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
        else:
            log_fn(f"Dùng tab Claude: {claude_page.url}")
            # Mở conversation mới
            claude_page.goto(CLAUDE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

        # Check vẫn login
        if "login" in claude_page.url or "auth" in claude_page.url:
            raise RuntimeError("Claude chưa login — hãy login trong Chrome rồi chạy lại")

        # === STEP 1: System prompt ===
        log_fn("Gửi system prompt (rule.md)...")
        _send_text(claude_page, system_prompt, log_fn)
        _click_send(claude_page, log_fn)

        # Đợi Claude ack system prompt — thường 10-20s
        r1 = _wait_response(claude_page, timeout=60, log_fn=log_fn)
        log_fn(f"Claude confirm: {r1[:80]}...")

        # === STEP 2: Article prompt ===
        log_fn("Gửi dữ liệu bài viết...")
        _send_text(claude_page, article_prompt, log_fn)
        _click_send(claude_page, log_fn)

        # Timeout dài vì Claude phải browse nhiều URL trước khi trả JSON
        log_fn("Chờ Claude xử lý + browse URL...")
        response = _wait_response(claude_page, timeout=300, log_fn=log_fn)

        # Không đóng browser — Chrome thật vẫn chạy
        return response


def run_annotation_with_retry(
    system_prompt: str,
    article_prompt: str,
    log_fn=print,
    max_retries: int = 3,
) -> str:
    """Wrapper retry."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return run_annotation(system_prompt, article_prompt, log_fn)
        except RuntimeError:
            raise  # lỗi setup — không retry
        except Exception as e:
            last_err = e
            log_fn(f"Lần {attempt}/{max_retries} thất bại: {e}")
            if attempt < max_retries:
                log_fn("Retry sau 5s...")
                time.sleep(5)
    raise RuntimeError(f"Thất bại sau {max_retries} lần. Lỗi cuối: {last_err}")
