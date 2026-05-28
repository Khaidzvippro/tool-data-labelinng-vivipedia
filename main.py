"""
main.py — RAG Annotation Tool GUI v3
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
import subprocess
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.pdf_parser      import parse_article
from modules.ref_parser      import parse_ref
from modules.prompt_builder  import build_system_prompt, build_article_prompt
from modules.claude_automation import run_annotation_with_retry
from modules.response_parser import extract_json, validate_schema, normalize_data
from modules.excel_writer    import append_rows, OUTPUT_PATH

# ─── Palette ──────────────────────────────────────────────────────────────────
BG       = "#F5F7FA"
CARD     = "#FFFFFF"
BORDER   = "#DDE1E9"
FG       = "#1A202C"
FG2      = "#4A5568"
ACCENT   = "#4F6EF7"
ACCENT_H = "#3A55D4"
SUCCESS  = "#22A663"
WARN     = "#E07B1F"
ERROR    = "#D94040"
DROP_BG  = "#EEF2FF"
DROP_ACT = "#C7D4FF"
DROP_ERR = "#FFE8E8"

FONT_BODY  = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_LABEL = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 9)
FONT_H1    = ("Segoe UI Semibold", 14)
FONT_H2    = ("Segoe UI Semibold", 10)
FONT_BTN   = ("Segoe UI Semibold", 11)

DOMAIN_OPTIONS = [
    ("law", "Pháp luật"),
    ("med", "Y tế & Sức khỏe"),
    ("trv", "Du lịch"),
    ("fin", "Tài chính & Kinh tế"),
    ("gov", "Chính trị & Hành chính"),
    ("edu", "Giáo dục"),
    ("sci", "Khoa học & Công nghệ"),
    ("biz", "Kinh doanh & Quản trị"),
    ("cul", "Văn hóa & Xã hội"),
    ("his", "Lịch sử & Địa lý"),
    ("re",  "Bất động sản & Xây dựng"),
    ("env", "Môi trường & Tài nguyên"),
    ("ent", "Thể thao & Giải trí"),
]


# ─── Validate errors ──────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Lỗi validate — có message người dùng đọc được + hint sửa."""
    def __init__(self, msg: str, hint: str = "", recoverable: bool = True):
        super().__init__(msg)
        self.hint       = hint
        self.recoverable = recoverable   # True = warning + hỏi tiếp tục; False = hard stop


class PipelineError(Exception):
    """Lỗi trong pipeline — stage + detail."""
    def __init__(self, stage: str, msg: str, hint: str = ""):
        super().__init__(msg)
        self.stage = stage
        self.hint  = hint


# ─── File validators ──────────────────────────────────────────────────────────

MIN_PDF_BYTES = 4096   # < 4 KB → file rỗng/giả

def _validate_pdf_file(path: str, label: str) -> None:
    """Kiểm tra file hợp lệ trước khi gửi vào fitz."""
    if not path:
        raise ValidationError(f"Chưa chọn {label}.",
                              hint="Kéo thả hoặc click vào vùng drop zone.")

    if not os.path.exists(path):
        raise ValidationError(f"Không tìm thấy file: {os.path.basename(path)}",
                              hint="File có thể đã bị xóa hoặc di chuyển.",
                              recoverable=False)

    if not path.lower().endswith(".pdf"):
        raise ValidationError(f"{label} không phải file PDF.",
                              hint=f"File được chọn: {os.path.basename(path)}\n"
                                    "Chỉ hỗ trợ định dạng .pdf",
                              recoverable=False)

    size = os.path.getsize(path)
    if size < MIN_PDF_BYTES:
        raise ValidationError(f"{label} có vẻ bị rỗng hoặc hỏng ({size} byte).",
                              hint="Kiểm tra lại file PDF gốc.",
                              recoverable=False)

    # Kiểm tra magic bytes PDF
    try:
        with open(path, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            raise ValidationError(f"{label} không phải file PDF hợp lệ (sai định dạng).",
                                  hint="File có thể bị đổi tên từ định dạng khác.",
                                  recoverable=False)
    except OSError as e:
        raise ValidationError(f"Không đọc được {label}: {e}",
                              hint="File có thể đang bị khóa bởi chương trình khác.",
                              recoverable=False)


def _validate_pdf_not_encrypted(path: str, label: str) -> None:
    """Kiểm tra PDF không bị mã hóa/password."""
    try:
        import fitz
        doc = fitz.open(path)
        if doc.needs_pass:
            doc.close()
            raise ValidationError(f"{label} bị bảo vệ bằng mật khẩu.",
                                  hint="Hãy mở PDF, lưu lại bản không có password.",
                                  recoverable=False)
        doc.close()
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Không mở được {label} bằng PyMuPDF: {e}",
                              hint="File có thể bị hỏng hoặc định dạng không tương thích.",
                              recoverable=False)


def _validate_not_same_file(art_path: str, ref_path: str) -> None:
    if ref_path and os.path.abspath(art_path) == os.path.abspath(ref_path):
        raise ValidationError("File bài viết và file Ref là cùng một file.",
                              hint="Hãy chọn hai file PDF khác nhau.",
                              recoverable=False)


# ─── Round rect canvas helper ─────────────────────────────────────────────────

def _round_rect(canvas, x1, y1, x2, y2, r=12, **kw):
    pts = [
        x1+r, y1,  x2-r, y1,
        x2, y1,   x2, y1+r,
        x2, y2-r, x2, y2,
        x2-r, y2, x1+r, y2,
        x1, y2,   x1, y2-r,
        x1, y1+r, x1, y1,
        x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


# ─── Drop Zone ────────────────────────────────────────────────────────────────

class DropZone(tk.Frame):
    STATE_EMPTY   = "empty"
    STATE_OK      = "ok"
    STATE_ERROR   = "error"
    STATE_LOADING = "loading"

    def __init__(self, parent, title: str, on_change=None, **kw):
        super().__init__(parent, bg=CARD, **kw)
        self._path      = ""
        self._on_change = on_change
        self._title     = title
        self._dragging  = False
        self._state     = self.STATE_EMPTY
        self._err_msg   = ""
        self._build()

        for w in self.winfo_children():
            w.configure(cursor="hand2")
            w.bind("<Button-1>", self._browse)
        self.bind("<Button-1>", self._browse)

        try:
            self.drop_target_register("DND_Files")  # type: ignore
            self.dnd_bind("<<DropEnter>>", self._drag_enter)  # type: ignore
            self.dnd_bind("<<DropLeave>>", self._drag_leave)  # type: ignore
            self.dnd_bind("<<Drop>>",      self._on_drop)     # type: ignore
        except Exception:
            pass

    def _build(self):
        self._canvas = tk.Canvas(self, bg=CARD, highlightthickness=0,
                                  width=280, height=130)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Button-1>", self._browse)
        self._canvas.bind("<Configure>", self._redraw)
        self._redraw()

    def _redraw(self, *_):
        c = self._canvas
        c.delete("all")
        w = int(c.winfo_width())  or 280
        h = int(c.winfo_height()) or 130

        # Background & border color by state
        if self._state == self.STATE_ERROR:
            bg, outline, dash = DROP_ERR, ERROR, (6, 4)
        elif self._dragging:
            bg, outline, dash = DROP_ACT, ACCENT, ()
        elif self._state == self.STATE_OK:
            bg, outline, dash = "#F0FFF6", SUCCESS, ()
        else:
            bg, outline, dash = DROP_BG, ACCENT, (6, 4)

        _round_rect(c, 2, 2, w-2, h-2, r=14,
                    fill=bg, outline=outline,
                    width=2 if (self._dragging or self._state != self.STATE_EMPTY) else 1,
                    dash=dash)

        if self._state == self.STATE_LOADING:
            c.create_text(w//2, h//2, text="⏳  Đang đọc...",
                          font=FONT_SMALL, fill=FG2)

        elif self._state == self.STATE_ERROR:
            c.create_text(w//2, h//2 - 20, text="⚠",
                          font=("Segoe UI", 20), fill=ERROR)
            c.create_text(w//2, h//2 + 4, text=self._err_msg,
                          font=("Segoe UI", 8), fill=ERROR, width=w-20)
            c.create_text(w//2, h//2 + 30, text="click để chọn file khác",
                          font=("Segoe UI", 8), fill=FG2)

        elif self._state == self.STATE_OK:
            name = os.path.basename(self._path)
            if len(name) > 32:
                name = name[:29] + "..."
            c.create_text(w//2, h//2 - 20, text="✅",
                          font=("Segoe UI", 22), fill=SUCCESS)
            c.create_text(w//2, h//2 + 8, text=name,
                          font=FONT_SMALL, fill=FG, width=w-20)
            c.create_text(w//2, h//2 + 30, text="click để đổi file",
                          font=("Segoe UI", 8), fill=FG2)

        else:
            c.create_text(w//2, h//2 - 22, text="📂",
                          font=("Segoe UI", 20), fill=ACCENT)
            c.create_text(w//2, h//2 + 4, text=self._title,
                          font=FONT_H2, fill=FG)
            c.create_text(w//2, h//2 + 24, text="kéo thả hoặc click để chọn PDF",
                          font=("Segoe UI", 8), fill=FG2)

    def set_state(self, state: str, err_msg: str = ""):
        self._state   = state
        self._err_msg = err_msg
        self._redraw()

    def _drag_enter(self, *_):
        self._dragging = True;  self._redraw()

    def _drag_leave(self, *_):
        self._dragging = False; self._redraw()

    def _on_drop(self, event):
        self._dragging = False
        raw = event.data.strip()
        if raw.startswith("{"):
            raw = raw[1:raw.rfind("}")]
        path = raw.split("\n")[0].strip()
        if path.lower().endswith(".pdf"):
            self.set_path(path)
        else:
            ext = os.path.splitext(path)[1] or "(không có đuôi)"
            self.set_state(self.STATE_ERROR,
                           f"Không phải PDF\n({ext})")

    def _browse(self, *_):
        path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            self.set_path(path)

    def set_path(self, path: str):
        self._path = path
        self.set_state(self.STATE_OK)
        if self._on_change:
            self._on_change(path)

    def clear_error(self):
        if self._state == self.STATE_ERROR:
            self._path = ""
            self.set_state(self.STATE_EMPTY)

    @property
    def path(self):
        return self._path


# ─── Chip / Badge ─────────────────────────────────────────────────────────────

class Chip(tk.Label):
    def __init__(self, parent, text="", color=ACCENT, **kw):
        super().__init__(parent, text=f"  {text}  ",
                         bg=color, fg=CARD,
                         font=("Segoe UI", 8, "bold"),
                         relief="flat", bd=0, padx=2, pady=1, **kw)


# ─── Log panel ────────────────────────────────────────────────────────────────

class LogPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=CARD, **kw)

        header = tk.Frame(self, bg="#F0F4FF", height=30)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  Log", font=FONT_H2,
                 bg="#F0F4FF", fg=FG2).pack(side="left", pady=4)
        clr = tk.Label(header, text="Xóa  ", font=("Segoe UI", 8),
                        bg="#F0F4FF", fg=FG2, cursor="hand2")
        clr.pack(side="right", pady=4)
        clr.bind("<Button-1>", lambda *_: self.clear())

        self._text = tk.Text(self, font=FONT_MONO, bg=CARD, fg=FG,
                              relief="flat", bd=0, state="disabled",
                              selectbackground=DROP_BG, wrap="word")
        sb = tk.Scrollbar(self, command=self._text.yview, bd=0, width=10)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(fill="both", expand=True, padx=10, pady=6)

        self._text.tag_config("ok",   foreground=SUCCESS)
        self._text.tag_config("err",  foreground=ERROR)
        self._text.tag_config("warn", foreground=WARN)
        self._text.tag_config("info", foreground=ACCENT)
        self._text.tag_config("dim",  foreground=FG2)
        self._text.tag_config("hint", foreground="#9B5DE5")

    def log(self, msg: str, tag: str = ""):
        if not tag:
            if any(k in msg for k in ("✅", "XONG", "Xong", "xong")):
                tag = "ok"
            elif any(k in msg for k in ("❌", "LỖI", "lỗi", "Error", "error", "Thất bại")):
                tag = "err"
            elif any(k in msg for k in ("⚠", "Cảnh báo", "WARNING", "Warn")):
                tag = "warn"
            elif msg.startswith("  →") or msg.startswith("→"):
                tag = "hint"
            elif msg.startswith("[") or any(k in msg for k in
                                            ("Đang", "Gửi", "Chờ", "Parse", "Đọc", "Bắt đầu")):
                tag = "info"
            else:
                tag = "dim"
        self._text.config(state="normal")
        self._text.insert("end", msg + "\n", tag)
        self._text.see("end")
        self._text.config(state="disabled")

    def clear(self):
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")


# ─── Status bar ───────────────────────────────────────────────────────────────

class StatusBar(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BORDER, height=3, **kw)
        self._bar = tk.Frame(self, bg=ACCENT, height=3)
        self._bar.place(x=0, y=0, relwidth=0, relheight=1)

    def set(self, fraction: float, color: str = ACCENT):
        self._bar.config(bg=color)
        self._bar.place(relwidth=max(0.0, min(1.0, fraction)))


# ─── Inline warning banner ────────────────────────────────────────────────────

class WarnBanner(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=CARD, **kw)
        self._visible = False

        self._inner = tk.Frame(self, bg="#FFF8E1", relief="flat", bd=0)
        self._inner.pack(fill="x")

        self._icon = tk.Label(self._inner, text="⚠", bg="#FFF8E1", fg=WARN,
                               font=("Segoe UI", 11))
        self._icon.pack(side="left", padx=(10, 4), pady=6)

        self._lbl = tk.Label(self._inner, text="", bg="#FFF8E1", fg="#7A4F00",
                              font=("Segoe UI", 9), anchor="w", justify="left",
                              wraplength=560)
        self._lbl.pack(side="left", fill="x", expand=True, pady=6)

        self._close = tk.Label(self._inner, text="✕", bg="#FFF8E1", fg=FG2,
                                font=("Segoe UI", 10), cursor="hand2", padx=10)
        self._close.pack(side="right")
        self._close.bind("<Button-1>", lambda *_: self.hide())

        # Line top
        tk.Frame(self._inner, bg="#FFCC02", height=2).place(x=0, y=0, relwidth=1)
        self.pack_forget()

    def show(self, msg: str):
        self._lbl.config(text=msg)
        self.pack(fill="x", pady=(0, 6))
        self._visible = True

    def hide(self):
        self.pack_forget()
        self._visible = False


# ─── Main App ─────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root  = root
        self._running = False
        root.title("Vivipedia Annotation Tool")
        root.geometry("860x740")
        root.minsize(820, 660)
        root.configure(bg=BG)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox",
                         fieldbackground=CARD, background=CARD,
                         foreground=FG, selectbackground=DROP_BG,
                         selectforeground=FG, relief="flat", borderwidth=1)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)],
                               background=[("readonly", CARD)])
        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        root = self.root

        # Topbar
        topbar = tk.Frame(root, bg=CARD, height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Frame(topbar, bg=ACCENT, width=4).pack(side="left", fill="y")
        tk.Label(topbar, text="Vivipedia Annotation",
                 font=FONT_H1, bg=CARD, fg=FG).pack(side="left", padx=18, pady=12)
        self._excel_chip = Chip(topbar, "Excel chưa có", color=FG2)
        self._excel_chip.pack(side="right", padx=16)
        self._refresh_excel_chip()
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

        # Body
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=20, pady=16)

        right = tk.Frame(body, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(0, 20), pady=16)

        # ── Section 1: Drop zones ──────────────────────────────────────────
        self._section(left, "1  Tệp đầu vào")

        dz_row = tk.Frame(left, bg=BG)
        dz_row.pack(fill="x", pady=(0, 2))

        self._dz_art = DropZone(dz_row, "Bài viết chính",
                                 on_change=self._on_article_drop,
                                 width=280, height=130)
        self._dz_art.pack(side="left", padx=(0, 10))

        self._dz_ref = DropZone(dz_row, "Tài liệu Ref PDF",
                                 width=280, height=130)
        self._dz_ref.pack(side="left")

        # Warning banner (ẩn mặc định)
        self._warn_banner = WarnBanner(left)

        # ── Section 2: Info ────────────────────────────────────────────────
        self._section(left, "2  Thông tin bài")

        info = tk.Frame(left, bg=CARD, relief="flat", bd=0)
        info.pack(fill="x", pady=(0, 4))

        # Title
        r0 = tk.Frame(info, bg=CARD, pady=6)
        r0.pack(fill="x", padx=14)
        tk.Label(r0, text="Tiêu đề", font=FONT_LABEL,
                 bg=CARD, fg=FG2, width=12, anchor="w").pack(side="left")
        self._title_var = tk.StringVar(value="")
        self._title_lbl = tk.Label(r0, textvariable=self._title_var,
                                    font=FONT_SMALL, bg=CARD, fg=FG,
                                    wraplength=380, anchor="w", justify="left")
        self._title_lbl.pack(side="left", padx=6)

        tk.Frame(info, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Claims count chip
        r0b = tk.Frame(info, bg=CARD, pady=4)
        r0b.pack(fill="x", padx=14)
        tk.Label(r0b, text="Số claims", font=FONT_LABEL,
                 bg=CARD, fg=FG2, width=12, anchor="w").pack(side="left")
        self._claims_var = tk.StringVar(value="—")
        tk.Label(r0b, textvariable=self._claims_var, font=FONT_SMALL,
                 bg=CARD, fg=FG2).pack(side="left", padx=6)

        tk.Frame(info, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Domain
        r1 = tk.Frame(info, bg=CARD, pady=8)
        r1.pack(fill="x", padx=14)
        tk.Label(r1, text="Domain", font=FONT_LABEL,
                 bg=CARD, fg=FG2, width=12, anchor="w").pack(side="left")
        self._domain_var = tk.StringVar(value="law — Pháp luật")
        domain_labels    = [f"{k} — {v}" for k, v in DOMAIN_OPTIONS]
        self._domain_cb  = ttk.Combobox(r1, textvariable=self._domain_var,
                                         values=domain_labels,
                                         state="readonly", width=30, font=FONT_SMALL)
        self._domain_cb.current(0)
        self._domain_cb.pack(side="left", padx=6)
        tk.Label(r1, text="gợi ý — Claude sẽ xác nhận",
                 font=("Segoe UI", 8), bg=CARD, fg=FG2).pack(side="left", padx=4)

        tk.Frame(info, bg=BORDER, height=1).pack(fill="x", padx=14)

        # Annotator
        r2 = tk.Frame(info, bg=CARD, pady=8)
        r2.pack(fill="x", padx=14)
        tk.Label(r2, text="Annotator ID", font=FONT_LABEL,
                 bg=CARD, fg=FG2, width=12, anchor="w").pack(side="left")
        self._ant_var = tk.StringVar(value="ANT-01")
        self._ant_entry = tk.Entry(
            r2, textvariable=self._ant_var, font=FONT_SMALL,
            bg="#F7F9FC", fg=FG, relief="solid", bd=1, width=14,
            insertbackground=FG,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        )
        self._ant_entry.pack(side="left", padx=6)
        self._ant_err = tk.Label(r2, text="", font=("Segoe UI", 8),
                                  bg=CARD, fg=ERROR)
        self._ant_err.pack(side="left", padx=4)

        tk.Frame(info, bg=BORDER, height=1).pack(fill="x")

        # ── Section 3: Run ─────────────────────────────────────────────────
        self._section(left, "3  Chạy")

        run_row = tk.Frame(left, bg=BG)
        run_row.pack(fill="x", pady=(0, 6))

        self._run_btn = tk.Button(
            run_row, text="▶  RUN ANNOTATION",
            font=FONT_BTN, bg=ACCENT, fg=CARD,
            activebackground=ACCENT_H, activeforeground=CARD,
            relief="flat", bd=0, padx=28, pady=10,
            cursor="hand2", command=self._on_run,
        )
        self._run_btn.pack(side="left")
        self._run_btn.bind("<Enter>", lambda *_: self._run_btn.config(bg=ACCENT_H)
                            if not self._running else None)
        self._run_btn.bind("<Leave>", lambda *_: self._run_btn.config(bg=ACCENT)
                            if not self._running else None)

        self._status_lbl = tk.Label(run_row, text="",
                                     font=FONT_SMALL, bg=BG, fg=FG2)
        self._status_lbl.pack(side="left", padx=16)

        self._prog = StatusBar(left)
        self._prog.pack(fill="x", pady=(4, 0))

        # Right: Log
        self._log_panel = LogPanel(right, relief="solid", bd=1)
        self._log_panel.pack(fill="both", expand=True)

        # Bottom strip
        strip = tk.Frame(root, bg=CARD, height=28)
        strip.pack(fill="x", side="bottom")
        strip.pack_propagate(False)
        tk.Frame(strip, bg=BORDER, height=1).pack(fill="x", side="top")
        self._strip_lbl = tk.Label(strip, text="Sẵn sàng",
                                    font=("Segoe UI", 8), bg=CARD, fg=FG2)
        self._strip_lbl.pack(side="left", padx=14)

    # ── Section header ────────────────────────────────────────────────────────

    def _section(self, parent, title: str):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=(10, 4))
        tk.Label(f, text=title, font=FONT_H2, bg=BG, fg=ACCENT).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x",
                                               expand=True, padx=(10, 0), pady=6)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_excel_chip(self):
        if os.path.exists(OUTPUT_PATH):
            kb = os.path.getsize(OUTPUT_PATH) // 1024
            self._excel_chip.config(text=f"  Excel  {kb} KB  ", bg=SUCCESS)
        else:
            self._excel_chip.config(text="  Excel chưa có  ", bg=FG2)

    def _domain_key(self) -> str:
        val = self._domain_var.get()
        return val.split(" — ")[0].strip() if " — " in val else val

    def _log(self, msg: str, tag: str = ""):
        self._log_panel.log(msg, tag)

    def _set_status(self, msg: str, color: str = FG2):
        self._status_lbl.config(text=msg, fg=color)
        self._strip_lbl.config(text=msg, fg=color)

    # ── On article drop: pre-validate + read info ─────────────────────────────

    def _on_article_drop(self, path: str):
        self._title_var.set("Đang đọc...")
        self._claims_var.set("—")
        self._dz_art.set_state(DropZone.STATE_LOADING)
        self._warn_banner.hide()

        def _read():
            try:
                _validate_pdf_file(path, "Bài viết chính")
                _validate_pdf_not_encrypted(path, "Bài viết chính")
                art = parse_article(path)
                t   = art.get("title", "")
                n   = art.get("claims_count", 0)
                self._title_var.set(t if t else "(không đọc được tiêu đề)")
                self._claims_var.set(f"{n} đoạn (claim)" if n else "⚠ Không tìm thấy claim")

                if not t or t == "Untitled":
                    self._warn_banner.show(
                        "Không đọc được tiêu đề bài. "
                        "PDF có thể là file scan ảnh hoặc không có text layer.")

                if n == 0:
                    self._dz_art.set_state(DropZone.STATE_ERROR,
                                            "Không trích xuất\nđược claim nào")
                    self._warn_banner.show(
                        "Không tìm thấy nội dung bài trong PDF.\n"
                        "Hãy kiểm tra: PDF có text không, hay chỉ là ảnh scan?")
                    return

                dk = art.get("domain_key")
                if dk:
                    for i, (k, v) in enumerate(DOMAIN_OPTIONS):
                        if k == dk:
                            self._domain_cb.current(i)
                            self._domain_var.set(f"{k} — {v}")
                            break

                self._dz_art.set_state(DropZone.STATE_OK)
                self._dz_art._path = path

            except ValidationError as e:
                self._dz_art.set_state(DropZone.STATE_ERROR, str(e)[:60])
                self._title_var.set(f"Lỗi: {e}")
                self._claims_var.set("—")
                if e.hint:
                    self._warn_banner.show(f"{e}\n→ {e.hint}")
                else:
                    self._warn_banner.show(str(e))
            except Exception as e:
                self._dz_art.set_state(DropZone.STATE_ERROR, "Lỗi đọc PDF")
                self._title_var.set(f"Lỗi: {e}")

        threading.Thread(target=_read, daemon=True).start()

    # ── Validate toàn bộ trước khi run ───────────────────────────────────────

    def _pre_validate(self) -> bool:
        """
        Validate nhiều tầng trước khi bắt đầu pipeline.
        Trả về True nếu OK (hoặc user chấp nhận warning).
        """
        art_path = self._dz_art.path
        ref_path = self._dz_ref.path

        # ── Tầng 1: Annotator ID ─────────────────────────────────────────
        ant = self._ant_var.get().strip()
        if not ant:
            self._ant_err.config(text="← Bắt buộc")
            self._ant_entry.config(highlightbackground=ERROR)
            messagebox.showwarning("Thiếu thông tin",
                                   "Vui lòng điền Annotator ID trước khi chạy.")
            return False
        if not ant.startswith("ANT-") or len(ant) < 5:
            if not messagebox.askyesno(
                "Annotator ID không đúng định dạng",
                f"Annotator ID '{ant}' không đúng định dạng khuyến nghị (ANT-xx).\n\n"
                "Tiếp tục với ID này?", icon="warning"
            ):
                return False
        self._ant_err.config(text="")
        self._ant_entry.config(highlightbackground=BORDER)

        # ── Tầng 2: File bài viết ────────────────────────────────────────
        try:
            _validate_pdf_file(art_path, "Bài viết chính")
        except ValidationError as e:
            self._dz_art.set_state(DropZone.STATE_ERROR, str(e)[:60])
            messagebox.showerror("Lỗi file bài viết",
                                  f"{e}\n\n→ {e.hint}" if e.hint else str(e))
            return False

        # ── Tầng 3: File Ref ─────────────────────────────────────────────
        if ref_path:
            try:
                _validate_pdf_file(ref_path, "Ref PDF")
            except ValidationError as e:
                self._dz_ref.set_state(DropZone.STATE_ERROR, str(e)[:60])
                messagebox.showerror("Lỗi file Ref PDF",
                                      f"{e}\n\n→ {e.hint}" if e.hint else str(e))
                return False
        else:
            # Không có Ref → hỏi tiếp tục
            if not messagebox.askyesno(
                "Không có Ref PDF",
                "Chưa chọn Ref PDF.\n"
                "Claude sẽ không có URL nguồn → hầu hết claims sẽ là KHONG TIM THAY.\n\n"
                "Tiếp tục không?", icon="warning"
            ):
                return False

        # ── Tầng 4: Không chọn cùng 1 file ──────────────────────────────
        try:
            _validate_not_same_file(art_path, ref_path)
        except ValidationError as e:
            messagebox.showerror("File trùng", str(e))
            return False

        # ── Tầng 5: Chrome CDP ───────────────────────────────────────────
        if not _check_chrome_cdp():
            answer = messagebox.askyesno(
                "Chrome chưa sẵn sàng",
                "Không kết nối được Chrome qua CDP (port 9222).\n\n"
                "Nguyên nhân thường gặp:\n"
                "• Chrome chưa mở với --remote-debugging-port=9222\n"
                "• Chrome chưa đăng nhập claude.ai\n\n"
                "Chạy file login_claude.py để mở Chrome đúng cách.\n\n"
                "Vẫn muốn thử tiếp tục?", icon="warning"
            )
            if not answer:
                return False

        return True

    # ── RUN ───────────────────────────────────────────────────────────────────

    def _on_run(self):
        if self._running:
            return
        if not self._pre_validate():
            return
        self._running = True
        self._run_btn.config(state="disabled", text="⏳  Đang chạy...",
                              bg="#9BADF7", cursor="arrow")
        self._set_status("Đang xử lý...", WARN)
        self._prog.set(0.04)
        self._log_panel.clear()
        self._warn_banner.hide()
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self):
        art_pdf = self._dz_art.path
        ref_pdf = self._dz_ref.path or None
        dk_hint = self._domain_key()
        ant     = self._ant_var.get().strip()
        today   = date.today().strftime("%Y-%m-%d")

        def step(n: float, msg: str):
            self._prog.set(n)
            self._log(msg)

        try:
            self._log("─" * 54)
            self._log(f"Bắt đầu: {os.path.basename(art_pdf)}")
            self._log("─" * 54)

            # ── STAGE 1: Parse article ────────────────────────────────────
            step(0.08, "\n[1/4] Đọc PDF bài viết...")
            try:
                _validate_pdf_not_encrypted(art_pdf, "Bài viết chính")
                art = parse_article(art_pdf)
            except ValidationError as e:
                raise PipelineError("Đọc PDF", str(e), e.hint)
            except Exception as e:
                raise PipelineError("Đọc PDF",
                                     f"PyMuPDF không đọc được file: {e}",
                                     "File PDF có thể bị hỏng hoặc không có text layer.")

            title    = art["title"]
            sections = art.get("sections", [])
            n_claims = art.get("claims_count", 0)
            detected = art.get("domain_key") or dk_hint

            self._log(f"  Tiêu đề  : {title}")
            self._log(f"  Domain   : {art.get('domain_name', detected)}")
            self._log(f"  Claims   : {n_claims}")

            if not title or title == "Untitled":
                self._log("  ⚠ Không đọc được tiêu đề — sẽ dùng '(Untitled)'", "warn")

            if n_claims == 0:
                raise PipelineError(
                    "Đọc PDF",
                    "Không trích xuất được claim nào từ bài viết.",
                    "Kiểm tra: PDF có text layer không? Bài có phần nội dung sau 'Tóm tắt nhanh' không?"
                )

            if n_claims > 40:
                self._log(f"  ⚠ {n_claims} claims — khá nhiều, Claude có thể timeout", "warn")

            # ── STAGE 2: Parse Ref ────────────────────────────────────────
            step(0.22, "\n[2/4] Đọc Ref PDF...")
            ref = {"urls": [], "url_count": 0}
            if ref_pdf and os.path.exists(ref_pdf):
                try:
                    ref = parse_ref(ref_pdf)
                    self._log(f"  URLs     : {ref['url_count']}")
                    for i, u in enumerate(ref["urls"][:5], 1):
                        self._log(f"    [{i}] {u}", "dim")
                    if ref["url_count"] > 5:
                        self._log(f"    ... + {ref['url_count']-5} URL khác", "dim")
                    if ref["url_count"] == 0:
                        self._log("  ⚠ Ref PDF không có URL hyperlink nào", "warn")
                        self._log("  → Claude sẽ không browse được URL", "hint")
                except Exception as e:
                    self._log(f"  ⚠ Lỗi đọc Ref PDF: {e} — bỏ qua, tiếp tục", "warn")
            else:
                self._log("  Không có Ref PDF → không có URL nguồn", "warn")

            # ── STAGE 3: Claude ───────────────────────────────────────────
            step(0.35, "\n[3/4] Gửi Claude Web...")
            try:
                sys_p = build_system_prompt()
                art_p = build_article_prompt(art, ref, detected)
                fetch_urls = ref.get("urls", [])[:8]  # tối đa 8 URL gửi riêng để fetch
                self._log(f"  System   : {len(sys_p)} ký tự")
                self._log(f"  Article  : {len(art_p)} ký tự")
                self._log(f"  URLs fetch: {len(fetch_urls)}")

                raw = run_annotation_with_retry(sys_p, art_p, urls=fetch_urls, log_fn=self._log)
            except RuntimeError as e:
                # RuntimeError = lỗi setup (Chrome/CDP) — không retry
                msg = str(e)
                if "connect" in msg.lower() or "9222" in msg:
                    raise PipelineError(
                        "Kết nối Claude",
                        "Không kết nối được Chrome CDP (port 9222).",
                        "Chạy login_claude.py để mở Chrome với remote debugging."
                    )
                elif "login" in msg.lower() or "auth" in msg.lower():
                    raise PipelineError(
                        "Kết nối Claude",
                        "Claude chưa đăng nhập.",
                        "Mở Chrome, đăng nhập claude.ai, rồi chạy lại."
                    )
                else:
                    raise PipelineError("Kết nối Claude", msg,
                                         "Kiểm tra Chrome có đang mở claude.ai không.")
            except Exception as e:
                raise PipelineError("Claude",
                                     f"Lỗi khi gửi/nhận dữ liệu: {e}",
                                     "Xem debug_screenshot.png để biết trạng thái trang.")

            if not raw or not raw.strip():
                raise PipelineError(
                    "Claude",
                    "Claude trả về response rỗng.",
                    "Timeout hoặc Claude không xử lý được. Xem debug_screenshot.png."
                )
            self._log(f"  Nhận     : {len(raw)} ký tự")

            # ── STAGE 4: Parse JSON ───────────────────────────────────────
            step(0.80, "\n[4/4] Parse JSON + ghi Excel...")
            try:
                data = extract_json(raw)
            except ValueError as e:
                # Hiện 200 ký tự đầu raw để debug
                preview = raw[:200].replace("\n", " ")
                raise PipelineError(
                    "Parse JSON",
                    f"Không parse được JSON từ Claude.\nPreview: {preview}",
                    "Claude có thể trả về text thay vì JSON. Xem log đầy đủ bên trên."
                )

            try:
                data = normalize_data(data)
            except Exception as e:
                raise PipelineError("Normalize", f"Lỗi normalize data: {e}")

            if not validate_schema(data):
                raise PipelineError(
                    "JSON Schema",
                    "JSON từ Claude thiếu field 'article' hoặc 'claims'.",
                    "Claude có thể đã trả về JSON sai schema. Kiểm tra rule.md."
                )

            cc   = data.get("claims", [])
            ca   = data.get("article", {})
            dn   = ca.get("domain") or art.get("domain_name", detected)
            sd   = ca.get("sub_domain", "")
            sdid = ca.get("sub_domain_id", "")

            # Cảnh báo nếu số claim lệch nhiều
            if abs(len(cc) - n_claims) > 3:
                self._log(
                    f"  ⚠ Claude trả {len(cc)} claims, script detect {n_claims} claims "
                    f"(lệch {abs(len(cc)-n_claims)})", "warn"
                )
            if len(cc) == 0:
                raise PipelineError(
                    "JSON Schema",
                    "Claude trả về 0 claims trong JSON.",
                    "Kiểm tra prompt — Claude có thể không xử lý được danh sách claim."
                )

            self._log(f"  Domain   : {dn}")
            self._log(f"  Sub      : {sd} [{sdid}]")
            self._log(f"  Claims   : {len(cc)}")
            self._log(f"  Rel={ca.get('rel','?')} | Comp={ca.get('comp','?')}")

            # Validate từng claim
            _validate_claims(cc, self._log)

            # ── Ghi Excel ─────────────────────────────────────────────────
            rows = _merge_rows(sections, cc, title, dn, sd, sdid, ant, today)
            try:
                out = append_rows(rows)
            except PermissionError:
                raise PipelineError(
                    "Ghi Excel",
                    f"Không ghi được vào {os.path.basename(OUTPUT_PATH)} — file đang mở.",
                    "Đóng file Excel trước khi chạy."
                )
            except Exception as e:
                raise PipelineError("Ghi Excel", f"Lỗi ghi Excel: {e}")

            self._prog.set(1.0, SUCCESS)
            self._log(f"\n{'─'*54}")
            self._log(f"✅  XONG!  {len(rows)} claims → {os.path.basename(out)}")
            self._log(f"{'─'*54}")
            self._set_status(f"✅  Xong — {len(cc)} claims  |  {dn} / {sd}", SUCCESS)
            self._refresh_excel_chip()
            subprocess.Popen(f'explorer /select,"{out}"')

        except PipelineError as e:
            self._prog.set(0, ERROR)
            self._log(f"\n❌  [{e.stage}] {e}", "err")
            if e.hint:
                self._log(f"  → {e.hint}", "hint")
            self._set_status(f"Lỗi [{e.stage}]: {e}", ERROR)
            # Show popup chỉ với lỗi nghiêm trọng
            messagebox.showerror(
                f"Lỗi — {e.stage}",
                f"{e}\n\n→ {e.hint}" if e.hint else str(e)
            )

        except Exception as e:
            import traceback
            self._prog.set(0, ERROR)
            self._log(f"\n❌  Lỗi không mong đợi: {e}", "err")
            self._log(traceback.format_exc(), "dim")
            self._set_status(f"Lỗi: {e}", ERROR)

        finally:
            self._running = False
            self._run_btn.config(state="normal",
                                  text="▶  RUN ANNOTATION",
                                  bg=ACCENT, cursor="hand2")


# ─── Claim-level validation ───────────────────────────────────────────────────

VALID_STATUSES = {"XAC NHAN", "LECH", "MAU THUAN", "OUTDATED", "KHONG TIM THAY", "BO QUA"}

def _validate_claims(claims: list, log_fn) -> None:
    """Cảnh báo các claim có dữ liệu bất thường — không raise, chỉ log."""
    issues = []
    for i, c in enumerate(claims, 1):
        status = c.get("fact_check_status", "")
        if status not in VALID_STATUSES:
            issues.append(f"  Claim {i}: fact_check_status không hợp lệ '{status}'")

        for field in ("source_fidelity", "source_coverage",
                       "hallucination_rate", "source_quality"):
            val = c.get(field)
            if val is not None:
                try:
                    v = float(val)
                    if not 0.0 <= v <= 1.0:
                        issues.append(f"  Claim {i}: {field}={v} ngoài khoảng [0,1]")
                except (TypeError, ValueError):
                    issues.append(f"  Claim {i}: {field} không phải số ('{val}')")

        url = c.get("fact_check_source_url", "")
        if url and not url.startswith("http"):
            issues.append(f"  Claim {i}: URL không hợp lệ '{url[:50]}'")

        notes = c.get("notes", "")
        if notes and not any(k in notes for k in ("SF=", "SC=", "HR=", "SQ=", "TXT=")):
            issues.append(f"  Claim {i}: notes thiếu format SF=/SC=/HR=/SQ=/TXT=")

    if issues:
        log_fn(f"  ⚠ {len(issues)} cảnh báo dữ liệu:", "warn")
        for iss in issues[:8]:     # tối đa 8 dòng
            log_fn(iss, "warn")
        if len(issues) > 8:
            log_fn(f"  ... và {len(issues)-8} cảnh báo khác", "warn")


# ─── Chrome CDP ping ──────────────────────────────────────────────────────────

def _check_chrome_cdp(port: int = 9222) -> bool:
    """Kiểm tra nhanh Chrome có đang lắng nghe CDP không."""
    try:
        import urllib.request
        urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


# ─── Merge helper ─────────────────────────────────────────────────────────────

def _merge_rows(sections, claude_claims, title,
                domain_name, subdomain, subdomain_id,
                annotator, today) -> list:
    rows = []
    flat = []
    for sec in sections:
        for para in sec.get("paragraphs", []):
            flat.append(para["text"] if isinstance(para, dict) else para)

    for i, text in enumerate(flat):
        c = claude_claims[i] if i < len(claude_claims) else {}
        rows.append([
            "",
            title,
            domain_name,
            subdomain,
            subdomain_id,
            text,
            c.get("fact_check_status", ""),
            c.get("fact_check_source_url", ""),
            c.get("source_fidelity", ""),
            c.get("source_coverage", ""),
            c.get("hallucination_rate", ""),
            c.get("source_quality", ""),
            c.get("notes", ""),
            annotator,
            today,
        ])
    return rows


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import tkinterdnd2
        root = tkinterdnd2.Tk()
    except ImportError:
        root = tk.Tk()

    App(root)
    root.mainloop()
