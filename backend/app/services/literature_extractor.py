"""
Extract CIOMS Form I (26 fields) from literature case-report PDFs.

Rules:
- Map case-report content to CIOMS sections I–IV.
- Use UK when information is not stated in the source.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.schemas import CiomsFormData
from app.services.cioms_defaults import (
    any_seriousness,
    apply_cioms_defaults,
    build_reaction_onset_display,
    compute_therapy_duration,
)
from app.services.meddra_coder import MeddraCoding, code_adverse_event, format_meddra
from app.services.pdf_text_utils import repair_pdf_text
from app.services.field_sanitizer import (
    build_prose_narrative_from_cioms,
    is_structured_narrative,
    parse_birth_date,
    parse_flexible_date,
    parse_onset_date,
    prepare_narrative_for_display,
    sanitize_age,
    sanitize_outcome,
    sanitize_sex,
    summarize_narrative,
)
from app.services.narrative_converter import (
    enrich_narrative_with_structured_sources,
    normalize_narrative_symbols,
)
from app.services.table_field_extractor import (
    extract_drug_from_tables,
    extract_labeled_events_from_tables,
    extract_onset_date_from_tables,
    is_citation_or_header_noise,
    is_table_dump,
    strip_table_text_from_body,
)

UK = "UK"
DATE_PATTERN = re.compile(
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
    re.I,
)


def _normalize_text(text: str) -> str:
    """Repair PDF spacing artifacts and normalize whitespace."""
    return repair_pdf_text(text)


def _is_metadata_noise(sentence: str) -> bool:
    low = sentence.lower()
    if re.search(
        r"article\s*history|article\s*info|keywords?\s*:|title\s*:|"
        r"received\s+\d|accepted\s+\d|doi[\s.:]|correspondence\s*:",
        low,
    ):
        return True
    # Long glued blob with almost no spaces
    if len(sentence) > 60 and sentence.count(" ") < len(sentence) / 20:
        return True
    return False


def _clean(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def _uk(val: str) -> str:
    return _clean(val) or UK


def _case_report_body(text: str) -> str:
    # Section header only — avoid matching "Case reports" keywords or citations.
    m = re.search(r"(?:^|\n)\s*CASE\s+REPORT\s*(?:\n|$)", text, re.I | re.M)
    if not m:
        m = re.search(r"\nCASE\s+REPORT\b", text, re.I)
    if m:
        body = text[m.start() :]
        disc = re.search(r"\n\s*DISCUSSION\b", body, re.I)
        return body[: disc.start()] if disc else body
    return text


def _first_match(patterns: list[str], text: str, flags: int = re.I | re.S) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return _clean(m.group(1) if m.lastindex else m.group(0))
    return ""


_AE_LABELS = [
    "Adverse Event",
    "Adverse event",
    "Adverse reaction",
    "Adverse Reaction",
    "Adverse drug reaction",
    "Adverse Drug Reaction",
    "ADR",
    "AE",
    "AR",
    "AE명",
    "AE name",
    "AE term",
    "Reaction",
    "Event term",
    "Reaction term",
    "Verbatim term",
    "Side effect",
    "Side effects",
    "Drug-related reaction",
    "이상반응",
    "부작용",
    "약물이상반응",
    "약물 이상반응",
]

_SAE_LABELS = [
    "Serious Adverse Event",
    "Serious adverse event",
    "SAE",
    "SAE명",
    "SAE name",
    "SAE term",
    "중대이상사례",
    "중대 이상사례",
    "중대한 이상사례",
]

_CASE_INFO_LABELS = [
    "이상사례",
    "이상사례정보",
    "이상 사례",
    "이상 사례 정보",
    "Adverse case",
    "Case information",
    "Adverse case information",
    "이상사례 정보",
]

_MEDDRA_LABELS = [
    "MedDRA PT",
    "MedDRA term",
    "Preferred Term",
    "PT",
    "MedDRA code",
    "MedDRA Code",
]

_DRUG_LABELS = [
    "Suspect drug",
    "Suspect Drug",
    "Suspect drug(s)",
    "Suspected drug",
    "Suspected medicinal product",
    "Causative drug",
    "Implicated drug",
    "Drug name",
    "Medicinal product",
    "Product name",
    "Generic name",
    "의약품",
    "제품명",
    "의심의약품",
    "원인의약품",
    "원인 의약품",
    "14. Suspect drug",
]

_SUBSTANCE_LABELS = [
    "Active substance",
    "Active ingredient",
    "Ingredient",
    "Generic name",
    "INN",
    "성분",
    "유효성분",
    "일반명",
]

# Known company-product patterns (name, optional INN/substance)
_KNOWN_PRODUCTS: list[tuple[str, str, str]] = [
    (r"\bIVIg\b", "IVIg", "Intravenous immunoglobulin"),
    (r"\bIVIG\b", "IVIG", "Intravenous immunoglobulin"),
    (r"intravenous immunoglobulin", "Intravenous immunoglobulin", "Immunoglobulin normal human"),
    (r"fibrin\s+glue", "Fibrin glue", "Fibrin sealant"),
    (r"\bUrokinase\b", "Urokinase", "Urokinase"),
    (r"Greenplast-[A-Z0-9]+", "", ""),  # name from match
]

_DRUG_NAME_STOPWORDS = frozenset({
    "patient", "hospital", "infusion", "therapy", "treatment", "administration",
    "reaction", "adverse", "event", "symptoms", "symptom", "january", "february",
    "march", "april", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "korea", "united", "states", "kingdom", "report",
    "following", "after", "before", "during", "generalized", "redness",
    "forearms", "antihistaminic", "hydrocortisone", "amoxicillin", "cefixime",
})

_ONSET_DATE_LABELS = [
    "Reaction onset date",
    "Onset date",
    "Date of onset",
    "AE onset date",
    "SAE onset date",
    "ADR onset date",
    "Event onset date",
    "Adverse event onset",
    "Serious adverse event onset",
    "Side effect onset",
    "Reaction onset",
    "Onset of reaction",
    "Date of event",
    "Onset",
    "발현일",
    "이상반응 발생일",
    "부작용 발생일",
    "발생일",
]

# Abbreviation + full-term patterns for drug-related AE detection
_KNOWN_AE_PATTERNS: list[tuple[str, str]] = [
    (r"\badr\b", "Adverse drug reaction"),
    (r"adverse\s+drug\s+reaction", "Adverse drug reaction"),
    (r"\bae\b", "Adverse event"),
    (r"adverse\s+event", "Adverse event"),
    (r"adverse\s+reaction", "Adverse reaction"),
    (r"side\s+effect", "Side effect"),
    (r"drug[- ]?related\s+reaction", "Drug-related reaction"),
    (r"ischemic\s+stroke", "Ischemic stroke"),
    (r"ischaemic\s+stroke", "Ischaemic stroke"),
    (r"pulmonary\s+embol", "Pulmonary embolism"),
    (r"transient\s+enhancing\s+lesion", "Transient enhancing lesion"),
    (r"\btec\b", "Transient enhancing lesion"),
    (r"persistent\s+diplopia", "Persistent diplopia"),
    (r"limited\s+eyeball\s+movement", "Limited eyeball movement"),
    (r"diplopia", "Diplopia"),
    (r"hepatotoxicity", "Hepatotoxicity"),
    (r"anaphylaxis", "Anaphylactic reaction"),
    (r"hypotension", "Hypotension"),
    (r"urticaria", "Urticaria"),
    (r"rash", "Rash"),
    (r"nausea", "Nausea"),
    (r"vomiting", "Vomiting"),
    (r"이상반응", "Adverse reaction"),
    (r"부작용", "Side effect"),
    (r"약물이상반응", "Adverse drug reaction"),
]


def _is_invalid_drug_name(value: str) -> bool:
    v = _clean(value)
    if not v or len(v) < 2:
        return True
    if is_citation_or_header_noise(v) or is_table_dump(v):
        return True
    if re.match(r"^(UK|NA|N/A|unknown|none)$", v, re.I):
        return True
    if re.search(r"^F/\d+|^M/\d+|^patient\b|^case report\b", v, re.I):
        return True
    if re.search(r"journal of|case report|abstract|introduction", v, re.I):
        return True
    # Narrative fragments mis-read as drug names (e.g. "The flow rate was" + dose "16 cc")
    if re.search(
        r"\b(the|a|an|this|that|it|he|she|they|we)\b",
        v,
        re.I,
    ) and re.search(r"\b(was|were|is|are|began|reduced|after|before|with)\b", v, re.I):
        return True
    if re.search(r"flow\s*rate|flowr\s*ate|infusion\s+rate|cc/h|ml/h|/h\b", v, re.I):
        return True
    if re.search(r"\b(was|were|reduced|began|completed|experienced|involved)\b\s*$", v, re.I):
        return True
    if len(v.split()) > 6:
        return True
    return False


def _is_infusion_rate_not_dose(value: str) -> bool:
    """Distinguish infusion flow rate (cc/h) from daily dose for field 15."""
    v = _clean(value)
    if not v:
        return True
    return bool(
        re.search(
            r"flow\s*rate|flowr\s*ate|infusion\s+rate|cc/h|ml/h|/h\b|per\s+hour",
            v,
            re.I,
        )
    )


def _infer_suspect_drug_from_text(text: str) -> dict[str, str]:
    """Fallback: infer product/substance/dose when no explicit Suspect drug label."""
    body = _case_report_body(text)
    search = f"{text}\n{body}"

    for label in _DRUG_LABELS + _SUBSTANCE_LABELS:
        val = _find_label_value(search, [label], max_len=150)
        if val and not _is_invalid_drug_name(val):
            dose = _find_label_value(search, ["Daily dose", "Dose", "Dosage", "용량"], max_len=80)
            if dose and _is_infusion_rate_not_dose(dose):
                dose = ""
            return {
                "name": _clean(val),
                "substance": _find_label_value(search, _SUBSTANCE_LABELS, max_len=120) or "",
                "dose": _clean(dose) if dose else "",
            }

    structured = _extract_structured_drug_name(search)
    if structured and not _is_invalid_drug_name(structured):
        return {"name": structured, "substance": structured, "dose": ""}

    for pat, default_name, default_sub in _KNOWN_PRODUCTS:
        m = re.search(pat, search, re.I)
        if m:
            name = default_name or _clean(m.group(0))
            if not _is_invalid_drug_name(name):
                return {
                    "name": name,
                    "substance": default_sub or name,
                    "dose": "",
                }

    infer_patterns = [
        r"(?:administration of|infusion of|infusions? of|treated with|therapy with|"
        r"received|exposure to|following|after)\s+([A-Za-z0-9][A-Za-z0-9 \-/]{1,80}?)"
        r"(?:\s+(?:infusion|administration|therapy|treatment)|[,.]|\s+on\b|\s+at\b)",
        r"(?:after|following)\s+([A-Za-z][A-Za-z0-9 \-/]{2,50})\s+(?:infusion|administration|exposure|therapy)",
        r"(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|cc|µg)(?:/kg)?(?:\s+daily)?)\s+(?:of\s+)?([A-Za-z][A-Za-z0-9 \-]{2,60})",
        r"([A-Za-z][A-Za-z0-9 \-/]{2,60})\s+(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|cc|µg)(?:/kg)?(?:\s+daily)?)",
    ]
    for pat in infer_patterns:
        m = re.search(pat, search, re.I)
        if not m:
            continue
        if m.lastindex and m.lastindex >= 2:
            a, b = m.group(1), m.group(2)
            if re.match(r"^\d", a):
                dose, name = a, b
            else:
                name, dose = a, b
        else:
            name, dose = m.group(1), ""
        name = _clean(name)
        dose = _clean(dose) if dose else ""
        if _is_invalid_drug_name(name):
            continue
        if dose and _is_infusion_rate_not_dose(dose):
            dose = ""
        return {"name": name, "substance": name, "dose": dose}

    aggressive = _aggressive_suspect_drug_fallback(search)
    if aggressive:
        return {"name": aggressive, "substance": aggressive, "dose": ""}

    return {}


def _aggressive_suspect_drug_fallback(text: str) -> str:
    """Last-resort drug name extraction — field 14 must never be UK."""
    if not text:
        return ""
    search = f"{text}\n{_case_report_body(text)}"

    patterns = [
        r"Drug\s+Name\s*[:：]\s*([^,}\n]{2,80})",
        r"(?:Suspect(?:ed)?|Implicated|Causative)\s+(?:drug|medicinal product|product)\s*[:：]?\s*([^\n,;]{2,80})",
        r"(?:enzyme|drug)\s+therapy\s+with\s+([A-Za-z][A-Za-z0-9\-]{2,40})",
        r"therapy\s+with\s+([A-Za-z][A-Za-z0-9\-]{2,40})\s+since\b",
        r"(?:reaction|allergic reaction|urticaria)\s+(?:to|with)\s+([A-Za-z][A-Za-z0-9\-]{2,50})",
        r"(?:related|due)\s+to\s+([A-Za-z][A-Za-z0-9\-]{2,50})",
        r"(?:infusion of|infusion with|received|administered)\s+([A-Za-z][A-Za-z0-9 \-]{2,60})",
        r"The suspected drug is\s+([^\n,.]{2,80})",
        r"- Suspected Drug Information:\s*The suspected drug is\s+([^\n,.(]{2,80})",
        r"\b([A-Z][a-z]{3,}(?:in|mab|zumab|nib|cillin|mycin|vir|stat|ide|ase|olol|pril|sartan|kinase))\b",
    ]
    for pat in patterns:
        m = re.search(pat, search, re.I)
        if not m:
            continue
        candidate = _clean(m.group(1))
        if _is_invalid_drug_name(candidate):
            continue
        if candidate.lower() in _DRUG_NAME_STOPWORDS:
            continue
        return candidate

    for pat, default_name, _ in _KNOWN_PRODUCTS:
        m = re.search(pat, search, re.I)
        if m:
            name = default_name or _clean(m.group(0))
            if name and not _is_invalid_drug_name(name):
                return name
    return ""


def _pick_suspect_drug_name(name: str, substance: str) -> str:
    for candidate in (name, substance):
        val = _clean(candidate)
        if val and val != UK and not _is_invalid_drug_name(val):
            return val
    return ""


def _ensure_suspect_drug(
    drug: dict[str, str],
    text: str,
    tables: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Company PV data always has a suspect product — never leave field 14 as UK."""
    current_name = drug.get("suspect_drug_name", "")
    if current_name != UK and not _is_invalid_drug_name(current_name):
        return drug
    if current_name != UK and _is_invalid_drug_name(current_name):
        drug["suspect_drug_name"] = UK

    table_name = extract_drug_from_tables(tables or [])
    if table_name and not _is_invalid_drug_name(table_name):
        drug["suspect_drug_name"] = _uk(table_name)
        if drug.get("suspect_drug_active_substance") == UK:
            drug["suspect_drug_active_substance"] = _uk(table_name)
        return drug

    inferred = _infer_suspect_drug_from_text(text)
    if inferred.get("name"):
        drug["suspect_drug_name"] = _uk(inferred["name"])
        if inferred.get("substance") and drug.get("suspect_drug_active_substance") == UK:
            drug["suspect_drug_active_substance"] = _uk(inferred["substance"])
        if inferred.get("dose") and drug.get("suspect_drug_dose") == UK:
            drug["suspect_drug_dose"] = _uk(inferred["dose"])

    if drug.get("suspect_drug_name") == UK and drug.get("suspect_drug_active_substance") != UK:
        drug["suspect_drug_name"] = drug["suspect_drug_active_substance"]

    final_name = _pick_suspect_drug_name(
        drug.get("suspect_drug_name", UK),
        drug.get("suspect_drug_active_substance", UK),
    )
    if not final_name:
        fallback = _aggressive_suspect_drug_fallback(text)
        if fallback:
            drug["suspect_drug_name"] = _uk(fallback)
            if drug.get("suspect_drug_active_substance") == UK:
                drug["suspect_drug_active_substance"] = _uk(fallback)

    return drug


def _find_label_value(text: str, labels: list[str], max_len: int = 300) -> str:
    hits = _find_all_label_values(text, labels, max_len)
    return hits[0][1] if hits else ""


def _find_all_label_values(
    text: str, labels: list[str], max_len: int = 300
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label in labels:
        for m in re.finditer(
            rf"{re.escape(label)}\s*[:：]\s*([^\n.]{{1,{max_len}}})",
            text,
            re.I,
        ):
            val = _clean(m.group(1).rstrip(",;"))
            if not val or val.lower() in ("na", "n/a", "unknown", "uk", "-"):
                continue
            if is_table_dump(val):
                continue
            key = val.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((label, val[:max_len]))
    return found


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


def _extract_labeled_events(text: str) -> list[dict[str, Any]]:
    """Extract AE / SAE / 이상사례정보 labels and apply MedDRA coding."""
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    groups = [
        ("SAE", _SAE_LABELS, True),
        ("AE", _AE_LABELS, False),
        ("CASE", _CASE_INFO_LABELS, False),
    ]
    for kind, labels, serious in groups:
        for source_label, verbatim in _find_all_label_values(text, labels):
            key = (kind, verbatim.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(_event_from_verbatim(kind, source_label, verbatim, serious))

    # Document-level MedDRA PT + code fields
    doc_pt = _find_label_value(text, ["MedDRA PT", "MedDRA term", "Preferred Term"])
    doc_code = _first_match([r"(?:MedDRA\s*)?(?:code|Code)\s*[:：]\s*(100\d{5})", r"\b(100\d{5})\b"], text)
    if doc_pt:
        verbatim = doc_pt
        if doc_code and doc_code not in verbatim:
            coding = MeddraCoding(_clean(doc_pt), doc_code, match_type="source")
        else:
            coding = code_adverse_event(doc_pt)
        key = ("MEDDRA", verbatim.lower())
        if key not in seen:
            seen.add(key)
            events.append(
                {
                    "kind": "MedDRA",
                    "source_label": "MedDRA PT",
                    "verbatim": verbatim,
                    "serious": False,
                    "meddra_pt": coding.pt if coding else doc_pt,
                    "meddra_code": coding.code if coding else (doc_code or ""),
                    "meddra_soc": coding.soc if coding else "",
                    "meddra_display": format_meddra(coding, verbatim) if coding else verbatim,
                }
            )

    return events


def _dedupe_labeled_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer SAE over AE when verbatim is identical; drop redundant MedDRA rows."""
    by_verbatim: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for ev in events:
        key = _clean(ev.get("verbatim", "")).lower()
        if not key:
            continue
        if key not in by_verbatim:
            order.append(key)
            by_verbatim[key] = ev
            continue
        existing = by_verbatim[key]
        if ev.get("serious") and not existing.get("serious"):
            by_verbatim[key] = ev

    out = [by_verbatim[k] for k in order]
    codes = {ev.get("meddra_code") for ev in out if ev.get("meddra_code")}
    filtered: list[dict[str, Any]] = []
    for ev in out:
        if ev.get("kind") == "MedDRA" and ev.get("meddra_code") in codes and len(out) > 1:
            # Skip duplicate MedDRA PT row when AE/SAE already carries same code
            if any(
                e.get("kind") != "MedDRA" and e.get("meddra_code") == ev.get("meddra_code")
                for e in out
            ):
                continue
        filtered.append(ev)
    return filtered


NARRATIVE_MAX_CHARS = 850
NARRATIVE_STRUCTURED_MAX_CHARS = 2800


def _shorten_for_narrative(text: str, max_len: int = 100) -> str:
    s = _clean(text)
    if len(s) <= max_len:
        return s
    cut = s[: max_len - 3].rsplit(" ", 1)[0]
    return (cut or s[: max_len - 3]) + "..."


def _format_event_line(ev: dict[str, Any]) -> str:
    kind = ev.get("kind", "AE")
    src = ev.get("source_label") or (
        "SAE명" if kind == "SAE" else "AE명" if kind == "AE" else "이상사례정보"
    )
    serious_note = " [Serious]" if ev.get("serious") else ""
    verbatim = ev.get("verbatim") or UK
    display = ev.get("meddra_display")
    if not display or "MedDRA" not in display:
        coding = code_adverse_event(verbatim)
        display = format_meddra(coding, verbatim) if coding else verbatim
    label = "SAE" if kind == "SAE" else "AE" if kind in ("AE", "MedDRA") else kind
    return f"- {label} ({src}){serious_note}: {display}"


def _compact_narrative(
    reaction: dict[str, Any],
    drug: dict[str, str],
    patient: dict[str, str],
) -> str:
    """Short 7+13 as narrative prose (not symbol/bullet dumps)."""
    return build_prose_narrative_from_cioms(
        {
            "patient_sex": patient.get("patient_sex"),
            "patient_age": patient.get("patient_age"),
            "patient_weight_kg": patient.get("patient_weight_kg"),
            "suspect_drug_name": drug.get("suspect_drug_name"),
            "suspect_drug_active_substance": drug.get("suspect_drug_active_substance"),
            "suspect_drug_dose": drug.get("suspect_drug_dose"),
            "suspect_drug_route": drug.get("suspect_drug_route"),
            "suspect_drug_indication": drug.get("suspect_drug_indication"),
            "reaction_verbatim": reaction.get("reaction_verbatim") or reaction.get("labeled_ae"),
            "reaction_meddra_pt": reaction.get("reaction_meddra_pt"),
            "reaction_outcome": reaction.get("reaction_outcome"),
            "causality_assessment": reaction.get("causality_sentence"),
        }
    )


def _compact_narrative_from_cioms(cioms: dict[str, Any]) -> str:
    """Compact long narratives built outside literature_extractor (e.g. parser dump)."""
    reaction = {
        "labeled_events": [],
        "labeled_ae": cioms.get("reaction_verbatim") or cioms.get("reaction_meddra_pt"),
        "labeled_sae": "",
        "reaction_verbatim": cioms.get("reaction_verbatim"),
        "reaction_meddra_pt": cioms.get("reaction_meddra_pt"),
        "reaction_outcome": cioms.get("reaction_outcome"),
        "causality_sentence": cioms.get("causality_assessment"),
    }
    drug = {
        "suspect_drug_name": cioms.get("suspect_drug_name"),
        "suspect_drug_dose": cioms.get("suspect_drug_dose"),
        "suspect_drug_route": cioms.get("suspect_drug_route"),
    }
    patient = {
        "patient_age": cioms.get("patient_age"),
        "patient_sex": cioms.get("patient_sex"),
    }
    return _compact_narrative(reaction, drug, patient)


def finalize_narrative(
    narrative: str,
    *,
    reaction: dict[str, Any] | None = None,
    drug: dict[str, str] | None = None,
    patient: dict[str, str] | None = None,
    cioms: dict[str, Any] | None = None,
) -> str:
    """Return narrative prose; never rewrite structured text into symbol bullets."""
    if narrative and narrative != UK:
        cleaned = normalize_narrative_symbols(narrative)
        if is_structured_narrative(cleaned):
            return summarize_narrative(cleaned)
        if len(cleaned) <= NARRATIVE_STRUCTURED_MAX_CHARS:
            return summarize_narrative(cleaned)
        return summarize_narrative(_shorten_for_narrative(cleaned, NARRATIVE_STRUCTURED_MAX_CHARS))
    if reaction is not None:
        return _compact_narrative(reaction, drug or {}, patient or {})
    if cioms is not None:
        return build_prose_narrative_from_cioms(cioms)
    return UK


def _drug_search_terms(drug: dict[str, str]) -> list[str]:
    terms: list[str] = []
    for key in ("suspect_drug_name", "suspect_drug_active_substance"):
        val = _clean(drug.get(key, ""))
        if not val or val == UK:
            continue
        terms.append(val)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", val):
            if len(token) >= 4 and token.lower() not in {"glue", "sealant", "drug"}:
                terms.append(token)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _context_links_drug_and_term(text: str, drug_terms: list[str], term: str) -> bool:
    """True when suspect drug and reaction term appear in the same local context."""
    if not term or is_citation_or_header_noise(term):
        return False
    if not drug_terms:
        return True
    term_esc = re.escape(term[: min(len(term), 40)])
    drug_pat = re.compile(
        "|".join(re.escape(t) for t in drug_terms if len(t) >= 3),
        re.I,
    )
    for m in re.finditer(term_esc, text, re.I):
        window = text[max(0, m.start() - 220) : min(len(text), m.end() + 220)]
        if drug_pat.search(window):
            return True
    return False


def _extract_onset_near_term(
    text: str,
    term: str,
    tables: list[dict[str, Any]] | None = None,
) -> str:
    """Find flexible onset date near a specific reaction term."""
    if tables:
        term_low = term.lower()
        for tbl in tables:
            for row in tbl.get("rows", []):
                if not isinstance(row, dict):
                    continue
                row_text = " ".join(str(v) for v in row.values())
                if term_low not in row_text.lower():
                    continue
                for val in row.values():
                    parsed = parse_flexible_date(str(val))
                    if parsed:
                        return parsed

    term_esc = re.escape(term[: min(len(term), 40)])
    for m in re.finditer(term_esc, text, re.I):
        window = text[max(0, m.start() - 160) : min(len(text), m.end() + 160)]
        for label in _ONSET_DATE_LABELS:
            raw = _find_label_value(window, [label], max_len=60)
            if raw:
                parsed = parse_flexible_date(raw)
                if parsed:
                    return parsed
        for pat in (
            r"onset\s*(?:on|date)?\s*[:：]?\s*([^\n,;]{4,40})",
            r"(\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?)",
            r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},?\s+\d{4})",
            r"\b(19|20)\d{2}\b",
        ):
            dm = re.search(pat, window, re.I)
            if dm:
                parsed = parse_flexible_date(dm.group(1) if dm.lastindex else dm.group(0))
                if parsed:
                    return parsed
    return ""


def _reaction_display_name(verbatim: str) -> str:
    coding = code_adverse_event(verbatim)
    return format_meddra(coding, verbatim) if coding else verbatim


def _collect_drug_related_reactions(
    text: str,
    body: str,
    drug: dict[str, str],
    labeled_events: list[dict[str, Any]],
    drug_ae_sentences: list[str],
    tables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """All suspect-drug-related AEs/ADRs with per-reaction onset."""
    drug_terms = _drug_search_terms(drug)
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_event(
        verbatim: str,
        kind: str = "AE",
        serious: bool = False,
        onset: str = "",
        from_label: bool = False,
    ) -> None:
        v = _clean(verbatim)
        if not v or is_citation_or_header_noise(v) or is_table_dump(v):
            return
        key = v.lower()
        if key in seen:
            return
        if not from_label:
            linked = _context_links_drug_and_term(body, drug_terms, v)
            in_drug_sent = any(v.lower() in s.lower() for s in drug_ae_sentences)
            if not linked and not in_drug_sent:
                return
        seen.add(key)
        on = onset or _extract_onset_near_term(f"{text}\n{body}", v, tables)
        if not on:
            on = _extract_global_onset(text, body, tables)
        display = _reaction_display_name(v)
        coding = code_adverse_event(v)
        collected.append(
            {
                "kind": kind,
                "verbatim": v,
                "display": display,
                "short_name": (coding.pt if coding else v)[:60],
                "serious": serious or kind == "SAE",
                "onset": on or UK,
            }
        )

    for ev in labeled_events:
        if ev.get("kind") in ("AE", "SAE", "CASE", "MedDRA"):
            add_event(
                ev.get("verbatim", ""),
                kind="SAE" if ev.get("serious") or ev.get("kind") == "SAE" else "AE",
                serious=bool(ev.get("serious")),
                from_label=True,
            )

    for _label, val in _find_all_label_values(text, _AE_LABELS, max_len=200):
        add_event(val, kind="AE", from_label=True)

    for _label, val in _find_all_label_values(text, _SAE_LABELS, max_len=200):
        add_event(val, kind="SAE", serious=True, from_label=True)

    search_scope = "\n".join(drug_ae_sentences) if drug_ae_sentences else body
    for pat, label in _KNOWN_AE_PATTERNS:
        if not re.search(pat, search_scope, re.I):
            continue
        if label.lower() in seen:
            continue
        if _context_links_drug_and_term(body, drug_terms, label) or drug_ae_sentences:
            add_event(label)

    return collected


def _extract_global_onset(
    text: str,
    body: str,
    tables: list[dict[str, Any]] | None = None,
) -> str:
    if tables:
        table_date = extract_onset_date_from_tables(tables)
        if table_date:
            return parse_flexible_date(table_date) or table_date
    for label in _ONSET_DATE_LABELS:
        raw = _find_label_value(text, [label], max_len=80)
        if raw and not is_table_dump(raw):
            parsed = parse_flexible_date(raw)
            if parsed:
                return parsed
    for pat in (
        r"(?:onset|started|developed)\s+(?:on\s+)?"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{4})",
        r"(?:onset|started|developed)\s+(?:on\s+)?(\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?)",
        r"(?:onset|started|developed)\s+(?:on\s+)?(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
    ):
        m = re.search(pat, body, re.I)
        if m:
            parsed = parse_flexible_date(m.group(1))
            if parsed:
                return parsed
    return ""


def _format_multi_reaction_fields(
    events: list[dict[str, Any]],
    is_sae: bool = False,
) -> tuple[str, str, str, str]:
    """Build reaction_meddra_pt, reaction_verbatim, onset_date, onset_display."""
    if not events:
        return UK, UK, UK, UK

    prefix = "[SAE] " if is_sae else ""
    displays = [ev["display"] for ev in events]
    pt = prefix + "; ".join(displays)
    verbatim = prefix + "; ".join(ev["verbatim"] for ev in events)

    if len(events) == 1:
        onset = events[0].get("onset") or UK
        onset_display = onset
    else:
        pairs = [f"{ev['short_name']}: {ev.get('onset') or UK}" for ev in events]
        onset_display = "; ".join(pairs)
        onset = onset_display

    return _uk(pt), _uk(verbatim), onset, onset_display


def _extract_case_title(text: str) -> str:
    """Paper/case title — not journal citation lines."""
    explicit = _first_match(
        [
            r"Title\s*[:：]\s*([^\n]+)",
            r"^([^\n]{15,200}(?:after|following|associated with|induced by|related to)[^\n]{3,120})$",
        ],
        text,
        re.M,
    )
    if explicit and not is_citation_or_header_noise(explicit):
        return explicit

    for line in text.splitlines():
        s = _clean(line)
        if len(s) < 15 or is_citation_or_header_noise(s):
            continue
        if re.match(
            r"^(CASE REPORT|ABSTRACT|INTRODUCTION|KEYWORDS|ARTICLE|REFERENCES|DISCUSSION)\b",
            s,
            re.I,
        ):
            continue
        if re.search(
            r"patient|stroke|infusion|reaction|toxicity|lesion|syndrome|diplopia|embol|"
            r"hepat|nausea|case report|ivig|tec\b",
            s,
            re.I,
        ):
            return s
    return ""


def _extract_reaction_onset_date(
    text: str,
    body: str,
    tables: list[dict[str, Any]] | None = None,
) -> str:
    """Field 4-6: flexible onset date when a single global date applies."""
    onset = _extract_global_onset(text, body, tables)
    return onset or UK


def _extract_drug_related_ae_sentences(body: str, drug_terms: list[str]) -> list[str]:
    if not drug_terms:
        return []
    drug_pat = re.compile("|".join(re.escape(t) for t in drug_terms), re.I)
    ae_pat = re.compile(
        r"\badr\b|adverse\s+(?:event|reaction|effect|drug\s+reaction)|"
        r"\bae\b|\bar\b|"
        r"(?:suspected|related|due|attributed)\s+(?:to|associated)|"
        r"complication|side\s+effect|toxicity|"
        r"diplopia|hypotension|rash|nausea|hepatotoxic|"
        r"이상반응|부작용|약물이상반응",
        re.I,
    )
    sentences = re.findall(r"[^.!?\n]{25,450}[.!?]", body)
    hits: list[str] = []
    for sent in sentences:
        s = normalize_narrative_symbols(_clean(sent))
        if not s or _is_metadata_noise(s):
            continue
        if is_table_dump(s) or is_citation_or_header_noise(s):
            continue
        if len(s) > 80 and s.count(" ") < len(s) / 18:
            continue
        if drug_pat.search(s) and ae_pat.search(s):
            hits.append(s)
    return hits[:10]


def _parse_date(text: str) -> str:
    parsed = parse_onset_date(text)
    if parsed:
        return parsed
    for m in DATE_PATTERN.finditer(text):
        raw = m.group(1)
        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
            "%B %d, %Y",
            "%B %d %Y",
            "%d %B %Y",
            "%d %B, %Y",
        ):
            try:
                return datetime.strptime(raw.replace("/", "-").replace(".", "-"), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    # e.g. Received 17 October 2020
    m = re.search(
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        text,
        re.I,
    )
    if m:
        for fmt in ("%d %B %Y",):
            try:
                return datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return ""


def _extract_medical_history(body: str) -> str:
    """Field 23 — capture full history across PDF line breaks."""
    if re.search(r"no\s+significant\s+medical\s+history", body, re.I):
        return "No significant medical history"

    # pdfplumber often inserts newlines mid-sentence; flatten for matching
    flat = re.sub(r"\s+", " ", repair_pdf_text(body))

    patterns = [
        r"past\s+medical\s+history\s+[^.]{10,2000}\.",
        r"medical\s+history\s+of\s+[^.]{10,2000}\.",
        r"with\s+a\s+medical\s+history\s+of\s+[^.]{10,2000}\.",
        r"medical\s+history[^.]{10,2000}\.",
        r"medical\s+history[^.]{10,2000}",
        r"history\s+of\s+(?:hypertension|diabetes|angina|[^.]{10,1200})",
    ]
    for pat in patterns:
        m = re.search(pat, flat, re.I)
        if m:
            return _clean(m.group(0).rstrip("."))

    return UK


def _extract_patient(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    age, sex = "", ""

    m = re.search(
        r"(\d{1,3})[- ]?year[- ]?old\s+(male|female|man|woman|boy|girl)\b",
        body,
        re.I,
    )
    if m:
        age = m.group(1)
        sex = m.group(2).lower()
        if sex in ("man", "boy"):
            sex = "male"
        elif sex in ("woman", "girl"):
            sex = "female"

    if not age or not sex:
        fm = re.search(r"\b([FM])/(\d{1,3})\b", body)
        if fm:
            sex = sex or ("female" if fm.group(1).upper() == "F" else "male")
            age = age or fm.group(2)

    sex = sex or _find_label_value(text, ["Sex", "Gender", "성별", "3. Sex"])
    sex = sanitize_sex(sex, full_text=text)
    age = sanitize_age(age) if age else sanitize_age(
        _find_label_value(text, ["Age", "Patient age", "나이", "Age (years)", "2a. Age"])
    )

    initials = _find_label_value(
        text,
        [
            "Patient initials",
            "Initials",
            "환자 이니셜",
            "Patient name",
            "Name of patient",
            "환자명",
            "환자 이름",
        ],
    )
    if not initials:
        initials = _first_match(
            [
                r"patient\s+initials?\s*[:：]\s*([A-Z]{1,3}(?:\s+[A-Z]{1,3})?)",
                r"initials?\s*[:：]\s*([A-Z]{2,4})",
                r"patient\s+name\s*[:：]\s*([A-Za-z][A-Za-z\s\-'.]{1,40})",
                r"환자\s*명\s*[:：]\s*([^\n,]{1,40})",
            ],
            body,
        )

    country = _find_label_value(
        text,
        ["Country", "Country of occurrence", "1a. Country", "발생국", "국가"],
    ) or _first_match(
        [
            r",\s*(Korea|Japan|China|USA|United States|UK|United Kingdom|Germany|France|India)\b",
            r"\b(Korea|Japan|China|USA|United States)\s*$",
        ],
        text,
    )
    if not country:
        if re.search(r"\bKorea\b|Republic of Korea|Seoul", text, re.I):
            country = "Korea"
        elif re.search(r"\bUnited States\b|\bUSA\b", text, re.I):
            country = "USA"

    dob_raw = _find_label_value(
        text, ["Date of birth", "DOB", "Birth date", "생년월일", "2. Date of Birth"]
    ) or _first_match(
        [r"date\s+of\s+birth\s*[:：]\s*([^\n]+)", r"born\s+(?:on\s+)?([^\n,]+)"],
        body,
    )
    dob = parse_birth_date(dob_raw) if dob_raw else ""
    if not dob and dob_raw:
        dob = _clean(dob_raw)[:40] or UK

    history = _extract_medical_history(body)

    return {
        "patient_initials": _uk(initials) if initials else UK,
        "country_of_occurrence": _uk(country),
        "patient_date_of_birth": _uk(dob),
        "patient_age": _uk(str(age)) if age else UK,
        "patient_sex": _uk(sex),
        "medical_history": history,
    }


def _extract_reaction(
    text: str,
    drug: dict[str, str],
    pre_labeled_events: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    norm_text: str | None = None,
) -> dict[str, Any]:
    body = _case_report_body(norm_text or text)

    labeled_events = _dedupe_labeled_events(pre_labeled_events or _extract_labeled_events(text))
    labeled_ae = _find_label_value(text, _AE_LABELS)
    if is_citation_or_header_noise(labeled_ae):
        labeled_ae = ""
    labeled_sae = _find_label_value(text, _SAE_LABELS)
    if is_citation_or_header_noise(labeled_sae):
        labeled_sae = ""

    drug_terms = _drug_search_terms(drug)
    drug_ae_sentences = _extract_drug_related_ae_sentences(body, drug_terms)

    drug_events = _collect_drug_related_reactions(
        text,
        body,
        drug,
        labeled_events,
        drug_ae_sentences,
        tables=tables,
    )

    is_sae_source = bool(labeled_sae) or any(
        ev.get("serious") or ev.get("kind") == "SAE" for ev in drug_events
    )
    pt, verbatim, onset_date, onset_display = _format_multi_reaction_fields(
        drug_events,
        is_sae=is_sae_source,
    )

    if pt == UK:
        title = _extract_case_title(text) or _extract_case_title(body)
        if title and not is_citation_or_header_noise(title):
            coding = code_adverse_event(title)
            display = format_meddra(coding, title) if coding else title
            onset = _extract_global_onset(text, body, tables) or UK
            pt = verbatim = display
            onset_date = onset_display = onset

    outcome = _first_match(
        [
            r"(symptoms?\s+were\s+relieved[^.]{0,120})",
            r"(discharged\s+without\s+additional\s+complications)",
            r"(recovered[^.]{0,80})",
            r"(resolved[^.]{0,80})",
        ],
        body,
    ) or UK

    causality = _first_match(
        [
            r"((?:likely|probably|possibly|suspected)\s+(?:related|associated|due)\s+to[^.]{0,120}\.)",
            r"(attributed\s+to[^.]{0,120}\.)",
            r"(caused\s+by[^.]{0,120}\.)",
        ],
        body,
    )

    return {
        "reaction_meddra_pt": pt,
        "reaction_verbatim": verbatim,
        "reaction_onset_date": onset_date,
        "reaction_onset_display": onset_display,
        "reaction_outcome": outcome,
        "labeled_ae": labeled_ae or (drug_events[0]["verbatim"] if drug_events else ""),
        "labeled_sae": labeled_sae,
        "labeled_events": labeled_events,
        "drug_related_events": drug_events,
        "drug_ae_sentences": drug_ae_sentences,
        "causality_sentence": causality,
        "is_sae": is_sae_source,
    }


def _extract_seriousness(text: str) -> dict[str, bool]:
    body = _case_report_body(text) + " " + text
    low = body.lower()
    flags = {
        "seriousness_death": bool(
            re.search(r"\b(?:died|death|fatal|mortality|사망|dead)\b", low)
        ),
        "seriousness_life_threatening": bool(
            re.search(
                r"life[- ]?threat|life[- ]?threatening|near\s+fatal|생명|"
                r"위독|중증|critical condition",
                low,
            )
        ),
        "seriousness_hospitalization": bool(
            re.search(
                r"\b(?:hospitali[sz]ed|admission|admitted|inpatient|입원|"
                r"emergency\s+department|icu\b|intensive care)\b",
                low,
            )
        ),
        "seriousness_disability": bool(
            re.search(
                r"\b(?:disabilit|incapacit|persistent\s+disabilit|limited\s+eyeball|"
                r"diplopia|significant\s+discomfort|restriction\s+of\s+ocular|"
                r"후유|장애)\b",
                low,
            )
        ),
        "seriousness_congenital_anomaly": bool(
            re.search(r"congenital|birth\s+defect|선천|기형", low)
        ),
        "seriousness_other_medically_important": bool(
            re.search(
                r"medically\s+important|required\s+(?:intervention|surgery|second\s+operation)|"
                r"persistent\s+diplopia|exploratory\s+surgery|serious\s+adverse|"
                r"\bsae\b|중대|중대한\s*유해|중대이상",
                low,
            )
        ),
    }
    return flags


def _extract_structured_drug_name(text: str) -> str:
    """Drug name from narrative blocks like 'Drug Name: Urokinase'."""
    return _first_match(
        [
            r"Drug\s+Name\s*[:：]\s*([^,}\n]{2,80})",
            r"(?:enzyme|drug)\s+therapy\s+with\s+([A-Za-z][A-Za-z0-9\-]{2,40})",
            r"therapy\s+with\s+([A-Za-z][A-Za-z0-9\-]{2,40})\s+since\b",
            r"reaction\s+to\s+([A-Za-z][A-Za-z0-9\-]{2,40})\s+or\s+an\s+ingredient",
        ],
        text,
    ) or ""


def _extract_drug(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    labeled_drug = _find_label_value(text, _DRUG_LABELS)
    if labeled_drug and _is_invalid_drug_name(labeled_drug):
        labeled_drug = ""

    structured_drug = _extract_structured_drug_name(text)
    if structured_drug and _is_invalid_drug_name(structured_drug):
        structured_drug = ""

    drug_line = _first_match(
        [
            r"(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g|mcg|µg|units?)\s+of\s+[^.\n]{5,120}fibrin\s+glue[^.\n]{0,80})",
            r"(fibrin\s+glue\s*\([^)]+\))",
            r"((?:Greenplast[^\n,]{0,40}|fibrin\s+glue)[^\n.]{0,120})",
            r"(?:Suspect|Suspected)\s+drug\s*[:：]\s*([^\n.]{3,120})",
        ],
        body,
    )

    brand = _first_match([r"(Greenplast-[A-Z0-9]+)"], body)
    manufacturer = _first_match(
        [
            r"Green\s+Cross\s+Co\.?,?\s*[^,\n]{0,40}",
            r"([A-Z][A-Za-z\s&]+Co\.?,?\s+[A-Za-z]+,?\s+[A-Za-z]+)",
        ],
        body,
    )

    substance = _find_label_value(text, _SUBSTANCE_LABELS)

    dose = _find_label_value(
        text, ["Daily dose", "Dose", "Dosage", "Daily Dose(s)", "용량"]
    ) or _first_match(
        [
            r"(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g|mcg|µg|units?))\s+of\s+fibrin\s+glue",
            r"fibrin\s+glue[^.\n]{0,40}(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g))",
        ],
        body,
    )
    if dose and _is_infusion_rate_not_dose(dose):
        dose = ""
    qty = _first_match([r"Quantity\s*[:：]\s*([^\n,}]{2,40})"], text)
    if not dose and qty and not _is_infusion_rate_not_dose(qty):
        dose = qty

    route = _find_label_value(
        text, ["Route", "Route of administration", "Administration route", "투여경로"]
    ) or UK
    if re.search(r"applied\s+between|topical|local(?:ly)?|subcutaneous|intravenous|oral|IV\b|PO\b", body, re.I):
        if re.search(r"\bIV\b|intravenous", body, re.I):
            route = "IV"
        elif re.search(r"\bPO\b|oral", body, re.I):
            route = "PO"
        elif re.search(r"applied\s+between|topical|implant", body, re.I):
            route = "Topical (local application)"

    indication = _find_label_value(
        text, ["Indication", "Indications for use", "적응증"]
    ) or _first_match(
        [
            r"for\s+(implant\s+stabilization[^.\n]{0,120})",
            r"indication[s]?\s*[:：]\s*([^\n]+)",
            r"(implant\s+stabilization,\s*hemostasis,\s*and\s*wound\s+healing)",
        ],
        body,
    )

    start_raw = _find_label_value(
        text, ["Therapy start", "Drug start", "Start date", "Therapy from", "투여 시작일"]
    )
    stop_raw = _find_label_value(
        text, ["Therapy end", "Drug stop", "Stop date", "Therapy to", "투여 종료일"]
    )
    start = _parse_date(start_raw) if start_raw else ""
    stop = _parse_date(stop_raw) if stop_raw else ""
    if not start:
        start = _parse_date(
            _first_match([r"from\s+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"], body) or ""
        )
    if not stop:
        stop = _parse_date(
            _first_match([r"to\s+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"], body) or ""
        )

    duration = compute_therapy_duration(_uk(start), _uk(stop))
    if duration == UK:
        dm = re.search(r"(\d+)\s+days?\s+after\s+the\s+first\s+surgery", body, re.I)
        if dm:
            duration = f"{dm.group(1)} days"

    if labeled_drug:
        suspect_name = labeled_drug
        active = substance or labeled_drug
    elif structured_drug:
        suspect_name = structured_drug
        active = substance or structured_drug
    elif drug_line or brand:
        name_parts = []
        if drug_line:
            name_parts.append(drug_line)
        elif brand:
            name_parts.append(f"Fibrin glue ({brand})")
        else:
            name_parts.append("Fibrin glue")
        if brand and brand not in " ".join(name_parts):
            name_parts.append(f"({brand})")
        if dose and dose not in " ".join(name_parts):
            name_parts.append(dose)
        suspect_name = " ".join(name_parts)
        active = substance or (
            "Fibrin glue (fibrin sealant)" if re.search(r"fibrin", suspect_name, re.I) else suspect_name
        )
    else:
        inferred = _infer_suspect_drug_from_text(text)
        if inferred.get("name"):
            suspect_name = inferred["name"]
            active = substance or inferred.get("substance") or inferred["name"]
            if not dose and inferred.get("dose"):
                dose = inferred["dose"]
        elif substance:
            suspect_name = substance
            active = substance
        else:
            suspect_name = UK
            active = UK

    manufacturer = manufacturer or _find_label_value(
        text,
        ["Manufacturer", "Manufacturer name", "Name and address of manufacturer", "제조사"],
        max_len=200,
    )

    return {
        "suspect_drug_name": _uk(suspect_name),
        "suspect_drug_active_substance": _uk(active),
        "suspect_drug_dose": _uk(dose) if dose else UK,
        "suspect_drug_route": _uk(route),
        "suspect_drug_indication": _uk(indication),
        "suspect_drug_start_date": _uk(start),
        "suspect_drug_stop_date": _uk(stop),
        "therapy_duration": duration,
        "manufacturer_name_address": _uk(manufacturer),
    }


def _format_drug14(name: str, substance: str, dose: str = "") -> str:
    """Field 14 — product name and generic/INN only; never UK."""
    n = _pick_suspect_drug_name(name, substance)
    if not n:
        return ""
    s = _clean(substance)
    if _is_invalid_drug_name(s) or s == UK:
        s = ""
    parts = [n]
    if s and s.lower() not in n.lower():
        parts.append(f"({s})")
    return " ".join(parts)


def resolve_suspect_drug_display(cioms: dict[str, Any], source_text: str = "") -> str:
    """Resolve field 14 for HTML/PDF — mandatory suspect drug, no UK."""
    name = _clean(cioms.get("suspect_drug_name"))
    substance = _clean(cioms.get("suspect_drug_active_substance"))
    line = _format_drug14(name, substance)
    if line:
        return line

    search = "\n".join(
        x
        for x in [
            source_text,
            cioms.get("narrative"),
            cioms.get("reaction_verbatim"),
            cioms.get("reaction_meddra_pt"),
            cioms.get("medical_history"),
            cioms.get("causality_assessment"),
            cioms.get("concomitant_medications"),
        ]
        if x and str(x).strip() and str(x).strip() != UK
    )
    drug = _ensure_suspect_drug(
        {
            "suspect_drug_name": name or UK,
            "suspect_drug_active_substance": substance or UK,
            "suspect_drug_dose": _clean(cioms.get("suspect_drug_dose")) or UK,
            "suspect_drug_route": UK,
            "suspect_drug_indication": UK,
            "suspect_drug_start_date": UK,
            "suspect_drug_stop_date": UK,
            "therapy_duration": UK,
            "manufacturer_name_address": UK,
        },
        search,
        None,
    )
    result = _format_drug14(
        drug.get("suspect_drug_name", ""),
        drug.get("suspect_drug_active_substance", ""),
    )
    if result:
        return result
    fallback = _aggressive_suspect_drug_fallback(search)
    return fallback or result


def finalize_cioms_suspect_drug(cioms: dict[str, Any]) -> dict[str, Any]:
    """Fill suspect_drug_* in API payload — field 14 must not be UK/empty."""
    out = dict(cioms)
    source_text = str(out.get("_source_text") or "")
    search = "\n".join(
        x
        for x in [
            source_text,
            out.get("narrative"),
            out.get("reaction_verbatim"),
            out.get("reaction_meddra_pt"),
            out.get("medical_history"),
            out.get("causality_assessment"),
            out.get("concomitant_medications"),
        ]
        if x and str(x).strip() and str(x).strip() != UK
    )
    drug = _ensure_suspect_drug(
        {
            "suspect_drug_name": _clean(out.get("suspect_drug_name")) or UK,
            "suspect_drug_active_substance": _clean(out.get("suspect_drug_active_substance")) or UK,
            "suspect_drug_dose": _clean(out.get("suspect_drug_dose")) or UK,
            "suspect_drug_route": _clean(out.get("suspect_drug_route")) or UK,
            "suspect_drug_indication": _clean(out.get("suspect_drug_indication")) or UK,
            "suspect_drug_start_date": _clean(out.get("suspect_drug_start_date")) or UK,
            "suspect_drug_stop_date": _clean(out.get("suspect_drug_stop_date")) or UK,
            "therapy_duration": _clean(out.get("therapy_duration")) or UK,
            "manufacturer_name_address": _clean(out.get("manufacturer_name_address")) or UK,
        },
        search,
        None,
    )
    name = _pick_suspect_drug_name(
        drug.get("suspect_drug_name", ""),
        drug.get("suspect_drug_active_substance", ""),
    )
    if not name:
        name = _aggressive_suspect_drug_fallback(search)
    if name:
        out["suspect_drug_name"] = name
        substance = _clean(drug.get("suspect_drug_active_substance"))
        if substance and substance != UK and not _is_invalid_drug_name(substance):
            out["suspect_drug_active_substance"] = substance
        elif not out.get("suspect_drug_active_substance") or out.get("suspect_drug_active_substance") == UK:
            out["suspect_drug_active_substance"] = name
    return out


def _extract_dechallenge(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    low = body.lower()
    abate = "NA"
    if re.search(
        r"symptoms?\s+were\s+relieved|relieved\s+without\s+(?:further|additional)|resolved|abated|"
        r"symptoms?\s+were\s+relieved\s+and\s+he\s+was\s+discharged",
        low,
    ):
        abate = "YES"
    elif re.search(r"did\s+not\s+(?:abate|resolve)|persisted|no\s+improvement", low):
        abate = "NO"

    reappear = "NA"
    if re.search(
        r"reappeared|recurred|reintroduction[^.\n]{0,40}(?:symptom|diplopia|complication)",
        low,
    ):
        reappear = "YES"
    elif re.search(
        r"applied\s+again|reintroduction|second\s+operation[^.\n]{0,120}(?:relieved|without\s+complication)",
        low,
    ):
        reappear = "NO"
    elif re.search(r"not\s+re(?:-| )?challenge|no\s+reintroduction", low):
        reappear = "NA"

    return {"dechallenge_abate": abate, "dechallenge_reappear": reappear}


def _extract_concomitant(text: str) -> str:
    body = _case_report_body(text)
    labeled = _find_label_value(
        text,
        [
            "Concomitant drug",
            "Concomitant drugs",
            "Concomitant medications",
            "Concurrent medications",
            "Other medications",
            "병용약",
            "병용 약물",
            "Concurrent drugs",
        ],
        max_len=500,
    )
    if labeled and not is_table_dump(labeled):
        return _clean(labeled)[:500]

    m = re.search(
        r"concomitant(?:\s+medications?|\s+drugs?)?\s*[:：]?\s*([^\n]{10,500})",
        body,
        re.I,
    )
    if m and not is_table_dump(m.group(1)):
        return _clean(m.group(1))[:500]

    if re.search(r"corticosteroid", body, re.I):
        return "Corticosteroid (dosage: UK, dates of administration: UK)"
    return UK


def _extract_report_metadata(text: str) -> dict[str, str]:
    received = _first_match(
        [r"Received\s+([^;\n]+)", r"Received:\s*([^\n]+)", r"Date received\s*[:：]\s*([^\n]+)"],
        text,
    )
    accepted = _first_match([r"Accepted\s+([^;\n]+)", r"Accepted:\s*([^\n]+)"], text)
    published = _first_match([r"Published\s+([^;\n]+)"], text)
    report_label = _find_label_value(
        text, ["Date of report", "Report date", "Date reported", "보고일"]
    )
    recv_date = (
        _parse_date(received)
        or _parse_date(accepted)
        or _parse_date(published)
        or _parse_date(report_label)
    )
    mfr_no = _find_label_value(
        text, ["MFR control no", "Manufacturer control", "Control no", "제조사 번호"]
    )
    return {
        "date_received_manufacturer": _uk(recv_date),
        "date_of_report": recv_date or date.today().isoformat(),
        "mfr_control_no": _uk(mfr_no),
    }


def _extract_reporter(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    name = _find_label_value(
        text, ["Reporter", "Reporter name", "Correspondence", "보고자"]
    ) or _first_match(
        [r"Correspondence:\s*([^\n,]+)", r"Correspondence to:\s*([^\n,]+)"],
        text,
    )
    org = _find_label_value(text, ["Organization", "Affiliation", "Institution"]) or _first_match(
        [
            r"Department\s+of\s+[^\n]+",
            r"([A-Z][^\n]{10,100}(?:Hospital|University|Institute)[^\n]*)",
        ],
        body,
    )
    addr = _first_match(
        [r"(\d+\s+[^\n]{10,80},\s*[^\n]+\d{4,6}[^\n]*)", r"Address\s*[:：]\s*([^\n]+)"],
        text,
    )
    email = _first_match([r"E-mail:\s*([^\s\n]+)", r"Email:\s*([^\s\n]+)"], text)
    reporter_country = _first_match(
        [r"(Korea|Japan|China|USA|United States|UK|Germany|France|India)\b"],
        text,
    )
    return {
        "reporter_name": _uk(name),
        "reporter_organization": _uk(org),
        "reporter_country": _uk(reporter_country),
        "reporter_address": _uk(addr or email),
    }


def _build_narrative(
    text: str,
    patient: dict,
    drug: dict,
    reaction: dict,
    tables: list[dict[str, Any]] | None = None,
) -> str:
    """Field 7+13 — narrative prose; tables/figures/symbols converted to sentences."""
    parts = enrich_narrative_with_structured_sources(
        text,
        tables,
        [],
        patient=patient,
        drug=drug,
        reaction=reaction,
    )

    if not parts:
        body = _case_report_body(text)
        drug_name = drug.get("suspect_drug_name", UK)
        ae_short = (
            reaction.get("labeled_ae")
            or reaction.get("reaction_verbatim")
            or reaction.get("reaction_meddra_pt", UK)
        )
        if ae_short != UK:
            parts.append(f"- Adverse Event: {ae_short}")
        if drug_name != UK and ae_short != UK:
            parts.append(
                f"- Suspected drug-related reaction: Following exposure to {drug_name}, "
                f"the patient developed {ae_short}."
            )
        presentation = _first_match(
            [r"((?:The\s+)?patient[^.]{30,280}\.)"],
            body,
        )
        if presentation and not _is_metadata_noise(presentation):
            parts.append(f"- Case summary: {normalize_narrative_symbols(presentation)}")

    full = "\n\n".join(normalize_narrative_symbols(p) for p in parts) if parts else UK
    structured = any(
        p.startswith("- Patient Information:")
        or p.startswith("- Suspected Drug Information:")
        or p.startswith("- Treatment Process:")
        for p in parts
    )
    if structured and len(full) <= NARRATIVE_STRUCTURED_MAX_CHARS:
        return summarize_narrative(full)
    result = finalize_narrative(full, reaction=reaction, drug=drug, patient=patient)
    return summarize_narrative(result)


def extract_cioms_from_literature(
    text: str,
    tables: list[dict[str, Any]] | None = None,
) -> CiomsFormData:
    """Map literature case-report text to CIOMS Form I (26 fields)."""
    raw_text = text
    if tables:
        raw_text = strip_table_text_from_body(text, tables)
    table_events = extract_labeled_events_from_tables(tables or [])
    pre_labeled = _dedupe_labeled_events(
        table_events + _extract_labeled_events(raw_text)
    )
    norm_text = _normalize_text(raw_text)

    patient = _extract_patient(raw_text)
    drug = _extract_drug(raw_text)
    drug = _ensure_suspect_drug(drug, raw_text, tables)
    reaction = _extract_reaction(
        raw_text, drug, pre_labeled_events=pre_labeled, tables=tables, norm_text=norm_text
    )
    seriousness = _extract_seriousness(raw_text + "\n" + norm_text)
    if any_seriousness(seriousness):
        reaction["is_sae"] = True
        for key in ("reaction_meddra_pt", "reaction_verbatim"):
            val = str(reaction.get(key) or "")
            if val and val != UK and not val.startswith("[SAE]"):
                reaction[key] = f"[SAE] {val}"
    dechallenge = _extract_dechallenge(raw_text)
    reporter = _extract_reporter(raw_text)
    report_meta = _extract_report_metadata(raw_text)
    concomitant = _extract_concomitant(raw_text)

    narrative = _build_narrative(raw_text, patient, drug, reaction, tables=tables)
    onset_display = build_reaction_onset_display(reaction)

    report_type = "INITIAL"
    if re.search(r"\bfollow[- ]?up\b", raw_text, re.I):
        report_type = "FOLLOWUP"
    if re.search(r"\bfinal\s+report\b", raw_text, re.I):
        report_type = "FINAL"

    data = CiomsFormData(
        report_type="Literature",
        report_source_cioms="LITERATURE",
        cioms_report_type=report_type,
        date_of_report=report_meta["date_of_report"],
        country_of_occurrence=patient["country_of_occurrence"],
        patient_initials=patient["patient_initials"],
        patient_date_of_birth=patient["patient_date_of_birth"],
        patient_age=patient["patient_age"],
        patient_sex=patient["patient_sex"],
        medical_history=patient["medical_history"],
        suspect_drug_name=drug["suspect_drug_name"],
        suspect_drug_active_substance=drug["suspect_drug_active_substance"],
        suspect_drug_dose=drug["suspect_drug_dose"],
        suspect_drug_route=drug["suspect_drug_route"],
        suspect_drug_indication=drug["suspect_drug_indication"],
        suspect_drug_start_date=drug["suspect_drug_start_date"],
        suspect_drug_stop_date=drug["suspect_drug_stop_date"],
        therapy_duration=drug["therapy_duration"],
        reaction_meddra_pt=reaction["reaction_meddra_pt"],
        reaction_verbatim=reaction["reaction_verbatim"],
        reaction_onset_date=reaction["reaction_onset_date"],
        reaction_onset_display=onset_display,
        reaction_outcome=reaction["reaction_outcome"],
        seriousness_death=seriousness["seriousness_death"],
        seriousness_life_threatening=seriousness["seriousness_life_threatening"],
        seriousness_hospitalization=seriousness["seriousness_hospitalization"],
        seriousness_disability=seriousness["seriousness_disability"],
        seriousness_congenital_anomaly=seriousness["seriousness_congenital_anomaly"],
        seriousness_other_medically_important=seriousness["seriousness_other_medically_important"],
        dechallenge_abate=dechallenge["dechallenge_abate"],
        dechallenge_reappear=dechallenge["dechallenge_reappear"],
        concomitant_medications=concomitant,
        manufacturer_name_address=drug["manufacturer_name_address"],
        mfr_control_no=report_meta["mfr_control_no"],
        date_received_manufacturer=report_meta["date_received_manufacturer"],
        reporter_name=reporter["reporter_name"],
        reporter_organization=reporter["reporter_organization"],
        reporter_country=reporter["reporter_country"],
        narrative=narrative,
        causality_assessment=_first_match(
            [
                r"(In\s+conclusion,\s+careful\s+attention[^.]{20,250}\.)",
                r"((?:likely|probably|possibly|suspected)\s+(?:related|associated|due)\s+to[^.]{0,120}\.)",
                r"(inappropriate\s+application\s+of\s+fibrin\s+glue[^.]{0,150}\.)",
            ],
            raw_text,
        )
        or UK,
        company_comment=UK,
    )
    return apply_cioms_defaults(data)
