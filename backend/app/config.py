from pathlib import Path

API_HOST = "127.0.0.1"
API_PORT = 8000

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CIOMS_TEMPLATE_PDF = BASE_DIR / "cioms-form1.pdf"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PDF_DIR = DATA_DIR / "cioms_pdfs"
HTML_DIR = DATA_DIR / "cioms_html"
DB_PATH = DATA_DIR / "pv.db"

for d in (DATA_DIR, UPLOAD_DIR, PDF_DIR, HTML_DIR):
    d.mkdir(parents=True, exist_ok=True)
