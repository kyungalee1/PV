"""Auto-calibrate FIELD_RECTS from cioms-form1.pdf grid image."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
import numpy as np
import pdfplumber

TEMPLATE = Path(__file__).resolve().parent.parent.parent / "cioms-form1.pdf"


def px_to_pt(px, py, pw, ph, iw, ih):
    return px * pw / iw, py * ph / ih


def main():
    with pdfplumber.open(TEMPLATE) as pdf:
        page = pdf.pages[0]
        pw, ph = float(page.width), float(page.height)
        arr = np.array(page.to_image(resolution=150).original)
        ih, iw = arr.shape[:2]
        gray = arr.mean(axis=2)
        black = gray < 100

        def vlines(y0, y1, min_ratio=0.55):
            seg = black[y0:y1].sum(axis=0)
            vx = [i for i, v in enumerate(seg) if v >= (y1 - y0) * min_ratio]
            out = []
            if not vx:
                return out
            s = vx[0]
            p = vx[0]
            for i in vx[1:]:
                if i - p > 2:
                    out.append((s + p) // 2)
                    s = i
                p = i
            out.append((s + p) // 2)
            return out

        def hlines(x0, x1, min_ratio=0.55):
            seg = black[:, x0:x1].sum(axis=1)
            hy = [i for i, v in enumerate(seg) if v >= (x1 - x0) * min_ratio]
            out = []
            if not hy:
                return out
            s = hy[0]
            p = hy[0]
            for i in hy[1:]:
                if i - p > 2:
                    out.append((s + p) // 2)
                    s = i
                p = i
            out.append((s + p) // 2)
            return out

        # Row 1 value band
        y_val0, y_val1 = 290, 316
        xs = vlines(268, 319, 0.45)
        # filter xs in left section only (< 0.56 * iw)
        xs = [x for x in xs if x < iw * 0.56]
        print("row1 xs frac", [round(x / iw, 3) for x in xs])

        # Use edge-based for row1 if needed
        band = gray[268:319].astype(float)
        gx = np.abs(np.diff(band, axis=1)).mean(axis=0)
        thr = gx.mean() + gx.std() * 1.5
        peaks = [i for i, v in enumerate(gx) if v > thr and i < iw * 0.56]
        out = []
        if peaks:
            s = peaks[0]
            p = peaks[0]
            for i in peaks[1:]:
                if i - p > 8:
                    out.append((s + p) // 2)
                    s = i
                p = i
            out.append((s + p) // 2)
        xs = out
        print("edge xs", [round(x / iw, 3) for x in xs])

        cols = []
        for i in range(len(xs) - 1):
            if xs[i + 1] - xs[i] > 15:
                x0, x1 = xs[i], xs[i + 1]
                y0, y1 = y_val0, y_val1
                cols.append(
                    {
                        "px": (x0, y0, x1, y1),
                        "pt": px_to_pt(x0, y0, pw, ph, iw, ih)
                        + px_to_pt(x1, y1, pw, ph, iw, ih)[0:2],
                    }
                )

        keys = ["patient_initials", "country", "dob", "age", "sex", "reaction_onset"]
        for k, c in zip(keys, cols):
            x0, y0, x1, y1 = c["pt"][0], c["pt"][1], c["pt"][2], c["pt"][3]
            print(f'    "{k}": ({x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}),')


if __name__ == "__main__":
    main()
