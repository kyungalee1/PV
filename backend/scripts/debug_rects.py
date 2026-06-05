"""Draw red rectangles on template to verify FIELD_RECTS alignment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
from app.config import CIOMS_TEMPLATE_PDF
from app.services.pdf_generator import FIELD_RECTS, CHECKBOXES

OUT = Path(__file__).resolve().parent.parent.parent / "cioms_debug_rects.pdf"

doc = fitz.open(str(CIOMS_TEMPLATE_PDF))
page = doc[0]
print(f"Page size: {page.rect.width} x {page.rect.height}")

for key, (x0, y0, x1, y1) in FIELD_RECTS.items():
    r = fitz.Rect(x0, y0, x1, y1)
    page.draw_rect(r, color=(1, 0, 0), width=0.5)
    page.insert_text((x0 + 1, y0 + 8), key[:8], fontsize=5, color=(1, 0, 0))

for key, (x, y) in CHECKBOXES.items():
    page.draw_circle(fitz.Point(x, y), 3, color=(0, 1, 0))

doc.save(str(OUT))
doc.close()
print(f"Saved: {OUT}")
