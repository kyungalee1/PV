"""Lightweight MedDRA PT lookup for common adverse event terms.

Full MedDRA requires a licensed MSSO subscription. This module maps frequent
verbatim / PT strings to MedDRA PT names and codes for CIOMS narrative use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MeddraCoding:
    pt: str
    code: str
    soc: str = ""
    match_type: str = "lookup"  # lookup | source | exact


# Common PTs (MedDRA 26.x representative codes)
_MEDDRA_TABLE: dict[str, MeddraCoding] = {
    "diplopia": MeddraCoding("Diplopia", "10013036", "Eye disorders"),
    "persistent diplopia": MeddraCoding("Diplopia", "10013036", "Eye disorders"),
    "limited eyeball movement": MeddraCoding("Ocular motility disorder", "10029934", "Eye disorders"),
    "hepatotoxicity": MeddraCoding("Hepatotoxicity", "10019832", "Hepatobiliary disorders"),
    "drug-induced liver injury": MeddraCoding("Drug-induced liver injury", "10072371", "Hepatobiliary disorders"),
    "hepatic function abnormal": MeddraCoding("Hepatic function abnormal", "10019676", "Investigations"),
    "nausea": MeddraCoding("Nausea", "10028813", "Gastrointestinal disorders"),
    "vomiting": MeddraCoding("Vomiting", "10047700", "Gastrointestinal disorders"),
    "anaphylaxis": MeddraCoding("Anaphylactic reaction", "10002198", "Immune system disorders"),
    "anaphylactic reaction": MeddraCoding("Anaphylactic reaction", "10002198", "Immune system disorders"),
    "hypotension": MeddraCoding("Hypotension", "10021097", "Vascular disorders"),
    "rash": MeddraCoding("Rash", "10037844", "Skin and subcutaneous tissue disorders"),
    "urticaria": MeddraCoding("Urticaria", "10046735", "Skin and subcutaneous tissue disorders"),
    "pruritus": MeddraCoding("Pruritus", "10037087", "Skin and subcutaneous tissue disorders"),
    "headache": MeddraCoding("Headache", "10019211", "Nervous system disorders"),
    "pyrexia": MeddraCoding("Pyrexia", "10037660", "General disorders and administration site conditions"),
    "fever": MeddraCoding("Pyrexia", "10037660", "General disorders and administration site conditions"),
    "ischemic stroke": MeddraCoding("Ischaemic stroke", "10061256", "Nervous system disorders"),
    "ischaemic stroke": MeddraCoding("Ischaemic stroke", "10061256", "Nervous system disorders"),
    "stroke": MeddraCoding("Cerebrovascular accident", "10008190", "Nervous system disorders"),
    "pulmonary embolism": MeddraCoding("Pulmonary embolism", "10037377", "Respiratory, thoracic and mediastinal disorders"),
    "transient enhancing lesion": MeddraCoding("Lesion", "10024293", "General disorders and administration site conditions"),
    "myocardial infarction": MeddraCoding("Myocardial infarction", "10028596", "Cardiac disorders"),
    "angioedema": MeddraCoding("Angioedema", "10002424", "Skin and subcutaneous tissue disorders"),
    "thrombocytopenia": MeddraCoding("Thrombocytopenia", "10043554", "Blood and lymphatic system disorders"),
    "neutropenia": MeddraCoding("Neutropenia", "10029354", "Blood and lymphatic system disorders"),
    "renal failure": MeddraCoding("Renal failure", "10038435", "Renal and urinary disorders"),
    "acute kidney injury": MeddraCoding("Acute kidney injury", "10069339", "Renal and urinary disorders"),
    "pneumonia": MeddraCoding("Pneumonia", "10035664", "Infections and infestations"),
    "sepsis": MeddraCoding("Sepsis", "10040047", "Infections and infestations"),
    "dyspnoea": MeddraCoding("Dyspnoea", "10013968", "Respiratory, thoracic and mediastinal disorders"),
    "dyspnea": MeddraCoding("Dyspnoea", "10013968", "Respiratory, thoracic and mediastinal disorders"),
    "chest pain": MeddraCoding("Chest pain", "10008479", "General disorders and administration site conditions"),
    "death": MeddraCoding("Death", "10011906", "General disorders and administration site conditions"),
    "hospitalisation": MeddraCoding("Hospitalisation", "10020002", "Surgical and medical procedures"),
    "hospitalization": MeddraCoding("Hospitalisation", "10020002", "Surgical and medical procedures"),
    # Korean common terms -> PT
    "구역": MeddraCoding("Nausea", "10028813", "Gastrointestinal disorders"),
    "오심": MeddraCoding("Nausea", "10028813", "Gastrointestinal disorders"),
    "발진": MeddraCoding("Rash", "10037844", "Skin and subcutaneous tissue disorders"),
    "두통": MeddraCoding("Headache", "10019211", "Nervous system disorders"),
    "발열": MeddraCoding("Pyrexia", "10037660", "General disorders and administration site conditions"),
    "저혈압": MeddraCoding("Hypotension", "10021097", "Vascular disorders"),
    "심근경색": MeddraCoding("Myocardial infarction", "10028596", "Cardiac disorders"),
    "간독성": MeddraCoding("Hepatotoxicity", "10019832", "Hepatobiliary disorders"),
    "아나필락시스": MeddraCoding("Anaphylactic reaction", "10002198", "Immune system disorders"),
}


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_meddra_from_text(text: str) -> MeddraCoding | None:
    """Parse MedDRA PT/code already present in source (e.g. PT: Diplopia, 10013036)."""
    m = re.search(
        r"(?:MedDRA\s*)?PT\s*[:：]\s*([^,\n;]{2,120})\s*[,;/]\s*(?:MedDRA\s*)?(?:code\s*)?[:：]?\s*(100\d{5})",
        text,
        re.I,
    )
    if m:
        return MeddraCoding(_clean_pt(m.group(1)), m.group(2), match_type="source")

    m = re.search(r"([A-Za-z][A-Za-z0-9 /\-]{2,80})\s*[\(（]\s*(100\d{5})\s*[\)）]", text)
    if m:
        return MeddraCoding(_clean_pt(m.group(1)), m.group(2), match_type="source")

    m = re.search(r"\b(100\d{5})\b", text)
    if m:
        code = m.group(1)
        for entry in _MEDDRA_TABLE.values():
            if entry.code == code:
                return MeddraCoding(entry.pt, code, entry.soc, match_type="source")
    return None


def _clean_pt(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def code_adverse_event(verbatim: str) -> MeddraCoding | None:
    """Map verbatim AE/SAE term to MedDRA PT (best effort)."""
    if not verbatim or verbatim.strip().upper() in ("UK", "NA", "N/A", "UNKNOWN"):
        return None

    src = extract_meddra_from_text(verbatim)
    if src:
        return src

    key = _normalize_key(verbatim)
    if key in _MEDDRA_TABLE:
        return _MEDDRA_TABLE[key]

    # Substring match (longest key first)
    for k, coding in sorted(_MEDDRA_TABLE.items(), key=lambda x: len(x[0]), reverse=True):
        if k in key or key in k:
            return MeddraCoding(coding.pt, coding.code, coding.soc, match_type="lookup")

    # Token overlap
    tokens = set(re.findall(r"[a-z가-힣]{3,}", key))
    best: MeddraCoding | None = None
    best_score = 0
    for k, coding in _MEDDRA_TABLE.items():
        kt = set(re.findall(r"[a-z가-힣]{3,}", k))
        score = len(tokens & kt)
        if score > best_score:
            best_score = score
            best = coding
    if best_score >= 1 and best:
        return MeddraCoding(best.pt, best.code, best.soc, match_type="lookup")
    return None


def format_meddra(coding: MeddraCoding | None, verbatim: str = "") -> str:
    if not coding:
        return verbatim
    if verbatim and _normalize_key(verbatim) != _normalize_key(coding.pt):
        return f"{verbatim} (MedDRA PT: {coding.pt}, {coding.code})"
    return f"{coding.pt} (MedDRA {coding.code})"
