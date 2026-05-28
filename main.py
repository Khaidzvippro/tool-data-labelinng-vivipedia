"""
main.py — RAG Annotation Tool GUI
"""
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.pdf_parser import parse_article
from modules.ref_parser import parse_ref, check_files, check_url_coverage
from modules.prompt_builder import build_system_prompt, build_article_prompt
from modules.claude_automation import run_annotation_with_retry
from modules.response_parser import extract_json, validate_schema, normalize_data
from modules.excel_writer import write_output

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
SURFACE = "#313244"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RAG Annotation Tool")
        self.geometry("680x580")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._build_ui()

    def _build_ui(self):
        # === Header ===
        hdr = tk.Frame(self, bg=BG, pady=14)
        hdr.pack(fill="x", padx=24)
        tk.Label(
            hdr, text="RAG Annotation Tool",
            font=("Segoe UI", 16, "bold"), bg=BG, fg=ACCENT
        ).pack(side="left")

        # === STT row ===
        row = tk.Frame(self, bg=BG, pady=4)
        row.pack(fill="x", padx=24)
        tk.Label(row, text="STT bài:", font=("Segoe UI", 12), bg=BG, fg=FG).pack(side="left")
        self.stt_var = tk.StringVar()
        self.stt_entry = tk.Entry(
            row, textvariable=self.stt_var,
            font=("Segoe UI", 14), width=7,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", bd=6,
        )
        self.stt_entry.pack(side="left", padx=10)
        self.run_btn = tk.Button(
            row, text="▶  RUN",
            font=("Segoe UI", 12, "bold"),
            bg=ACCENT, fg="#1e1e2e",
            activebackground="#74c7ec",
            relief="flat", padx=18, pady=4,
            cursor="hand2",
            command=self._on_run,
        )
        self.run_btn.pack(side="left")
        self.stt_var.trace_add("write", self._on_stt_change)

        # === File + URL status ===
        sf = tk.LabelFrame(
            self, text="File & URL Status",
            font=("Segoe UI", 10), bg=BG, fg=FG,
            bd=1, relief="groove", padx=10, pady=6,
        )
        sf.pack(fill="x", padx=24, pady=8)
        self.file_label = tk.Label(sf, text="Nhập STT để kiểm tra...", fg="gray", bg=BG, anchor="w")
        self.file_label.pack(fill="x")
        self.url_label = tk.Label(sf, text="", fg="gray", bg=BG, anchor="w")
        self.url_label.pack(fill="x")

        # === Log ===
        lf = tk.LabelFrame(
            self, text="Log",
            font=("Segoe UI", 10), bg=BG, fg=FG,
            bd=1, relief="groove",
        )
        lf.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.log = scrolledtext.ScrolledText(
            lf,
            font=("Consolas", 10),
            bg="#11111b", fg=FG,
            insertbackground=FG,
            state="disabled",
            relief="flat",
        )
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def _on_stt_change(self, *_):
        stt = self.stt_var.get().strip()
        if not stt:
            self.file_label.config(text="Nhập STT để kiểm tra...", fg="gray")
            self.url_label.config(text="")
            return
        ch = check_files(stt, DATA_DIR)
        if ch["ok"]:
            ref_exists = os.path.exists(ch["ref_pdf"])
            ref_info = "✓ Ref có" if ref_exists else "⚠ Không có Ref PDF"
            self.file_label.config(
                text=f"✓ {ch['main_pdf']}   |   {ref_info}",
                fg=GREEN,
            )
            # Quick check URL count from Ref
            if ref_exists:
                try:
                    ref = parse_ref(stt, DATA_DIR)
                    n_url = ref.get("url_count", 0)
                    self.url_label.config(
                        text=f"  Ref URLs: {n_url} links (sẽ check coverage khi Run)",
                        fg=GREEN if n_url > 0 else YELLOW,
                    )
                except Exception:
                    self.url_label.config(text="  URL: chưa đọc được", fg="gray")
            else:
                self.url_label.config(text="  Không có Ref → không có URL nguồn", fg=YELLOW)
        else:
            self.file_label.config(text=" | ".join(ch["errors"]), fg=RED)
            self.url_label.config(text="")

    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.update_idletasks()

    def _on_run(self):
        stt = self.stt_var.get().strip()
        if not stt:
            messagebox.showwarning("Thiếu STT", "Vui lòng nhập STT bài viết")
            return
        ch = check_files(stt, DATA_DIR)
        if not ch["ok"]:
            messagebox.showerror("Lỗi file", "\n".join(ch["errors"]))
            return
        self.run_btn.config(state="disabled", text="⏳ Đang chạy...")
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        threading.Thread(target=self._pipeline, args=(stt, ch), daemon=True).start()

    def _ask_continue(self, message: str) -> bool:
        """Hỏi user có muốn tiếp không (chạy từ thread)."""
        result = [False]
        def ask():
            result[0] = messagebox.askyesno(
                "⚠ Cảnh báo thiếu nguồn",
                f"{message}\n\nTiếp tục annotation không?",
                icon="warning",
            )
        self.after(0, ask)
        # Chờ dialog đóng
        import time
        time.sleep(0.3)
        while self.focus_get() is not None and not result[0]:
            time.sleep(0.1)
            # Kiểm tra nếu dialog đã được trả lời
            break
        # Simple approach: block với event
        self.after(0, lambda: result.__setitem__(0, result[0]))
        time.sleep(0.5)
        return result[0]

    def _pipeline(self, stt: str, ch: dict):
        try:
            self._log(f"{'='*40}")
            self._log(f"  Bắt đầu xử lý bài STT: {stt}")
            self._log(f"{'='*40}")

            # [1] Parse bài chính
            self._log("\n[1/5] Parsing bài chính...")
            art = parse_article(ch["main_pdf"])
            self._log(f"  Title: {art['title']}")
            self._log(f"  Nội dung: {len(art['content'])} chars")
            self._log(f"  Claims ước tính: {art['claims_count']}")

            # [2] Parse Ref + check URL coverage
            self._log("\n[2/5] Parsing Ref PDF + kiểm tra URL...")
            ref = parse_ref(stt, DATA_DIR)
            n_url = ref.get("url_count", 0)
            n_claims = art.get("claims_count", 1)

            if ref.get("content"):
                self._log(f"  Ref content: {len(ref['content'])} chars")
                self._log(f"  URLs tìm được: {n_url}")
                for u in ref.get("urls", [])[:5]:
                    self._log(f"    - {u}")
                if n_url > 5:
                    self._log(f"    ... và {n_url - 5} URL khác")
            else:
                self._log("  Ref: không có file")

            # Coverage check
            coverage = check_url_coverage(n_url, n_claims)
            if coverage["warning"]:
                self._log(f"\n  ⚠ {coverage['message']}")
                # Hỏi user qua dialog (main thread)
                proceed = [False]
                def ask_proceed():
                    proceed[0] = messagebox.askyesno(
                        "Thiếu nguồn",
                        f"{coverage['message']}\n\nTiếp tục annotation không?",
                        icon="warning",
                    )
                self.after(0, ask_proceed)
                import time; time.sleep(1.0)  # chờ dialog
                if not proceed[0]:
                    self._log("  Đã hủy.")
                    return
            else:
                self._log(f"  ✓ {coverage['message']}")

            # [3] Build prompts
            self._log("\n[3/5] Build prompt...")
            sys_p = build_system_prompt()
            art_p = build_article_prompt(art, ref)
            self._log(f"  System prompt: {len(sys_p)} chars")
            self._log(f"  Article prompt: {len(art_p)} chars")

            # [4] Claude automation
            self._log("\n[4/5] Claude Web automation...")
            raw = run_annotation_with_retry(sys_p, art_p, log_fn=self._log)
            self._log(f"  Response: {len(raw)} chars")

            if not raw.strip():
                raise ValueError("Claude trả về response rỗng — xem debug_screenshot.png")

            # [5] Parse JSON
            self._log("\n[5/5] Parse + validate JSON...")
            data = extract_json(raw)
            data = normalize_data(data)  # fix status, ensure floats
            if not validate_schema(data):
                raise ValueError("JSON thiếu field 'article' hoặc 'claims'")
            n_out = len(data.get("claims", []))
            self._log(f"  Claims output: {n_out}")
            self._log(f"  Domain: {data.get('article', {}).get('domain', '?')}")

            # Write Excel
            self._log("\nGhi vào Excel...")
            out = write_output(stt, data, log_fn=self._log)

            self._log(f"\n{'='*40}")
            self._log(f"  ✅ XONG! {n_out} claims → {out}")
            self._log(f"{'='*40}")

            subprocess.Popen(f'explorer /select,"{out}"')

        except Exception as e:
            self._log(f"\n❌ LỖI: {e}")
        finally:
            self.run_btn.config(state="normal", text="▶  RUN")


if __name__ == "__main__":
    App().mainloop()
