"""Regenerate the fictional sample CVs in sample_data/. Needs reportlab and python-docx (pip install -r requirements-dev.txt).
All the people are invented. Run from the project root:  python scripts/make_sample_cvs.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from tests import fixtures as F

out = os.path.join(ROOT, "sample_data")
bad = os.path.join(out, "not_accepted")
os.makedirs(bad, exist_ok=True)
files = {
    os.path.join(out, "cv_priya_nair_data_analyst.pdf"): F.make_pdf(F.PRIYA, width=120),
    os.path.join(out, "cv_rohan_mehta_software_engineer.pdf"): F.make_pdf(F.ROHAN, width=120),
    os.path.join(out, "cv_meera_kapoor_marketing.docx"): F.make_docx(F.MEERA),
    # a CV with an undated role and a multi-part layout, to show reading warnings and unverifiable experience
    os.path.join(out, "cv_kiran_desai_undated_role.pdf"): F.make_pdf(F.KIRAN, width=120),
    # three applicants whose CVs come from one generated template (same sentences, different fill-ins): template detection
    os.path.join(out, "cv_arjun_rao_template.pdf"): F.make_pdf(F.ARJUN, width=120),
    os.path.join(out, "cv_sana_iqbal_template.pdf"): F.make_pdf(F.SANA, width=120),
    os.path.join(out, "cv_dev_malhotra_template.pdf"): F.make_pdf(F.DEV, width=120),
    # files the app should refuse or explain, for the validation part of the demo
    os.path.join(bad, "scanned_image_only.pdf"): F.scanned_like_pdf(),
    os.path.join(bad, "not_a_cv.txt"): b"This is a plain text file. Only PDF and DOCX CVs are accepted.\n",
    os.path.join(bad, "empty.pdf"): b"",
}
for path, data in files.items():
    with open(path, "wb") as f:
        f.write(data)
    print("wrote", os.path.relpath(path, ROOT), len(data), "bytes")
