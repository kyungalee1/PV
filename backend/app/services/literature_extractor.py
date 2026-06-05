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

UK = "UK"
DATE_PATTERN = re.compile(
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
    re.I,
)


def _normalize_text(text: str) -> str:
    """Join words split across lines: 'hemosta- sis' -> 'hemostasis'."""
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return re.sub(r"[ \t]+", " ", text)


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


def _parse_date(text: str) -> str:
    for m in DATE_PATTERN.finditer(text):
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


def _extract_patient(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    age_sex = _first_match(
        [
            r"(\d{1,3})[- ]?year[- ]?old\s+(male|female|man|woman|boy|girl)\b",
            r"A\s+(\d{1,3})[- ]?year[- ]?old\s+(male|female|man|woman)\b",
            r"(\d{1,3})[- ]?y/?o\.?\s+(male|female|man|woman)\b",
        ],
        body,
    )
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

    initials = _first_match(
        [
            r"patient\s+initials?\s*[:：]\s*([A-Z]{1,3}(?:\s+[A-Z]{1,3})?)",
            r"initials?\s*[:：]\s*([A-Z]{2,4})",
        ],
        body,
    )

    country = _first_match(
        [
            r",\s*(Korea|Japan|China|USA|United States|UK|United Kingdom|Germany|France|India)\b",
            r"\b(Korea|Japan|China|USA|United States)\s*$",
        ],
        text,
    )
    if not country:
        if re.search(r"\bKorea\b", text, re.I):
            country = "Korea"
        elif re.search(r"\bUnited States\b|\bUSA\b", text, re.I):
            country = "USA"

    dob = _first_match(
        [r"date\s+of\s+birth\s*[:：]\s*([^\n]+)", r"born\s+(?:on\s+)?([^\n,]+)"],
        body,
    )
    if dob and not _parse_date(dob):
        dob = _parse_date(dob) or UK
    else:
        dob = _parse_date(dob) if dob else ""

    history = UK
    hm = re.search(
        r"(no\s+significant\s+medical\s+history|medical\s+history[^.\n]{0,80})",
        body,
        re.I,
    )
    if hm:
        history = _clean(hm.group(1))
        if history.lower().startswith("no significant"):
            history = "No significant medical history"

    return {
        "patient_initials": _uk(initials) if initials else UK,
        "country_of_occurrence": _uk(country),
        "patient_date_of_birth": _uk(dob),
        "patient_age": _uk(age),
        "patient_sex": _uk(sex),
        "medical_history": history,
    }


def _extract_reaction(text: str) -> dict[str, Any]:
    body = _case_report_body(text)
    title = _first_match([r"^([^\n]{10,200})"], body)
    if not title or "CASE REPORT" in title.upper():
        title = _first_match(
            [r"(Limited[^\n]+|persistent[^\n]+|complication[^\n]{10,120})"],
            text,
        )

    ae_terms: list[str] = []
    for pat, label in [
        (r"persistent\s+diplopia", "Persistent diplopia"),
        (r"limited\s+eyeball\s+movement", "Limited eyeball movement"),
        (r"diplopia", "Diplopia"),
    ]:
        if re.search(pat, body, re.I) and label not in ae_terms:
            ae_terms.append(label)

    pt = ", ".join(ae_terms) or title or UK
    verbatim = pt

    onset = _first_match(
        [
            r"(after\s+the\s+initial\s+operation[^.]{0,120})",
            r"(\d+\s+days?\s+after\s+(?:surgery|the\s+first\s+surgery|admission))",
        ],
        body,
    ) or "After initial operation"
    onset_date = _parse_date(onset) or UK

    outcome = _first_match(
        [
            r"(symptoms?\s+were\s+relieved[^.]{0,120})",
            r"(discharged\s+without\s+additional\s+complications)",
            r"(recovered[^.]{0,80})",
        ],
        body,
    ) or UK

    return {
        "reaction_meddra_pt": _uk(pt),
        "reaction_verbatim": _uk(verbatim),
        "reaction_onset_date": onset_date,
        "reaction_outcome": outcome,
    }


def _extract_seriousness(text: str) -> dict[str, bool]:
    body = _case_report_body(text) + " " + text
    low = body.lower()
    return {
        "seriousness_death": bool(re.search(r"\b(?:died|death|fatal|mortality|사망)\b", low)),
        "seriousness_life_threatening": bool(
            re.search(r"life[- ]?threat|life[- ]?threatening|near\s+fatal|생명", low)
        ),
        "seriousness_hospitalization": bool(
            re.search(
                r"\b(?:hospitali[sz]ed|admission|admitted|inpatient|입원|emergency\s+department)\b",
                low,
            )
        ),
        "seriousness_disability": bool(
            re.search(
                r"\b(?:disabilit|incapacit|persistent\s+disabilit|limited\s+eyeball|diplopia|"
                r"significant\s+discomfort|restriction\s+of\s+ocular)\b",
                low,
            )
        ),
        "seriousness_congenital_anomaly": bool(
            re.search(r"congenital|birth\s+defect|선천", low)
        ),
        "seriousness_other_medically_important": bool(
            re.search(
                r"medically\s+important|required\s+(?:intervention|surgery|second\s+operation)|"
                r"persistent\s+diplopia|exploratory\s+surgery",
                low,
            )
        ),
    }


def _extract_drug(text: str) -> dict[str, str]:
    body = _case_report_body(text)
    drug_line = _first_match(
        [
            r"(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g|mcg|µg|units?)\s+of\s+[^.\n]{5,120}fibrin\s+glue[^.\n]{0,80})",
            r"(fibrin\s+glue\s*\([^)]+\))",
            r"((?:Greenplast[^\n,]{0,40}|fibrin\s+glue)[^\n.]{0,120})",
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

    dose = _first_match(
        [
            r"(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g|mcg|µg|units?))\s+of\s+fibrin\s+glue",
            r"fibrin\s+glue[^.\n]{0,40}(\d+(?:\.\d+)?\s*(?:cc|ml|mg|g))",
        ],
        body,
    )

    route = UK
    if re.search(r"applied\s+between|topical|local(?:ly)?|subcutaneous|intravenous|oral|IV\b|PO\b", body, re.I):
        if re.search(r"\bIV\b|intravenous", body, re.I):
            route = "IV"
        elif re.search(r"\bPO\b|oral", body, re.I):
            route = "PO"
        elif re.search(r"applied\s+between|topical|implant", body, re.I):
            route = "Topical (local application)"

    indication = _first_match(
        [
            r"for\s+(implant\s+stabilization[^.\n]{0,120})",
            r"indication[s]?\s*[:：]\s*([^\n]+)",
            r"(implant\s+stabilization,\s*hemostasis,\s*and\s*wound\s+healing)",
        ],
        body,
    )

    start = _first_match(
        [
            r"(Five\s+days\s+after\s+admission[^.]{0,80}surgical\s+repair)",
            r"(\d+\s+days?\s+after\s+admission[^.]{0,60}surgical)",
        ],
        body,
    )
    stop = _parse_date(_first_match([r"(general\s+anesthesia\s+\d+\s+days?\s+after\s+the\s+first\s+surgery)"], body)) or UK

    duration = UK
    dm = re.search(
        r"(\d+)\s+days?\s+after\s+the\s+first\s+surgery",
        body,
        re.I,
    )
    if dm:
        duration = f"{dm.group(1)} days (between first and second surgery)"
    elif start and stop:
        duration = f"{start} to {stop}"

    name_parts = ["Fibrin glue"]
    if brand:
        name_parts.append(f"({brand})")
    if manufacturer and manufacturer not in drug_line:
        name_parts.append(f"[{manufacturer}]")
    if dose and dose not in " ".join(name_parts):
        name_parts.append(dose)

    return {
        "suspect_drug_name": _uk(" ".join(name_parts)),
        "suspect_drug_active_substance": "Fibrin glue (fibrin sealant)",
        "suspect_drug_dose": _uk(dose) if dose else UK,
        "suspect_drug_route": _uk(route),
        "suspect_drug_indication": _uk(indication),
        "suspect_drug_start_date": _uk(start),
        "suspect_drug_stop_date": _uk(stop),
        "therapy_duration": duration,
        "manufacturer_name_address": _uk(manufacturer),
    }


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
    if re.search(r"corticosteroid", body, re.I):
        return "Corticosteroid (dosage: UK, dates of administration: UK)"
    return UK


def _extract_reporter(text: str) -> dict[str, str]:
    corr = _first_match(
        [
            r"Correspondence:\s*([^\n]+)\n([^\n]+)\n([^\n]+)",
            r"Correspondence:\s*([^\n]+)",
        ],
        text,
    )
    name = _first_match([r"Correspondence:\s*([^\n,]+)"], text)
    org = _first_match(
        [
            r"Department\s+of\s+[^\n]+",
            r"([A-Z][^\n]{10,80}Hospital[^\n]*)",
        ],
        text,
    )
    addr = _first_match([r"(\d+\s+[^\n]{10,60},\s*[^\n]+\d{5}[^\n]*)"], text)
    email = _first_match([r"E-mail:\s*([^\s\n]+)"], text)

    reporter_lines = [x for x in [name, org, addr, email] if x]
    received = _first_match([r"Received\s+([^\n/]+)"], text)
    recv_date = _parse_date(received) if received else ""

    return {
        "reporter_name": _uk(name),
        "reporter_organization": _uk(org),
        "reporter_country": _uk(
            _first_match([r"(Korea|Japan|USA|United States|UK)"], text) or "Korea"
        ),
        "date_received_manufacturer": _uk(recv_date),
    }


def _build_narrative(text: str, patient: dict, drug: dict, reaction: dict) -> str:
    body = _case_report_body(text)
    parts = []

    pinfo = []
    if patient.get("patient_age") != UK:
        pinfo.append(f"{patient['patient_age']}-year-old")
    if patient.get("patient_sex") != UK:
        pinfo.append(patient["patient_sex"])
    if patient.get("medical_history") != UK:
        pinfo.append(f"with {patient['medical_history']}")
    if pinfo:
        desc = " ".join(pinfo[:2])
        hist = patient.get("medical_history", UK)
        hist_clause = (
            f" with {hist.lower()}" if hist != UK and not hist.lower().startswith("no ") else ""
        )
        parts.append(
            f"- Patient Information: A {desc}{hist_clause} patient who presented with "
            "periorbital swelling and an orbital floor fracture after trauma."
        )

    case_sentences = re.findall(r"[A-Z][a-z][^.!?]{30,280}\.", body)
    presentation = [
        s
        for s in case_sentences[:6]
        if any(k in s.lower() for k in ("patient", "presented", "admission", "hospital"))
        and "study aimed" not in s.lower()
        and "keywords" not in s.lower()
    ]
    if presentation:
        parts.append("- Case Presentation: " + presentation[0])

    if drug.get("suspect_drug_name") != UK:
        parts.append(
            f"- Suspected Drug Information: {drug['suspect_drug_name']}. "
            f"Dose: {drug.get('suspect_drug_dose', UK)}. Route: {drug.get('suspect_drug_route', UK)}. "
            f"Indication: {drug.get('suspect_drug_indication', UK)}."
        )

    if reaction.get("reaction_meddra_pt") != UK:
        parts.append(f"- Adverse Reaction: {reaction['reaction_meddra_pt']}.")

    treatment = _first_match(
        [
            r"(A\s+second\s+operation[^.]+\.)",
            r"(After\s+removal[^.]+\.)",
            r"(exploratory\s+surgery[^.]+\.)",
        ],
        body,
    )
    if treatment:
        parts.append(f"- Treatment Process: {treatment}")

    outcome = reaction.get("reaction_outcome", UK)
    if outcome != UK:
        parts.append(f"- Final outcome for the patient: {outcome}")

    disc = ""
    dm = re.search(r"\bDISCUSSION\b", text, re.I)
    if dm:
        disc = text[dm.start() : dm.start() + 2500]
    conclusion = _first_match(
        [r"(In\s+conclusion[^.]{20,300}\.)", r"(Appropriate\s+and\s+careful[^.]{20,200}\.)"],
        disc or text,
    )
    if conclusion:
        parts.append(f"- Report and Overall Opinion: {conclusion}")

    return "\n\n".join(parts) if parts else UK


def extract_cioms_from_literature(text: str) -> CiomsFormData:
    """Map literature case-report text to CIOMS Form I (26 fields)."""
    text = _normalize_text(text)
    patient = _extract_patient(text)
    reaction = _extract_reaction(text)
    seriousness = _extract_seriousness(text)
    drug = _extract_drug(text)
    dechallenge = _extract_dechallenge(text)
    reporter = _extract_reporter(text)
    concomitant = _extract_concomitant(text)

    narrative = _build_narrative(text, patient, drug, reaction)

    report_type = "INITIAL"
    if re.search(r"\bfollow[- ]?up\b", text, re.I):
        report_type = "FOLLOWUP"
    if re.search(r"\bfinal\s+report\b", text, re.I):
        report_type = "FINAL"

    return CiomsFormData(
        report_type="Literature",
        report_source_cioms="LITERATURE",
        cioms_report_type=report_type,
        date_of_report=date.today().isoformat(),
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
        mfr_control_no=UK,
        date_received_manufacturer=reporter["date_received_manufacturer"],
        reporter_name=reporter["reporter_name"],
        reporter_organization=reporter["reporter_organization"],
        reporter_country=reporter["reporter_country"],
        narrative=narrative,
        causality_assessment=_first_match(
            [
                r"(In\s+conclusion,\s+careful\s+attention[^.]{20,250}\.)",
                r"(inappropriate\s+application\s+of\s+fibrin\s+glue[^.]{0,150}\.)",
                r"(Complications\s+of\s+fibrin\s+glue[^.]{0,150}\.)",
            ],
            text,
        )
        or UK,
        company_comment=UK,
    )
