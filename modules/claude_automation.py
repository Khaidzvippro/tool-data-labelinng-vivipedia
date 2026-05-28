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

# JS để lấy text của assistant message cuối — chạy trong browser context
_JS_GET_LAST_RESPONSE = """
() => {
    // 1. Thử lấy từ block code JSON cuối cùng (chuẩn nhất cho data RAG)
    const jsonCodes = Array.from(document.querySelectorAll('code.language-json, [aria-label="json code"] code'));
    if (jsonCodes.length > 0) {
        return jsonCodes[jsonCodes.length - 1].textContent;
    }

    // 2. Thử dùng selector chuẩn của tin nhắn assistant
    const assistantMsgs = Array.from(document.querySelectorAll('[data-message-author-role="assistant"], .font-claude-message'));
    if (assistantMsgs.length > 0) {
        const lastMsg = assistantMsgs[assistantMsgs.length - 1];
        const prose = lastMsg.querySelector('.prose');
        return prose ? prose.innerText : lastMsg.innerText;
    }
    
    // 3. Fallback: Tìm tất cả các thẻ .prose trên trang
    const proses = Array.from(document.querySelectorAll('.prose'));
    if (proses.length > 0) {
        return proses[proses.length - 1].innerText;
    }
    
    return "";
}
"""


def _wait_response(page, timeout: int = 120, log_fn=print) -> str:
    """Chờ Claude stream xong bằng cách đợi thời gian tĩnh + trích xuất text cuối."""
    log_fn(f"  Bắt đầu đợi {timeout}s cho Claude suy nghĩ...")
    
    # Đợi tĩnh hoàn toàn (không phụ thuộc vào DOM)
    # timeout = 20s cho lệnh ngắn, 90s cho lệnh dài
    time.sleep(timeout)
    log_fn("  Hết thời gian đợi, bắt đầu hút chữ về...")

    # Lấy text qua JS
    try:
        text = page.evaluate(_JS_GET_LAST_RESPONSE)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as e:
        log_fn(f"  JS eval lỗi: {e}")

    # Fallback cuối cùng
    try:
        page.screenshot(path=os.path.abspath("debug_screenshot.png"), full_page=True)
    except Exception:
        pass

    return ""



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
    """Gửi text vào input box Claude bằng insert_text (tốt nhất cho React/Prosemirror)."""
    inp = _get_input_box(page)
    inp.click()
    time.sleep(0.2)

    # Ctrl+A để xóa text cũ (nếu có)
    page.keyboard.press("Control+a")
    time.sleep(0.1)
    page.keyboard.press("Backspace")
    time.sleep(0.1)

    # Insert text trực tiếp qua CDP dispatch
    page.keyboard.insert_text(text)
    time.sleep(0.5)
    
    # RẤT QUAN TRỌNG: Gõ thêm 1 dấu cách bằng phím thật để ép React nhận diện có chữ
    # Nếu không gõ phím thật, nút Send trông có màu nhưng bấm vào sẽ không chạy!
    page.keyboard.press("Space")
    time.sleep(0.5)

    # Lấy text check thử
    current = page.evaluate(
        "() => document.querySelector('[contenteditable=\"true\"]')?.innerText || ''"
    )
    log_fn(f"  Đã insert {len(text)} chars (DOM text len: {len(current.strip())})")




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

        r1 = _wait_response(claude_page, timeout=15, log_fn=log_fn)
        log_fn(f"Claude confirm: {r1[:100]}...")

        # === STEP 2: Article prompt ===
        log_fn("Gửi dữ liệu bài viết...")
        _send_text(claude_page, article_prompt, log_fn)
        _click_send(claude_page, log_fn)

        log_fn("Chờ Claude xử lý (khoảng 90s)...")
        response = _wait_response(claude_page, timeout=90, log_fn=log_fn)

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
