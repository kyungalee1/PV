"""Build FIELD_RECTS from detected horizontal grid lines."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
import numpy as np

TEMPLATE = Path(__file__).resolve().parent.parent.parent / "cioms-form1.pdf"
OUT = Path(__file__).resolve().parent.parent.parent / "cioms_calibrated_debug.pdf"
DPI = 200

XL, XR = 0.148, 0.552
XM = 0.362
XR2L, XR2R = 0.472, 0.920


def cluster(vals, gap):
    if not vals:
        return []
    vals = sorted(vals)
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def rf(x0, y0, x1, y1, pw, ph):
    return (
        round(x0 * pw, 1),
        round(y0 * ph, 1),
        round(x1 * pw, 1),
        round(y1 * ph, 1),
    )


def band(hy, i, j, inset=0.12):
    y0, y1 = hy[i], hy[j]
    pad = (y1 - y0) * inset
    return y0 + pad, y1 - pad


def main():
    doc = fitz.open(str(TEMPLATE))
    page = doc[0]
    pw, ph = page.rect.width, page.rect.height
    mat = fitz.Matrix(DPI / 72, DPI / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    gray = arr.mean(axis=2)
    h_px, w_px = gray.shape
    black = gray < 120

    hy = [y / h_px for y in cluster([i for i, s in enumerate(black.sum(axis=1)) if s > w_px * 0.22], gap=3)]
    print("HY:", [round(y, 3) for y in hy])

    # Expected keys near: 0.153,0.182,0.208,0.235,0.276,0.433,0.46,0.501,0.531,0.561,0.591,
    # 0.618,0.675,0.731,0.758,0.818,0.848

    def idx(target):
        return min(range(len(hy)), key=lambda i: abs(hy[i] - target))

    i = {
        "r1a": idx(0.182),
        "r1b": idx(0.208),
        "narr_t": idx(0.235),
        "narr_b": idx(0.433),
        "d14a": idx(0.433),
        "d14b": idx(0.460),
        "d15a": idx(0.460),
        "d15b": idx(0.501),
        "d17a": idx(0.501),
        "d17b": idx(0.531),
        "d18a": idx(0.531),
        "d18b": idx(0.561),
        "d19a": idx(0.561),
        "d19b": idx(0.591),
        "c22a": idx(0.618),
        "c22b": idx(0.675),
        "c23a": idx(0.675),
        "c23b": idx(0.731),
        "s4a": idx(0.731),
        "s4b": idx(0.758),
        "s4c": idx(0.758),
        "s4d": idx(0.818),
        "s4e": idx(0.818),
        "s4f": idx(0.848),
    }

    r1 = band(hy, i["r1a"], i["r1b"])
    narr = (hy[i["narr_t"]] + 0.004, hy[i["narr_b"]] - 0.004)
    d14 = band(hy, i["d14a"], i["d14b"])
    d15 = band(hy, i["d15a"], i["d15b"])
    d17 = band(hy, i["d17a"], i["d17b"])
    d18 = band(hy, i["d18a"], i["d18b"])
    d19 = band(hy, i["d19a"], i["d19b"])
    c22 = band(hy, i["c22a"], i["c22b"])
    c23 = band(hy, i["c23a"], i["c23b"])
    mfr_a = band(hy, i["s4a"], i["s4d"])   # 24a large block
    mfr_b = band(hy, i["s4d"], i["s4f"])   # 24b
    i["s4g"] = idx(0.887)
    i["s4h"] = idx(0.911)
    recv = band(hy, i["s4f"], i["s4g"])  # 24c
    report = band(hy, i["s4g"], i["s4h"])  # date of report

    fields = {
        "patient_initials": rf(XL, r1[0], 0.198, r1[1], pw, ph),
        "country": rf(0.198, r1[0], 0.256, r1[1], pw, ph),
        "dob": rf(0.256, r1[0], XM, r1[1], pw, ph),
        "age": rf(XM, r1[0], 0.406, r1[1], pw, ph),
        "sex": rf(0.406, r1[0], 0.468, r1[1], pw, ph),
        "reaction_onset": rf(0.468, r1[0], XR, r1[1], pw, ph),
        "narrative": rf(XL, narr[0], XR, narr[1], pw, ph),
        "drug14": rf(XL, d14[0], XR, d14[1], pw, ph),
        "dose15": rf(XL, d15[0], XM, d15[1], pw, ph),
        "route16": rf(XM, d15[0], XR, d15[1], pw, ph),
        "indication17": rf(XL, d17[0], XR, d17[1], pw, ph),
        "therapy18": rf(XL, d18[0], XM, d18[1], pw, ph),
        "duration19": rf(XM, d18[0], XR, d18[1], pw, ph),
        "concomitant22": rf(XL, c22[0], XR2R, c22[1], pw, ph),
        "history23": rf(XL, c23[0], XR2R, c23[1], pw, ph),
        "mfr24a": rf(XL, mfr_a[0], XR2L, mfr_a[1], pw, ph),
        "mfr24b": rf(XL, mfr_b[0], XR2L, mfr_b[1], pw, ph),
        "recv24c": rf(XL, recv[0], 0.336, recv[1], pw, ph),
        "report_date": rf(XL, report[0], 0.336, report[1], pw, ph),
        "remarks26": rf(XR2L, mfr_a[0], XR2R, mfr_b[1], pw, ph),
        "reporter25b": rf(XR2L, recv[0], XR2R, report[1], pw, ph),
    }

    checks = {
        "seriousness_death": (540.2, rf(0, 0.200, 0, 0.212, pw, ph)[1]),
        "seriousness_life_threatening": (540.2, rf(0, 0.220, 0, 0.234, pw, ph)[1]),
        "seriousness_hospitalization": (540.2, rf(0, 0.242, 0, 0.256, pw, ph)[1]),
        "seriousness_disability": (540.2, rf(0, 0.264, 0, 0.278, pw, ph)[1]),
        "seriousness_congenital_anomaly": (540.2, rf(0, 0.286, 0, 0.300, pw, ph)[1]),
        "seriousness_other_medically_important": (540.2, rf(0, 0.308, 0, 0.322, pw, ph)[1]),
        "dechallenge_yes": (540.2, rf(0, 0.518, 0, 0.532, pw, ph)[1]),
        "dechallenge_no": (558.0, rf(0, 0.518, 0, 0.532, pw, ph)[1]),
        "dechallenge_na": (575.8, rf(0, 0.518, 0, 0.532, pw, ph)[1]),
        "rechallenge_yes": (540.2, rf(0, 0.578, 0, 0.592, pw, ph)[1]),
        "rechallenge_no": (558.0, rf(0, 0.578, 0, 0.592, pw, ph)[1]),
        "rechallenge_na": (575.8, rf(0, 0.578, 0, 0.592, pw, ph)[1]),
    }

    for k, r in fields.items():
        page.draw_rect(fitz.Rect(*r), color=(1, 0, 0), width=0.8)

    doc.save(str(OUT))
    doc.close()

    print("\nFIELD_RECTS = {")
    for k, v in fields.items():
        print(f'    "{k}": {v},')
    print("}")
    print("\nCHECKBOXES = {")
    for k, v in checks.items():
        print(f'    "{k}": {v},')
    print("}")


if __name__ == "__main__":
    main()
