"""
CIOMS Form I — overlay field values onto cioms-form1.pdf using PyMuPDF.
Coordinates calibrated to the blank template (A4 portrait, top-left origin).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from app.config import CIOMS_TEMPLATE_PDF
from app.services.cioms_mapping import narrative_text as _cioms_narrative_text

VALUE_BLUE = (0, 0, 0.85)
FONT = "helv"
FONT_SIZE = 8

# (x0, y0, x1, y1) in PDF points — top-left origin, calibrated to cioms-form1.pdf grid
FIELD_RECTS: dict[str, tuple[float, float, float, float]] = {
    "patient_initials": (88.1, 155.8, 117.8, 172.3),
    "country": (117.8, 155.8, 152.4, 172.3),
    "dob": (152.4, 155.8, 215.5, 172.3),
    "age": (215.5, 155.8, 241.7, 172.3),
    "sex": (241.7, 155.8, 278.6, 172.3),
    "reaction_onset": (278.6, 155.8, 328.6, 172.3),
    "narrative": (88.1, 201.0, 328.6, 361.5),
    "drug14": (88.1, 367.5, 328.6, 384.5),
    "dose15": (88.1, 391.3, 215.5, 417.6),
    "route16": (215.5, 391.3, 328.6, 417.6),
    "indication17": (88.1, 424.8, 328.6, 443.9),
    "therapy18": (88.1, 450.0, 215.5, 469.1),
    "duration19": (215.5, 450.0, 328.6, 469.1),
    "concomitant22": (88.1, 525.8, 547.6, 562.2),
    "history23": (88.1, 573.6, 547.6, 610.0),
    "mfr24a": (88.1, 624.5, 280.9, 679.9),
    "mfr24b": (88.1, 691.7, 280.9, 710.9),
    "recv24c": (88.1, 717.8, 200.0, 742.4),
    "report_date": (88.1, 748.7, 200.0, 764.3),
    "remarks26": (280.9, 624.5, 547.6, 710.9),
    "reporter25b": (280.9, 717.8, 547.6, 764.3),
}

CHECKBOXES: dict[str, tuple[float, float]] = {
    "seriousness_death": (540.2, 168.3),
    "seriousness_life_threatening": (540.2, 185.2),
    "seriousness_hospitalization": (540.2, 203.7),
    "seriousness_disability": (540.2, 222.2),
    "seriousness_congenital_anomaly": (540.2, 240.7),
    "seriousness_other_medically_important": (540.2, 259.2),
    "dechallenge_yes": (540.2, 436.0),
    "dechallenge_no": (558.0, 436.0),
    "dechallenge_na": (575.8, 436.0),
    "rechallenge_yes": (540.2, 486.5),
    "rechallenge_no": (558.0, 486.5),
    "rechallenge_na": (575.8, 486.5),
    "source_study": (300.0, 717.2),
    "source_literature": (300.0, 730.0),
    "source_authority": (300.0, 742.7),
    "source_hp": (300.0, 755.5),
    "source_other": (300.0, 768.3),
    "type_initial": (420.0, 717.2),
    "type_followup": (420.0, 730.0),
    "type_final": (420.0, 742.7),
}


def _txt(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _infer_report_source(cioms: dict) -> str:
    src = _txt(cioms.get("report_source_cioms")).upper()
    if src:
        return src
    rt = _txt(cioms.get("report_type")).lower()
    if "study" in rt:
        return "STUDY"
    if "literature" in rt:
        return "LITERATURE"
    if "authority" in rt:
        return "AUTHORITY"
    if "professional" in rt or "spontaneous" in rt:
        return "HEALTH PROFESSIONAL"
    return "OTHER"


def _reaction_onset_lines(cioms: dict) -> str:
    """Field 4-6: onset date only."""
    from app.services.field_sanitizer import format_reaction_onset_field

    return format_reaction_onset_field(cioms)


def _narrative_text(cioms: dict) -> str:
    return _cioms_narrative_text(cioms)


def _yn_checked(answer: str, option: str) -> bool:
    return _txt(answer).upper() == option


def _put_text(page: fitz.Page, key: str, text: str, size: float = FONT_SIZE) -> None:
    if not text or key not in FIELD_RECTS:
        return
    rect = fitz.Rect(*FIELD_RECTS[key])
    if len(text) <= 8 and rect.height <= 22:
        tw = fitz.get_text_length(text, fontname=FONT, fontsize=size)
        x = rect.x0 + max(1, (rect.width - tw) / 2)
        y = rect.y0 + rect.height * 0.72
        page.insert_text((x, y), text, fontsize=size, fontname=FONT, color=VALUE_BLUE)
        return
    page.insert_textbox(
        rect,
        text,
        fontsize=size,
        fontname=FONT,
        color=VALUE_BLUE,
        align=fitz.TEXT_ALIGN_LEFT,
    )


def _put_check(page: fitz.Page, key: str, checked: bool) -> None:
    if not checked or key not in CHECKBOXES:
        return
    x, y = CHECKBOXES[key]
    page.insert_text((x, y), "X", fontsize=7, fontname=FONT, color=(0, 0, 0))


def generate_cioms_pdf(cioms: dict, case_id: int, output_path: Path) -> Path:
    template = CIOMS_TEMPLATE_PDF
    if not template.exists():
        raise FileNotFoundError(f"CIOMS template not found: {template}")

    doc = fitz.open(str(template))
    page = doc[0]

    age = _txt(cioms.get("patient_age")) or "UK"
    sex = _txt(cioms.get("patient_sex")) or "UK"
    from app.services.literature_extractor import resolve_suspect_drug_display

    drug = resolve_suspect_drug_display(
        cioms,
        source_text=str(cioms.get("_source_text") or ""),
    )
    therapy = ""
    if _txt(cioms.get("suspect_drug_start_date")) or _txt(cioms.get("suspect_drug_stop_date")):
        therapy = f"{_txt(cioms.get('suspect_drug_start_date'))} / {_txt(cioms.get('suspect_drug_stop_date'))}".strip(" /")

    reporter = "\n".join(
        x
        for x in [
            _txt(cioms.get("reporter_name")),
            _txt(cioms.get("reporter_organization")),
            _txt(cioms.get("reporter_country")),
        ]
        if x
    )

    src = _infer_report_source(cioms)
    rt = (_txt(cioms.get("cioms_report_type")) or "INITIAL").upper()
    abate = _txt(cioms.get("dechallenge_abate")) or "NA"
    reappear = _txt(cioms.get("dechallenge_reappear")) or "NA"

    # Section I
    _put_text(page, "patient_initials", _txt(cioms.get("patient_initials")) or "UK")
    _put_text(page, "country", _txt(cioms.get("country_of_occurrence")) or "UK")
    _put_text(page, "dob", _txt(cioms.get("patient_date_of_birth")) or "UK")
    _put_text(page, "age", age)
    _put_text(page, "sex", sex)
    _put_text(page, "reaction_onset", _reaction_onset_lines(cioms) or "UK", size=7)
    _put_text(page, "narrative", _narrative_text(cioms) or "UK", size=7)

    _put_check(page, "seriousness_death", bool(cioms.get("seriousness_death")))
    _put_check(page, "seriousness_life_threatening", bool(cioms.get("seriousness_life_threatening")))
    _put_check(page, "seriousness_hospitalization", bool(cioms.get("seriousness_hospitalization")))
    _put_check(page, "seriousness_disability", bool(cioms.get("seriousness_disability")))
    _put_check(page, "seriousness_congenital_anomaly", bool(cioms.get("seriousness_congenital_anomaly")))
    _put_check(page, "seriousness_other_medically_important", bool(cioms.get("seriousness_other_medically_important")))

    # Section II
    _put_text(page, "drug14", drug)
    _put_text(page, "dose15", _txt(cioms.get("suspect_drug_dose")) or "UK")
    _put_text(page, "route16", _txt(cioms.get("suspect_drug_route")) or "UK")
    _put_text(page, "indication17", _txt(cioms.get("suspect_drug_indication")) or "UK")
    _put_text(page, "therapy18", therapy or "UK")
    _put_text(page, "duration19", _txt(cioms.get("therapy_duration")) or "UK")

    _put_check(page, "dechallenge_yes", _yn_checked(abate, "YES"))
    _put_check(page, "dechallenge_no", _yn_checked(abate, "NO"))
    _put_check(page, "dechallenge_na", _yn_checked(abate, "NA"))
    _put_check(page, "rechallenge_yes", _yn_checked(reappear, "YES"))
    _put_check(page, "rechallenge_no", _yn_checked(reappear, "NO"))
    _put_check(page, "rechallenge_na", _yn_checked(reappear, "NA"))

    # Section III
    _put_text(page, "concomitant22", _txt(cioms.get("concomitant_medications")) or "UK", size=7)
    _put_text(page, "history23", _txt(cioms.get("medical_history")) or "UK", size=7)

    # Section IV
    _put_text(page, "mfr24a", _txt(cioms.get("manufacturer_name_address")) or "UK", size=7)
    _put_text(page, "remarks26", _txt(cioms.get("company_comment")) or "UK", size=7)
    _put_text(page, "mfr24b", _txt(cioms.get("mfr_control_no")) or "UK")
    _put_text(page, "recv24c", _txt(cioms.get("date_received_manufacturer")) or "UK")
    _put_text(page, "report_date", _txt(cioms.get("date_of_report")) or "UK")
    _put_text(page, "reporter25b", reporter or "UK", size=7)

    for label, key in [
        ("STUDY", "source_study"),
        ("LITERATURE", "source_literature"),
        ("AUTHORITY", "source_authority"),
        ("HEALTH PROFESSIONAL", "source_hp"),
        ("OTHER", "source_other"),
    ]:
        _put_check(page, key, src == label)

    for label, key in [
        ("INITIAL", "type_initial"),
        ("FOLLOWUP", "type_followup"),
        ("FINAL", "type_final"),
    ]:
        _put_check(page, key, rt == label)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()
    return output_path
