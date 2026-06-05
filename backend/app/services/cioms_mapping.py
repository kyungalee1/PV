"""Shared CIOMS field mapping for PDF and HTML generators."""

from __future__ import annotations


def txt(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip()


def infer_report_source(cioms: dict) -> str:
    src = txt(cioms.get("report_source_cioms")).upper()
    if src:
        return src
    rt = txt(cioms.get("report_type")).lower()
    if "study" in rt:
        return "STUDY"
    if "literature" in rt:
        return "LITERATURE"
    if "authority" in rt:
        return "AUTHORITY"
    if "professional" in rt or "spontaneous" in rt:
        return "HEALTH PROFESSIONAL"
    return "OTHER"


def reaction_onset_lines(cioms: dict) -> str:
    pt = txt(cioms.get("reaction_meddra_pt"))
    vb = txt(cioms.get("reaction_verbatim"))
    onset = txt(cioms.get("reaction_onset_date")) or "UK"
    lines = []
    if pt or vb:
        lines.append(f"{pt or vb} : {onset}")
    if pt and vb and pt.lower() != vb.lower():
        lines.append(f"{vb} : {onset}")
    return "\n".join(lines) if lines else ""


def narrative_text(cioms: dict) -> str:
    parts = []
    if txt(cioms.get("narrative")):
        parts.append(txt(cioms["narrative"]))
    if txt(cioms.get("suspect_drug_name")):
        parts.append(f"Suspected Drug Information: {txt(cioms.get('suspect_drug_name'))}")
    if txt(cioms.get("reaction_meddra_pt")):
        parts.append(f"Adverse Reaction: {txt(cioms.get('reaction_meddra_pt'))}")
    if txt(cioms.get("causality_assessment")):
        parts.append(f"Report and Overall Opinion: {txt(cioms.get('causality_assessment'))}")
    return "\n\n".join(parts) if parts else ""


def yn_checked(answer: str, option: str) -> bool:
    return txt(answer).upper() == option


def build_cioms_context(cioms: dict, case_id: int) -> dict[str, str]:
    age = txt(cioms.get("patient_age")) or "UK"
    sex = txt(cioms.get("patient_sex")) or "UK"
    drug = txt(cioms.get("suspect_drug_name")) or txt(cioms.get("suspect_drug_active_substance")) or "UK"
    substance = txt(cioms.get("suspect_drug_active_substance"))
    dose14 = txt(cioms.get("suspect_drug_dose"))
    if substance and substance.lower() not in drug.lower():
        drug = f"{drug} ({substance})"
    if dose14 and dose14 not in drug:
        drug = f"{drug} — {dose14}"
    therapy = ""
    if txt(cioms.get("suspect_drug_start_date")) or txt(cioms.get("suspect_drug_stop_date")):
        therapy = f"{txt(cioms.get('suspect_drug_start_date'))} / {txt(cioms.get('suspect_drug_stop_date'))}".strip(" /")

    reporter = "\n".join(
        x
        for x in [
            txt(cioms.get("reporter_name")),
            txt(cioms.get("reporter_organization")),
            txt(cioms.get("reporter_country")),
        ]
        if x
    )

    src = infer_report_source(cioms)
    rt = (txt(cioms.get("cioms_report_type")) or "INITIAL").upper()
    abate = txt(cioms.get("dechallenge_abate")) or "NA"
    reappear = txt(cioms.get("dechallenge_reappear")) or "NA"

    return {
        "patient_initials": txt(cioms.get("patient_initials")) or "UK",
        "country": txt(cioms.get("country_of_occurrence")) or "UK",
        "dob": txt(cioms.get("patient_date_of_birth")) or "UK",
        "age": age,
        "sex": sex,
        "reaction_onset": reaction_onset_lines(cioms) or "UK",
        "narrative": narrative_text(cioms) or "UK",
        "drug14": drug,
        "dose15": txt(cioms.get("suspect_drug_dose")) or "UK",
        "route16": txt(cioms.get("suspect_drug_route")) or "UK",
        "indication17": txt(cioms.get("suspect_drug_indication")) or "UK",
        "therapy18": therapy or "UK",
        "duration19": txt(cioms.get("therapy_duration")) or "UK",
        "concomitant22": txt(cioms.get("concomitant_medications")) or "UK",
        "history23": txt(cioms.get("medical_history")) or "UK",
        "mfr24a": txt(cioms.get("manufacturer_name_address")) or "UK",
        "mfr24b": txt(cioms.get("mfr_control_no")) or "UK",
        "recv24c": txt(cioms.get("date_received_manufacturer")) or "UK",
        "report_date": txt(cioms.get("date_of_report")) or "UK",
        "remarks26": txt(cioms.get("company_comment")) or "UK",
        "reporter25b": reporter or "UK",
        "cb_death": "☑" if cioms.get("seriousness_death") else "□",
        "cb_life": "☑" if cioms.get("seriousness_life_threatening") else "□",
        "cb_hosp": "☑" if cioms.get("seriousness_hospitalization") else "□",
        "cb_disability": "☑" if cioms.get("seriousness_disability") else "□",
        "cb_congenital": "☑" if cioms.get("seriousness_congenital_anomaly") else "□",
        "cb_other": "☑" if cioms.get("seriousness_other_medically_important") else "□",
        "abate_yes": "☑" if yn_checked(abate, "YES") else "□",
        "abate_no": "☑" if yn_checked(abate, "NO") else "□",
        "abate_na": "☑" if yn_checked(abate, "NA") else "□",
        "reappear_yes": "☑" if yn_checked(reappear, "YES") else "□",
        "reappear_no": "☑" if yn_checked(reappear, "NO") else "□",
        "reappear_na": "☑" if yn_checked(reappear, "NA") else "□",
        "src_study": "☑" if src == "STUDY" else "□",
        "src_literature": "☑" if src == "LITERATURE" else "□",
        "src_authority": "☑" if src == "AUTHORITY" else "□",
        "src_hp": "☑" if src == "HEALTH PROFESSIONAL" else "□",
        "src_other": "☑" if src == "OTHER" else "□",
        "type_initial": "☑" if rt == "INITIAL" else "□",
        "type_followup": "☑" if rt == "FOLLOWUP" else "□",
        "type_final": "☑" if rt == "FINAL" else "□",
        "case_id": str(case_id),
    }
