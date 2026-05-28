import sys
sys.stdout.reconfigure(encoding='utf-8')

from modules.pdf_parser import parse_article
from modules.ref_parser import parse_ref, check_url_coverage

art = parse_article("data/1.pdf")
print("Title:", art["title"])
print("Claims count:", art["claims_count"])
print("Headings:", art["headings"][:5])

ref = parse_ref("1", "data")
print("\nRef URLs:", ref["url_count"])
for u in ref["urls"]:
    print(" -", u)

cov = check_url_coverage(ref["url_count"], art["claims_count"])
print("\nCoverage:", cov)
