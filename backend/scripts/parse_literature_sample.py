"""Parse Literature source_1.pdf and print CIOMS fields + generate HTML."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.html_generator import generate_cioms_html_file
from app.services.parser import extract_from_pdf, parse_uploaded_file

PDF = Path(r"c:\Users\10124\Desktop\PV\Data input\Literature source_1.pdf")
OUT_HTML = Path(__file__).resolve().parent.parent.parent / "cioms_literature_source_1.html"


def main():
    if not PDF.exists():
        print(f"Missing: {PDF}")
        return
    result = parse_uploaded_file(PDF)
    cioms = result["cioms"]
    print(json.dumps(cioms, indent=2, ensure_ascii=False))
    generate_cioms_html_file(cioms, case_id=1, output_path=OUT_HTML)
    print(f"\nHTML: {OUT_HTML}")


if __name__ == "__main__":
    main()
