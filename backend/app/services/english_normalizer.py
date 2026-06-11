"""Normalize CIOMS field values to English (translate Korean, keep English as base)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.schemas import CiomsFormData

logger = logging.getLogger(__name__)

UK = "UK"
_HAS_HANGUL = re.compile(r"[가-힣]")
_PRESERVE_VALUES = frozenset(
    {
        UK,
        "NA",
        "N/A",
        "YES",
        "NO",
        "INITIAL",
        "FOLLOWUP",
        "FINAL",
        "STUDY",
        "LITERATURE",
        "AUTHORITY",
        "HEALTH PROFESSIONAL",
        "OTHER",
    }
)

# Longest Korean phrases first when applying glossary replacements.
_KO_EN_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("중대한 이상사례", "serious adverse event"),
    ("중대 이상사례", "serious adverse event"),
    ("중대이상사례", "serious adverse event"),
    ("약물이상반응", "adverse drug reaction"),
    ("이상반응 발생일", "adverse reaction onset date"),
    ("이상 사례 정보", "adverse case information"),
    ("이상사례정보", "adverse case information"),
    ("이상 사례", "adverse case"),
    ("이상사례", "adverse case"),
    ("이상반응", "adverse reaction"),
    ("부작용", "adverse reaction"),
    ("원인 의약품", "suspect drug"),
    ("원인의약품", "suspect drug"),
    ("의심의약품", "suspect drug"),
    ("병용 약물", "concomitant medication"),
    ("병용약", "concomitant medication"),
    ("투여 시작일", "therapy start date"),
    ("투여 종료일", "therapy stop date"),
    ("투여경로", "route of administration"),
    ("환자 이니셜", "patient initials"),
    ("생년월일", "date of birth"),
    ("발생국", "country of occurrence"),
    ("제조사 번호", "manufacturer control number"),
    ("보고일", "date of report"),
    ("발현일", "onset date"),
    ("발생일", "onset date"),
    ("유효성분", "active substance"),
    ("일반명", "generic name"),
    ("제품명", "product name"),
    ("의약품", "medicinal product"),
    ("적응증", "indication"),
    ("제조사", "manufacturer"),
    ("보고자", "reporter"),
    ("인과관계", "causality"),
    ("성별", "sex"),
    ("나이", "age"),
    ("체중", "weight"),
    ("용량", "dose"),
    ("국가", "country"),
    ("입원", "hospitalization"),
    ("사망", "death"),
    ("발열", "pyrexia"),
    ("오심", "nausea"),
    ("구역", "nausea"),
    ("발진", "rash"),
    ("두통", "headache"),
    ("저혈압", "hypotension"),
    ("심근경색", "myocardial infarction"),
    ("간독성", "hepatotoxicity"),
    ("아나필락시스", "anaphylaxis"),
    ("남성", "male"),
    ("여성", "female"),
    ("남", "male"),
    ("여", "female"),
    ("예", "yes"),
    ("아니오", "no"),
    ("없음", "none"),
    ("미상", "unknown"),
    ("회복", "recovered"),
    ("호전", "recovering"),
    ("완전회복", "fully recovered"),
    ("경구", "oral"),
    ("정맥", "intravenous"),
    ("근육", "intramuscular"),
    ("피하", "subcutaneous"),
    ("경피", "transdermal"),
    ("흡입", "inhalation"),
    ("점적", "infusion"),
    ("한국", "Korea"),
    ("대한민국", "Republic of Korea"),
    ("고혈압", "hypertension"),
    ("병력", "medical history"),
    ("투여", "administration"),
    ("및", "and"),
    ("있음", "present"),
    ("무", "none"),
    ("관련", "related"),
    ("의심", "suspected"),
    ("환자", "patient"),
    ("치료", "treatment"),
    ("경과", "course"),
    ("결과", "outcome"),
)

_CIOMS_TEXT_FIELDS = (
    "report_type",
    "country_of_occurrence",
    "reporter_type",
    "reporter_name",
    "reporter_organization",
    "reporter_country",
    "reporter_qualification",
    "patient_initials",
    "patient_date_of_birth",
    "patient_age",
    "patient_sex",
    "patient_weight_kg",
    "patient_height_cm",
    "medical_history",
    "concomitant_medications",
    "suspect_drug_name",
    "suspect_drug_active_substance",
    "suspect_drug_dose",
    "suspect_drug_route",
    "suspect_drug_indication",
    "suspect_drug_start_date",
    "suspect_drug_stop_date",
    "suspect_drug_batch_lot",
    "therapy_duration",
    "reaction_meddra_pt",
    "reaction_verbatim",
    "reaction_onset_date",
    "reaction_onset_display",
    "reaction_end_date",
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


def contains_korean(text: str) -> bool:
    return bool(text and _HAS_HANGUL.search(text))


def apply_korean_glossary(text: str) -> str:
    if not text:
        return text
    out = text
    for ko, en in _KO_EN_GLOSSARY:
        out = out.replace(ko, en)
    return re.sub(r"\s+", " ", out).strip()


def _machine_translate(text: str) -> str:
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        logger.warning("deep-translator not installed; glossary-only Korean normalization")
        return text

    try:
        translator = GoogleTranslator(source="auto", target="en")
        chunk_size = 4500
        if len(text) <= chunk_size:
            return translator.translate(text)
        parts: list[str] = []
        for i in range(0, len(text), chunk_size):
            parts.append(translator.translate(text[i : i + chunk_size]))
        return " ".join(parts)
    except Exception:
        logger.exception("Korean translation failed; returning glossary-normalized text")
        return text


def normalize_to_english(text: str) -> str:
    """Translate Korean fragments to English; leave pure English text unchanged."""
    if not text:
        return text
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned or cleaned.upper() in _PRESERVE_VALUES:
        return cleaned
    if not contains_korean(cleaned):
        return cleaned

    glossed = apply_korean_glossary(cleaned)
    if not contains_korean(glossed):
        return glossed
    return _machine_translate(glossed)


def normalize_cioms_dict(cioms: dict[str, Any]) -> dict[str, Any]:
    out = dict(cioms)
    for field in _CIOMS_TEXT_FIELDS:
        val = out.get(field)
        if isinstance(val, str) and val.strip():
            out[field] = normalize_to_english(val)
    return out


def normalize_cioms_to_english(data: CiomsFormData) -> CiomsFormData:
    updates = {}
    for field in _CIOMS_TEXT_FIELDS:
        val = getattr(data, field, "")
        if isinstance(val, str) and val.strip() and val.strip().upper() not in _PRESERVE_VALUES:
            normalized = normalize_to_english(val)
            if normalized != val:
                updates[field] = normalized
    return data.model_copy(update=updates) if updates else data
