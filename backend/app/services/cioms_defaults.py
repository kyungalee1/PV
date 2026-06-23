"""CIOMS Form I — field defaults, display formatting, and UK fill rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas import CiomsFormData
from app.services.field_sanitizer import (
    format_reaction_onset_field,
    parse_onset_date,
    sanitize_age,
    sanitize_outcome,
    sanitize_sex,
    sanitize_weight,
)
from app.services.english_normalizer import normalize_cioms_to_english
from app.services.meddra_coder import code_adverse_event, format_meddra

UK = "UK"

# String fields that should show UK when empty in the final form
_CIOMS_STRING_FIELDS = (
    "country_of_occurrence",
    "date_of_report",
    "reporter_name",
    "reporter_organization",
    "reporter_country",
    "patient_initials",
    "patient_date_of_birth",
    "patient_age",
    "patient_sex",
    "patient_weight_kg",
    "medical_history",
    "concomitant_medications",
    "suspect_drug_name",
    "suspect_drug_active_substance",
    "suspect_drug_dose",
    "suspect_drug_route",
    "suspect_drug_indication",
    "suspect_drug_start_date",
    "suspect_drug_stop_date",
    "therapy_duration",
    "reaction_meddra_pt",
    "reaction_verbatim",
    "reaction_onset_date",
    "reaction_onset_display",
    "reaction_outcome",
    "manufacturer_name_address",
    "mfr_control_no",
    "date_received_manufacturer",
    "report_source_cioms",
    "cioms_report_type",
    "narrative",
    "causality_assessment",
    "company_comment",
)


def compute_therapy_duration(start: str, stop: str) -> str:
    """Field 19 — duration between therapy start and stop dates."""
    if not start or not stop or start == UK or stop == UK:
        return UK
    try:
        d0 = datetime.strptime(start, "%Y-%m-%d")
        d1 = datetime.strptime(stop, "%Y-%m-%d")
        days = abs((d1 - d0).days)
    except ValueError:
        return UK
    if days == 0:
        return "Same day"
    if days == 1:
        return "1 day"
    if days < 31:
        return f"{days} days"
    if days < 365:
        months = max(1, round(days / 30))
        return f"{months} month(s)" if months > 1 else "1 month"
    years = round(days / 365, 1)
    return f"{years} year(s)"


def build_reaction_onset_display(reaction: dict[str, Any]) -> str:
    """Field 4-6: onset date(s) per reaction when available."""
    from app.services.field_sanitizer import format_reaction_onset_field, parse_flexible_date

    prebuilt = str(reaction.get("reaction_onset_display") or "").strip()
    if prebuilt and prebuilt.upper() != UK:
        return prebuilt
    onset = str(reaction.get("reaction_onset_date") or "").strip()
    if onset and onset.upper() != UK:
        if ";" in onset or ":" in onset:
            return onset
        parsed = parse_flexible_date(onset)
        if parsed:
            return parsed
    for key in ("labeled_ae", "reaction_verbatim", "reaction_meddra_pt", "labeled_sae"):
        parsed = parse_flexible_date(str(reaction.get(key) or ""))
        if parsed:
            return parsed
    return UK


def any_seriousness(seriousness: dict[str, bool]) -> bool:
    return any(seriousness.get(k) for k in (
        "seriousness_death",
        "seriousness_life_threatening",
        "seriousness_hospitalization",
        "seriousness_disability",
        "seriousness_congenital_anomaly",
        "seriousness_other_medically_important",
    ))


def apply_cioms_defaults(data: CiomsFormData) -> CiomsFormData:
    """Fill empty text fields with UK; keep dechallenge NA defaults."""
    updates: dict[str, Any] = {}
    for field in _CIOMS_STRING_FIELDS:
        val = getattr(data, field, "")
        if field in ("suspect_drug_name", "suspect_drug_active_substance"):
            continue  # handled by _ensure_suspect_drug; company data always has a product
        if not str(val or "").strip():
            updates[field] = UK
    if not updates.get("report_source_cioms"):
        updates["report_source_cioms"] = data.report_source_cioms or "LITERATURE"
    if not data.cioms_report_type:
        updates["cioms_report_type"] = "INITIAL"
    if not str(data.dechallenge_abate or "").strip():
        updates["dechallenge_abate"] = "NA"
    if not str(data.dechallenge_reappear or "").strip():
        updates["dechallenge_reappear"] = "NA"
    onset_display = format_reaction_onset_field(
        {
            "reaction_onset_date": data.reaction_onset_date,
            "reaction_onset_display": data.reaction_onset_display,
            "reaction_meddra_pt": data.reaction_meddra_pt,
            "reaction_verbatim": data.reaction_verbatim,
            "narrative": data.narrative,
        }
    )
    if onset_display != UK:
        updates["reaction_onset_display"] = onset_display
        if not str(data.reaction_onset_date or "").strip() or data.reaction_onset_date == UK:
            updates["reaction_onset_date"] = onset_display
    if not str(data.suspect_drug_name or "").strip() or data.suspect_drug_name == UK:
        if str(data.suspect_drug_active_substance or "").strip() and data.suspect_drug_active_substance != UK:
            updates["suspect_drug_name"] = data.suspect_drug_active_substance
    if not str(data.suspect_drug_active_substance or "").strip():
        if str(data.suspect_drug_name or "").strip() and data.suspect_drug_name != UK:
            updates["suspect_drug_active_substance"] = data.suspect_drug_name

    from app.services.literature_extractor import (
        UK as EXTRACTOR_UK,
        _ensure_suspect_drug,
        _is_invalid_drug_name,
        _pick_suspect_drug_name,
    )

    merged = data.model_copy(update=updates) if updates else data
    drug_search_text = "\n".join(
        x
        for x in (
            merged.narrative,
            merged.reaction_verbatim,
            merged.reaction_meddra_pt,
            merged.medical_history,
            merged.causality_assessment,
            merged.concomitant_medications,
        )
        if x and str(x).strip() and str(x).strip() != UK
    )
    needs_drug = not _pick_suspect_drug_name(
        str(merged.suspect_drug_name or ""),
        str(merged.suspect_drug_active_substance or ""),
    )
    if needs_drug and drug_search_text:
        ensured = _ensure_suspect_drug(
            {
                "suspect_drug_name": merged.suspect_drug_name or EXTRACTOR_UK,
                "suspect_drug_active_substance": merged.suspect_drug_active_substance or EXTRACTOR_UK,
                "suspect_drug_dose": merged.suspect_drug_dose or EXTRACTOR_UK,
                "suspect_drug_route": merged.suspect_drug_route or EXTRACTOR_UK,
                "suspect_drug_indication": merged.suspect_drug_indication or EXTRACTOR_UK,
                "suspect_drug_start_date": merged.suspect_drug_start_date or EXTRACTOR_UK,
                "suspect_drug_stop_date": merged.suspect_drug_stop_date or EXTRACTOR_UK,
                "therapy_duration": merged.therapy_duration or EXTRACTOR_UK,
                "manufacturer_name_address": merged.manufacturer_name_address or EXTRACTOR_UK,
            },
            drug_search_text,
            None,
        )
        name = ensured.get("suspect_drug_name", EXTRACTOR_UK)
        substance = ensured.get("suspect_drug_active_substance", EXTRACTOR_UK)
        if name and name != EXTRACTOR_UK and not _is_invalid_drug_name(name):
            updates["suspect_drug_name"] = name
        if substance and substance != EXTRACTOR_UK and not _is_invalid_drug_name(substance):
            updates["suspect_drug_active_substance"] = substance

    if str(data.patient_sex or "").strip():
        updates["patient_sex"] = sanitize_sex(str(data.patient_sex))
    if str(data.patient_age or "").strip() and data.patient_age != UK:
        updates["patient_age"] = sanitize_age(str(data.patient_age))
    if str(data.patient_weight_kg or "").strip() and data.patient_weight_kg != UK:
        updates["patient_weight_kg"] = sanitize_weight(str(data.patient_weight_kg))
    if str(data.reaction_outcome or "").strip() and data.reaction_outcome != UK:
        updates["reaction_outcome"] = sanitize_outcome(str(data.reaction_outcome))
    result = data.model_copy(update=updates) if updates else data
    return normalize_cioms_to_english(result)
