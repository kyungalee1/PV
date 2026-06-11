"""Extract labeled PV fields from PDF/Excel tables (not raw table dumps)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.services.meddra_coder import code_adverse_event, format_meddra

_DATE_PATTERN = re.compile(
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})",
    re.I,
)
_ONSET_DATE_LABELS = [
    "Reaction onset date", "Onset date", "Date of onset", "AE onset date", "SAE onset date",
    "Event onset date", "Adverse event onset", "Serious adverse event onset",
    "Reaction onset", "Onset of reaction", "Date of event", "Onset",
    "발현일", "이상반응 발생일", "발생일",
]

_AE_LABELS = [
    "Adverse Event", "Adverse reaction", "AE", "AE명", "Reaction", "Event term",
    "이상반응", "부작용", "약물이상반응",
]
_SAE_LABELS = [
    "Serious Adverse Event", "SAE", "SAE명", "중대이상사례", "중대 이상사례",
]
_CASE_INFO_LABELS = [
    "이상사례", "이상사례정보", "이상 사례", "Adverse case", "Case information",
]
_DRUG_LABELS = [
    "Suspect drug", "Drug name", "Medicinal product", "Product name", "의약품", "제품명",
]
_MEDDRA_LABELS = ["MedDRA PT", "MedDRA term", "Preferred Term", "PT"]


def _clean(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def _event_from_verbatim(kind: str, source_label: str, verbatim: str, serious: bool) -> dict[str, Any]:
    coding = code_adverse_event(verbatim)
    return {
        "kind": kind,
        "source_label": source_label,
        "verbatim": verbatim,
        "serious": serious,
        "meddra_pt": coding.pt if coding else "",
        "meddra_code": coding.code if coding else "",
        "meddra_soc": coding.soc if coding else "",
        "meddra_display": format_meddra(coding, verbatim) if coding else verbatim,
    }

# Header / cell text -> (kind, serious)
_LABEL_GROUPS: list[tuple[str, list[str], bool]] = [
    ("SAE", _SAE_LABELS, True),
    ("AE", _AE_LABELS, False),
    ("CASE", _CASE_INFO_LABELS, False),
    ("DRUG", _DRUG_LABELS, False),
    ("MEDDRA", _MEDDRA_LABELS, False),
]

_FIELD_LABEL_HINTS = re.compile(
    r"adverse|reaction|event|ae\b|sae|drug|product|meddra|pt\b|verbatim|"
    r"onset|발현|발생|"
    r"이상|부작|의약|제품|중대|사례",
    re.I,
)


_CITATION_NOISE = re.compile(
    r"journal\s+of\b|"
    r"\b(?:vol\.?|volume|issue|pages?|pp\.?)\b|"
    r"\d+\(\d{4}\)\s*\d+|"
    r"\(\d{4}\)\s*\d+|"
    r"\d+[–\-—]\d+\s*$|"
    r"\belsevier\b|\bspringer\b|\bwiley\b|\bpmid\b|"
    r"\bdoi[\s.:]|"
    r"www\.|https?://|"
    r"clinical\s+neuroscience",
    re.I,
)


def is_table_dump(value: str) -> bool:
    """True when a value looks like a whole table row/ block, not a single field."""
    v = _clean(value)
    if not v:
        return True
    if len(v) > 350:
        return True
    if v.count("|") >= 2:
        return True
    if v.count("\t") >= 2:
        return True
    if len(re.findall(r"\b[FM]/\d+\b", v)) >= 2:
        return True
    if re.search(r"Comorbidities|Laboratory\s*findings|Labora\s*tory", v, re.I) and len(v) > 60:
        return True

    label_hits = 0
    for _, labels, _ in _LABEL_GROUPS:
        for label in labels:
            if re.search(rf"\b{re.escape(label)}\b", v, re.I):
                label_hits += 1
                break
    if label_hits >= 2:
        return True

    segments = [s.strip() for s in re.split(r"[|;\n]", v) if s.strip()]
    if len(segments) >= 4 and sum(1 for s in segments if len(s) < 50) >= 4:
        return True
    return False


def is_citation_or_header_noise(value: str) -> bool:
    """Journal lines, DOI, volume/page refs — not adverse reaction names."""
    v = _clean(value)
    if not v:
        return True
    if _CITATION_NOISE.search(v):
        return True
    if re.search(r"[A-Z][a-z]+\s+(?:of|in)\s+[A-Z][a-z]", v) and re.search(r"\(\d{4}\)", v):
        return True
    if re.match(r"^(received|accepted|published|article)\b", v, re.I):
        return True
    return False


def sanitize_cell_value(value: str, max_len: int = 200) -> str:
    v = _clean(value)
    if is_table_dump(v) or is_citation_or_header_noise(v):
        return ""
    return v[:max_len]


def _label_matches(label: str, pattern: str) -> bool:
    """Match header/cell labels without treating 'Adverse Event' as SAE."""
    low = _clean(label).lower()
    pl = _clean(pattern).lower()
    if not low or not pl:
        return False
    if low == pl:
        return True
    if len(pl) <= 5 and not any(ch.isspace() for ch in pl):
        return bool(re.search(rf"(?:^|\b){re.escape(pl)}(?:\b|$)", low, re.I))
    return bool(re.search(rf"(?:^|\b){re.escape(pl)}(?:\b|$)", low, re.I))


def _classify_label(label: str) -> tuple[str, bool] | None:
    text = _clean(label)
    if not text:
        return None
    low = text.lower()
    for kind, labels, serious in _LABEL_GROUPS:
        for pat in labels:
            if _label_matches(text, pat):
                return kind, serious
    if _FIELD_LABEL_HINTS.search(text) and len(text) < 60:
        if "sae" in low or "serious" in low or "중대" in text:
            return "SAE", True
        if any(x in low for x in ("ae", "adverse", "reaction", "이상", "부작")):
            return "AE", False
        if "drug" in low or "product" in low or "의약" in text or "제품" in text:
            return "DRUG", False
        if "meddra" in low or low == "pt":
            return "MEDDRA", False
        if "사례" in text or "case" in low:
            return "CASE", False
    return None


def _pair_from_row(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract label/value pairs from a table row dict."""
    pairs: list[tuple[str, str]] = []
    for key, val in row.items():
        k = _clean(key)
        v = sanitize_cell_value(val)
        if not v:
            continue
        if _classify_label(k):
            pairs.append((k, v))
            continue
        # Sometimes header is generic ("Field", "Value") — value-only row
        if k.lower() in ("field", "item", "항목", "구분", "label", "column1", ""):
            continue
        if _classify_label(v):
            continue
        if _FIELD_LABEL_HINTS.search(k):
            pairs.append((k, v))
    return pairs


def _pairs_from_raw_table(raw: list[list[Any]]) -> list[tuple[str, str]]:
    """Parse 2-column key/value tables from raw pdfplumber rows."""
    pairs: list[tuple[str, str]] = []
    for row in raw:
        cells = [_clean(c) for c in row if _clean(c)]
        if len(cells) == 2:
            label, val = cells[0], sanitize_cell_value(cells[1])
            if val and (_classify_label(label) or _FIELD_LABEL_HINTS.search(label)):
                pairs.append((label, val))
        elif len(cells) >= 3:
            # Header row: label in col0, value in col1, extra cols ignored for narrative
            label, val = cells[0], sanitize_cell_value(cells[1])
            if val and _classify_label(label):
                pairs.append((label, val))
    return pairs


def extract_labeled_events_from_tables(
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map table cells to AE/SAE/CASE events (structured, not full table paste)."""
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for tbl in tables:
        raw = tbl.get("raw")
        if raw:
            pairs = _pairs_from_raw_table(raw)
        else:
            pairs = []
        for row in tbl.get("rows", []):
            if isinstance(row, dict):
                pairs.extend(_pair_from_row(row))

        for source_label, verbatim in pairs:
            classified = _classify_label(source_label)
            if not classified:
                continue
            kind, serious = classified
            if kind == "DRUG":
                continue  # drug handled separately; skip in 7+13 AE list
            if kind == "MEDDRA" and "code" in source_label.lower():
                continue
            key = (kind, verbatim.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(_event_from_verbatim(kind, source_label, verbatim, serious))

    return events


def strip_table_text_from_body(text: str, tables: list[dict[str, Any]]) -> str:
    """Drop pdfplumber table rows from free text so 7+13 does not paste whole tables."""
    if not tables or not text.strip():
        return text

    row_signatures: list[str] = []
    for tbl in tables:
        for row in tbl.get("raw") or []:
            cells = [_clean(c) for c in row if _clean(c)]
            if len(cells) < 2:
                continue
            row_signatures.append(" ".join(cells))
            row_signatures.append(" | ".join(cells))

    kept: list[str] = []
    for line in text.splitlines():
        s = _clean(line)
        if not s:
            kept.append(line)
            continue
        if is_table_dump(s):
            continue
        if any(len(sig) > 12 and (sig in s or s in sig) for sig in row_signatures):
            continue
        kept.append(line)
    return "\n".join(kept)


def _parse_date_value(text: str) -> str:
    for m in _DATE_PATTERN.finditer(text):
        raw = m.group(1)
        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
            "%B %d, %Y",
            "%B %d %Y",
        ):
            try:
                return datetime.strptime(raw.replace("/", "-").replace(".", "-"), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


def _is_onset_date_label(label: str) -> bool:
    text = _clean(label)
    if not text:
        return False
    low = text.lower()
    if any(_label_matches(text, pat) for pat in _ONSET_DATE_LABELS):
        return True
    if ("onset" in low or "발현" in text or "발생일" in text) and "drug" not in low:
        return True
    return False


def extract_onset_date_from_tables(tables: list[dict[str, Any]]) -> str:
    """Return YYYY-MM-DD for AE/SAE onset from table cells."""
    for tbl in tables:
        for row in tbl.get("raw") or []:
            cells = [_clean(c) for c in row if _clean(c)]
            if len(cells) >= 2 and _is_onset_date_label(cells[0]):
                parsed = _parse_date_value(cells[1])
                if parsed:
                    return parsed
        pairs: list[tuple[str, str]] = []
        raw = tbl.get("raw")
        if raw:
            pairs = _pairs_from_raw_table(raw)
        for row in tbl.get("rows", []):
            if isinstance(row, dict):
                pairs.extend(_pair_from_row(row))
        for label, val in pairs:
            if not _is_onset_date_label(label):
                continue
            parsed = _parse_date_value(val)
            if parsed:
                return parsed
    return ""


def extract_drug_from_tables(tables: list[dict[str, Any]]) -> str:
    for tbl in tables:
        pairs: list[tuple[str, str]] = []
        raw = tbl.get("raw")
        if raw:
            pairs = _pairs_from_raw_table(raw)
        for row in tbl.get("rows", []):
            if isinstance(row, dict):
                pairs.extend(_pair_from_row(row))
        for label, val in pairs:
            kind, _ = _classify_label(label) or ("", False)
            if kind == "DRUG" and val:
                return val
    return ""
