"""
login_claude.py — Mở Chrome thật với remote debug port để login Claude.

Cách dùng:
1. python login_claude.py
2. Chrome mở → login Claude bình thường
3. Sau khi vào được Claude chat, KHÔNG đóng Chrome
4. Chạy main.py → tool tự connect vào Chrome đó
"""
import subprocess
import sys
import time
import os

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222
USER_DATA_DIR = os.path.abspath("chrome_profile")


def main():
    print("=" * 50)
    print("RAG Annotation Tool — Login Helper")
    print("=" * 50)
    print(f"\nMở Chrome với remote debug port {DEBUG_PORT}...")
    print(f"Profile: {USER_DATA_DIR}")
    print("\nBước 1: Login Claude.ai trong cửa sổ Chrome vừa mở")
    print("Bước 2: Sau khi vào được chat page → KHÔNG ĐÓNG Chrome")
    print("Bước 3: Chạy main.py để bắt đầu annotation\n")

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://claude.ai",
    ]

    proc = subprocess.Popen(cmd)
    print(f"Chrome PID: {proc.pid}")
    print("Chrome đang chạy. Login xong thì chạy main.py.")
    proc.wait()
    print("Chrome đã đóng.")


if __name__ == "__main__":
    main()

