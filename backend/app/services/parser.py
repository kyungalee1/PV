"""Extract PV lead information from PDF, Excel, and text sources."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

from app.schemas import CiomsFormData
from app.services.literature_extractor import extract_cioms_from_literature

# Keyword maps (Korean + English) -> CIOMS field hints
AE_KEYWORDS = re.compile(
    r"(?:adverse\s*event|ae\b|adr|부작용|이상반응|약물이상반응|"
    r"serious\s*adverse|sae\b|중대한|중대이상)",
    re.I,
)
SAE_KEYWORDS = re.compile(r"(?:\bsae\b|serious|중대|life.?threat|death|사망|입원)", re.I)
DRUG_KEYWORDS = re.compile(
    r"(?:suspect|drug|medication|product|의약품|약물|투여|제품명|"
    r"active\s*substance|성분)",
    re.I,
)
PATIENT_KEYWORDS = re.compile(
    r"(?:patient|subject|환자|피험자|age|sex|gender|성별|나이|체중)",
    re.I,
)
DATE_PATTERN = re.compile(
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})"
)

# Large literature PDFs: cap pages to avoid long blocking parses
MAX_PDF_PAGES = 50
MAX_PDF_TABLES_PER_PAGE = 5


def _clean(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _parse_date(text: str) -> str:
    for m in DATE_PATTERN.finditer(text):
        raw = m.group(1).replace("/", "-").replace(".", "-")
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


def _find_label_value(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*[:：]\s*(.+?)(?:\n|$)",
            re.I,
        )
        m = pattern.search(text)
        if m:
            return m.group(1).strip()[:500]
    return ""


def _sheet_to_text(df: pd.DataFrame) -> str:
    lines = []
    for _, row in df.iterrows():
        cells = [_clean(c) for c in row.values if _clean(c)]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def extract_from_pdf(path: Path) -> tuple[str, list[dict[str, Any]]]:
    texts: list[str] = []
    tables: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages[:MAX_PDF_PAGES]):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if t.strip():
                    texts.append(t)
                try:
                    page_tables = page.extract_tables() or []
                except Exception:
                    page_tables = []
                for ti, table in enumerate(page_tables[:MAX_PDF_TABLES_PER_PAGE]):
                    if not table:
                        continue
                    headers = [_clean(h) for h in (table[0] if table else [])]
                    rows = []
                    for row in table[1:]:
                        rows.append(dict(zip(headers, [_clean(c) for c in row])))
                    tables.append({"page": i + 1, "table_index": ti, "rows": rows})
            if total > MAX_PDF_PAGES:
                texts.append(
                    f"[Note: PDF has {total} pages; first {MAX_PDF_PAGES} pages were parsed.]"
                )
    except Exception as exc:
        raise ValueError(f"Cannot read PDF: {exc}") from exc
    return "\n\n".join(texts), tables


def extract_from_excel(path: Path) -> tuple[str, list[dict[str, Any]]]:
    xl = pd.ExcelFile(path)
    parts: list[str] = []
    tables: list[dict[str, Any]] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=None)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        # Promote first row to header if it looks like labels
        first = df.iloc[0].astype(str).str.len().mean()
        if first < 40 and len(df) > 1:
            df.columns = [_clean(c) for c in df.iloc[0]]
            df = df.iloc[1:].reset_index(drop=True)
        text = _sheet_to_text(df)
        parts.append(f"[Sheet: {sheet}]\n{text}")
        rows = df.fillna("").astype(str).to_dict(orient="records")
        tables.append({"sheet": sheet, "rows": rows[:200]})
    return "\n\n".join(parts), tables


def extract_from_text(path: Path) -> tuple[str, list[dict[str, Any]]]:
    return path.read_text(encoding="utf-8", errors="ignore"), []


def _infer_ae_from_tables(tables: list[dict[str, Any]]) -> str:
    ae_cols = (
        "ae",
        "adverse event",
        "adr",
        "reaction",
        "event",
        "pt",
        "verbatim",
        "이상반응",
        "부작용",
        "ae명",
    )
    for tbl in tables:
        for row in tbl.get("rows", []):
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                kl = _clean(k).lower()
                if any(c in kl for c in ae_cols) and _clean(v):
                    return _clean(v)
    return ""


def _infer_sae(text: str, tables: list[dict[str, Any]]) -> bool:
    if SAE_KEYWORDS.search(text):
        return True
    for tbl in tables:
        for row in tbl.get("rows", []):
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                kl = _clean(k).lower()
                vl = _clean(v).lower()
                if "sae" in kl or "serious" in kl:
                    if vl in ("y", "yes", "true", "1", "예", "o"):
                        return True
                if vl in ("sae", "serious", "yes", "y"):
                    return True
    return False


def build_cioms_from_content(
    text: str,
    tables: list[dict[str, Any]],
    source_type: str,
) -> CiomsFormData:
    if source_type == "literature":
        return extract_cioms_from_literature(text)
    ae = _find_label_value(
        text,
        [
            "Adverse Event",
            "AE",
            "Reaction",
            "Event term",
            "이상반응",
            "부작용",
            "AE명",
        ],
    ) or _infer_ae_from_tables(tables)

    drug = _find_label_value(
        text,
        [
            "Suspect drug",
            "Drug name",
            "Product",
            "Medicinal product",
            "의약품",
            "제품명",
            "Suspected medicinal product",
        ],
    )
    narrative_parts = [text[:4000]] if text else []
    for tbl in tables[:3]:
        for row in tbl.get("rows", [])[:5]:
            if isinstance(row, dict):
                narrative_parts.append(" | ".join(f"{k}: {v}" for k, v in row.items() if _clean(v)))

    is_sae = _infer_sae(text, tables)
    onset = _find_label_value(text, ["Onset", "Start date", "발현일", "Reaction onset"]) or _parse_date(text)

    source_cioms = {
        "clinical_data": "STUDY",
        "literature": "LITERATURE",
        "sae_form": "HEALTH PROFESSIONAL",
        "email": "OTHER",
        "spontaneous": "HEALTH PROFESSIONAL",
    }.get(source_type, "OTHER")

    return CiomsFormData(
        report_type="Spontaneous" if source_type in ("email", "literature", "spontaneous") else "Study",
        report_source_cioms=source_cioms,
        date_of_report=date.today().isoformat(),
        patient_initials=_find_label_value(text, ["Patient initials", "Initials", "환자 이니셜"]),
        patient_age=_find_label_value(text, ["Age", "나이", "Patient age"]),
        patient_sex=_find_label_value(text, ["Sex", "Gender", "성별"]),
        patient_weight_kg=_find_label_value(text, ["Weight", "체중"]),
        suspect_drug_name=drug,
        suspect_drug_active_substance=_find_label_value(
            text, ["Active substance", "Ingredient", "유효성분"]
        ),
        suspect_drug_dose=_find_label_value(text, ["Dose", "Dosage", "용량", "Daily dose"]),
        suspect_drug_route=_find_label_value(text, ["Route", "투여경로", "Administration route"]),
        suspect_drug_indication=_find_label_value(text, ["Indication", "적응증"]),
        suspect_drug_start_date=_find_label_value(text, ["Drug start", "Therapy start", "투여 시작일"]),
        suspect_drug_stop_date=_find_label_value(text, ["Drug stop", "Therapy end", "투여 종료일"]),
        reaction_meddra_pt=ae,
        reaction_verbatim=ae,
        reaction_onset_date=onset,
        reaction_outcome=_find_label_value(
            text, ["Outcome", "결과", "Event outcome"]
        ),
        seriousness_death=bool(re.search(r"\bdeath\b|사망", text, re.I)),
        seriousness_life_threatening=bool(
            re.search(r"life.?threat|생명", text, re.I)
        ),
        seriousness_hospitalization=bool(
            re.search(r"hospital|입원", text, re.I)
        ),
        narrative="\n".join(narrative_parts)[:8000],
        causality_assessment=_find_label_value(
            text, ["Causality", "Assessment", "인과관계"]
        ),
    )


def detect_source_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        return "clinical_data"
    if "sae" in lower:
        return "sae_form"
    if "mail" in lower or "email" in lower:
        return "email"
    if lower.endswith(".pdf"):
        return "literature"
    return "other"


def parse_uploaded_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    tables: list[dict[str, Any]] = []
    if suffix == ".pdf":
        text, tables = extract_from_pdf(path)
        source = detect_source_type(path.name)
    elif suffix in (".xlsx", ".xls"):
        text, tables = extract_from_excel(path)
        source = "clinical_data"
    elif suffix in (".txt", ".csv"):
        text, tables = extract_from_text(path)
        source = "other"
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    source = detect_source_type(path.name) if source == "other" else source
    cioms = build_cioms_from_content(text, tables, source)
    ae_name = cioms.reaction_meddra_pt or cioms.reaction_verbatim or "Unknown AE"
    is_sae = _infer_sae(text, tables)

    return {
        "source": source,
        "ae_name": ae_name[:500],
        "is_sae": is_sae,
        "collection_date": date.today().isoformat(),
        "cioms": cioms.model_dump(),
        "extracted_text_preview": text[:2000],
        "tables_count": len(tables),
    }
