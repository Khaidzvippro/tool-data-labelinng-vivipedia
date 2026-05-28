import shutil
import os
from datetime import date
import openpyxl

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "tem.xlsx")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")


def write_output(stt: str, data: dict, log_fn=print) -> str:
    """
    Điền data vào tem.xlsx, save vào outputs/{stt}_annotated.xlsx.
    data schema: {article: {...}, claims: [...]}
    Returns: absolute path to output file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{stt}_annotated.xlsx")
    try:
        shutil.copy(TEMPLATE_PATH, out_path)
    except PermissionError:
        import time
        out_path = os.path.join(OUTPUT_DIR, f"{stt}_annotated_{int(time.time())}.xlsx")
        shutil.copy(TEMPLATE_PATH, out_path)

    wb = openpyxl.load_workbook(out_path)
    today = date.today().isoformat()
    art = data.get("article", {})
    claims = data.get("claims", [])

    # === Sheet: Annotation (row 4 trở đi) ===
    ws_ann = wb["Annotation"]
    for i, c in enumerate(claims):
        r = 4 + i
        ws_ann.cell(r, 1, stt)                                     # #
        ws_ann.cell(r, 2, art.get("title", ""))                    # Article Title
        ws_ann.cell(r, 3, art.get("domain", ""))                   # Domain
        ws_ann.cell(r, 4, art.get("sub_domain", ""))               # Sub-domain
        ws_ann.cell(r, 5, art.get("sub_domain_id", ""))            # Sub-domain ID
        ws_ann.cell(r, 6, c.get("claim", ""))                      # Claim
        ws_ann.cell(r, 7, c.get("fact_check_status", ""))          # Fact-check Status
        ws_ann.cell(r, 8, c.get("fact_check_source_url", ""))      # Source URL
        ws_ann.cell(r, 9, c.get("source_fidelity", ""))            # SF
        ws_ann.cell(r, 10, c.get("source_coverage", ""))           # SC
        ws_ann.cell(r, 11, c.get("hallucination_rate", ""))        # HR (inv)
        ws_ann.cell(r, 12, c.get("source_quality", ""))            # SQ
        ws_ann.cell(r, 13, c.get("notes", ""))                     # Notes
        ws_ann.cell(r, 14, "AUTO")                                 # Annotator ID
        ws_ann.cell(r, 15, today)                                  # Date

    # === Sheet: Article Evaluation (row 4) ===
    ws_ae = wb["Article Evaluation"]
    r = 4
    ws_ae.cell(r, 1, stt)
    ws_ae.cell(r, 2, art.get("title", ""))
    ws_ae.cell(r, 3, "")                               # URL bài (để trống)
    ws_ae.cell(r, 4, art.get("domain", ""))
    ws_ae.cell(r, 5, art.get("sub_domain", ""))
    ws_ae.cell(r, 6, art.get("rel", ""))
    ws_ae.cell(r, 7, art.get("rel_band", ""))
    ws_ae.cell(r, 8, art.get("rel_reason", ""))
    ws_ae.cell(r, 9, art.get("comp", ""))
    ws_ae.cell(r, 10, art.get("comp_band", ""))
    ws_ae.cell(r, 11, art.get("comp_reason", ""))
    ws_ae.cell(r, 12, "")
    ws_ae.cell(r, 13, "AUTO")
    ws_ae.cell(r, 14, today)

    wb.save(out_path)
    log_fn(f"Saved: {out_path}")
    return os.path.abspath(out_path)
