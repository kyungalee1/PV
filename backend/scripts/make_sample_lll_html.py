"""Generate sample HTML: field 1 = LLL, all other fields = UK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.html_generator import generate_cioms_html_file

if __name__ == "__main__":
    cioms = {"patient_initials": "LLL"}
    out = Path(__file__).resolve().parent.parent.parent / "cioms_sample_LLL.html"
    generate_cioms_html_file(cioms, case_id=0, output_path=out)
    print(f"Created: {out}")
