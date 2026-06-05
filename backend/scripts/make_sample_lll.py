"""Generate sample: field 1 = LLL, all other fields = UK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pdf_generator import FIELD_RECTS, generate_cioms_pdf

if __name__ == "__main__":
    cioms = {"patient_initials": "LLL"}
    out = Path(__file__).resolve().parent.parent.parent / "cioms_sample_LLL_v2.pdf"
    generate_cioms_pdf(cioms, case_id=0, output_path=out)
    print(f"Created: {out}")
    print(f"Fields: {len(FIELD_RECTS)}")
