"""Convert tables, symbols, and figure captions into CIOMS 7+13 narrative prose."""

from __future__ import annotations

import re
from typing import Any

from app.services.meddra_coder import code_adverse_event, format_meddra
from app.services.pdf_text_utils import repair_pdf_text
from app.services.table_field_extractor import is_citation_or_header_noise, is_table_dump

_SYMBOL_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[□☐▢]"), "not checked"),
    (re.compile(r"[☑✓✔]"), "yes"),
    (re.compile(r"[☒✗✘]"), "no"),
    (re.compile(r"\(\+\)"), "positive"),
    (re.compile(r"\(-\)"), "negative"),
    (re.compile(r"(?<![\d\-])[+](?=\s|$)"), "positive"),
    (re.compile(r"±"), "plus or minus"),
    (re.compile(r"→"), "leading to"),
    (re.compile(r"≤"), "less than or equal to"),
    (re.compile(r"≥"), "greater than or equal to"),
    (re.compile(r"≈"), "approximately"),
    (re.compile(r"×"), " by "),
]

_FIGURE_CAPTION = re.compile(
    r"Fig(?:ure)?\.?\s*\d+[A-Za-z]?\.?\s*([^.\n]{20,400}\.)",
    re.I,
)

_PATIENT_ROW = re.compile(
    r"([FM])/(\d{1,3})\s+"
    r"([A-Za-z/]+?)\s+"
    r"(Ischemic\s*stroke|Ischaemic\s*stroke|Pulmonary\s*thromboembolism|"
    r"Transient\s*enhancing\s*lesion|TEC|Cardiac\s*arrest|Diplopia|"
    r"Hepatotoxicity|Anaphylaxis|Hypotension)"
    r"\s+(.{8,180}?)"
    r"(?=(?:[FM]/\d{1,3}\s)|Abbreviations:|Fig\.|$)",
    re.I | re.S,
)

_TABLE_BLOCK = re.compile(
    r"Table\s*(\d+)\b(.{20,1200}?)(?=Table\s*\d+|Fig\.|Abbreviations:|\n\d+\.\d+\.|DISCUSSION|$)",
    re.I | re.S,
)

_CASE_SECTION = re.compile(
    r"(?:^|\n)\s*(?:3\.1\.?\s*)?Patient\s*1\b(.{200,6000}?)"
    r"(?=(?:3\.2\.?\s*)?Patient\s*2\b|Table\s*2\b|DISCUSSION\b|$)",
    re.I | re.S,
)


def _clean(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def normalize_narrative_symbols(text: str) -> str:
    """Replace checkbox/special symbols with readable words."""
    out = text
    for pattern, replacement in _SYMBOL_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    out = re.sub(r"\[(?:\d+\s*,\s*)*\d+\]", "", out)
    return _clean(out)


def _is_narrative_noise(sentence: str) -> bool:
    s = _clean(sentence)
    if not s or len(s) < 20:
        return True
    if is_citation_or_header_noise(s):
        return True
    if re.match(r"^A \d{1,3}-year-old (?:female|male)\b", s, re.I):
        return False
    if is_table_dump(s):
        return True
    if re.search(r"^(?:Table\s*\d+|Abbreviations?:|References\b)", s, re.I):
        return True
    if len(s) > 80 and s.count(" ") < len(s) / 18:
        return True
    if re.search(r"doi\.org|https?://|www\.", s, re.I):
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    repaired = normalize_narrative_symbols(repair_pdf_text(text))
    parts = re.split(r"(?<=[.!?])\s+", repaired)
    return [_clean(p) for p in parts if p and not _is_narrative_noise(p)]


def figure_captions_to_narrative(text: str) -> list[str]:
    """Turn figure captions into descriptive narrative sentences."""
    lines: list[str] = []
    seen: set[str] = set()
    for m in _FIGURE_CAPTION.finditer(text):
        caption = normalize_narrative_symbols(_clean(m.group(0)))
        if _is_narrative_noise(caption):
            continue
        fig_num = re.search(r"Fig(?:ure)?\.?\s*(\d+[A-Za-z]?)", caption, re.I)
        label = f"Figure {fig_num.group(1)}" if fig_num else "Imaging"
        body = re.sub(r"^Fig(?:ure)?\.?\s*\d+[A-Za-z]?\.?\s*", "", caption, flags=re.I)
        sentence = f"{label}: {_clean(body)}"
        key = sentence.lower()[:80]
        if key not in seen:
            seen.add(key)
            lines.append(sentence)
    return lines


def _format_onset_phrase(onset: str) -> str:
    o = repair_pdf_text(onset)
    o = re.sub(
        r"After\s*IVIg\s*infusion\s*\(\s*day\s*(\d+)\s*\)",
        r"after IVIg infusion on day \1",
        o,
        flags=re.I,
    )
    o = re.sub(
        r"(\d+)\s*days?\s*after\s*IVIg\s*completion",
        r"\1 days after IVIg completion",
        o,
        flags=re.I,
    )
    return _clean(o)


def _format_lab_phrase(lab: str) -> str:
    l = normalize_narrative_symbols(repair_pdf_text(lab))
    l = re.sub(r"Anti-microsomal\s*antibody\s*positive", "anti-microsomal antibody positive", l, flags=re.I)
    l = re.sub(r"D-dimer\s*([\d.]+)\s*ug/m\s*L", r"D-dimer \1 ug/mL", l, flags=re.I)
    l = re.sub(r"No\s*significant\s*findings?", "no significant laboratory findings", l, flags=re.I)
    return _clean(l)


def _patient_row_to_sentence(sex: str, age: str, diagnosis: str, event: str, rest: str) -> str:
    sex_word = "female" if sex.upper() == "F" else "male"
    diag = repair_pdf_text(diagnosis).replace("/", " ")
    evt = repair_pdf_text(event)
    evt = re.sub(
        r"(Ischemic|Ischaemic|Pulmonary|Transient)([A-Z])",
        r"\1 \2",
        evt,
    )
    evt = re.sub(r"([a-z])(stroke|embolism|lesion)", r"\1 \2", evt, flags=re.I)
    remainder = repair_pdf_text(rest)

    onset = ""
    comorbidities = ""
    labs = ""

    m_onset = re.search(
        r"(after\s*IVIg\s*infusion\s*\(\s*day\s*\d+\s*\)|"
        r"after\s*IVIg\s*infusion[^,;]*|"
        r"\d+\s*days?\s*after\s*IVIg\s*completion[^,;]*)",
        remainder,
        re.I,
    )
    if m_onset:
        onset = _format_onset_phrase(m_onset.group(1))
        tail = remainder[m_onset.end() :].strip(" ,;")
    else:
        tail = remainder

    lab_match = re.search(
        r"(Anti[-\w]+\s*antibody\s*\(\+\)|D-dimer\s*[\d.]+\s*ug/m\s*L|No\s*significant\s*findings?)",
        tail,
        re.I,
    )
    if lab_match:
        labs = _format_lab_phrase(lab_match.group(1))
        comorbidities = tail[: lab_match.start()].strip(" ,;")
    else:
        comorbidities = tail.strip(" ,;")
        labs = ""

    if comorbidities:
        comorbidities = _clean(re.sub(r"\bHTN\b", "hypertension", comorbidities, flags=re.I))
        comorbidities = re.sub(r"\bDM\b", "diabetes mellitus", comorbidities, flags=re.I)
        comorbidities = re.sub(r"\bA-fib\b", "atrial fibrillation", comorbidities, flags=re.I)
        comorbidities = re.sub(r"\bischemic\s*stroke\b", "", comorbidities, flags=re.I)
        comorbidities = _clean(comorbidities.strip(" ,"))

    parts = [f"A {age}-year-old {sex_word} with {diag} developed {evt.lower()}"]
    if onset:
        parts.append(onset)
    sentence = " ".join(parts) + "."
    if comorbidities:
        sentence += f" Comorbidities included {comorbidities}."
    if labs and labs.lower() not in comorbidities.lower():
        sentence += f" Laboratory findings: {labs}."
    return sentence


def inline_tables_to_narrative(text: str) -> list[str]:
    """Convert embedded PDF table blocks (Table 1, Table 2, …) to prose."""
    lines: list[str] = []
    seen: set[str] = set()
    repaired = repair_pdf_text(text)

    for block in _TABLE_BLOCK.finditer(repaired):
        table_num = block.group(1)
        body = block.group(2)
        rows = list(_PATIENT_ROW.finditer(body))
        if rows:
            intro = f"Table {table_num} summary:"
            if intro not in seen:
                seen.add(intro)
                lines.append(intro)
            for row in rows:
                sentence = _patient_row_to_sentence(
                    row.group(1),
                    row.group(2),
                    row.group(3),
                    row.group(4),
                    row.group(5),
                )
                key = sentence.lower()[:100]
                if key not in seen:
                    seen.add(key)
                    lines.append(sentence)
            continue

        pairs = re.findall(
            r"([A-Za-z][A-Za-z /-]{2,40})\s+([^\n|]{3,120})",
            repair_pdf_text(body),
        )
        if len(pairs) >= 2 and not re.search(r"[FM]/\d", body):
            joined = "; ".join(f"{k}: {v}" for k, v in pairs[:6])
            if not _is_narrative_noise(joined):
                lines.append(f"Table {table_num} describes: {joined}")

    if not lines:
        for row in _PATIENT_ROW.finditer(repaired):
            sentence = _patient_row_to_sentence(
                row.group(1), row.group(2), row.group(3), row.group(4), row.group(5)
            )
            key = sentence.lower()[:100]
            if key not in seen:
                seen.add(key)
                lines.append(sentence)

    return lines


def _is_form_table_content(text: str) -> bool:
    from app.services.field_sanitizer import contains_form_dump

    return contains_form_dump(text)


def structured_tables_to_narrative(tables: list[dict[str, Any]]) -> list[str]:
    """Convert pdfplumber table rows into labeled narrative sentences."""
    lines: list[str] = []
    for tbl in tables:
        headers: list[str] = []
        raw = tbl.get("raw") or []
        if raw:
            first = [_clean(c) for c in raw[0] if _clean(c)]
            if len(first) >= 2:
                headers = first

        for row in raw[1:] if raw else []:
            cells = [_clean(c) for c in row if _clean(c)]
            if len(cells) < 2:
                continue
            if headers and len(headers) == len(cells):
                pairs = [
                    f"{h}: {normalize_narrative_symbols(v)}"
                    for h, v in zip(headers, cells)
                    if v and not is_table_dump(v)
                ]
                if pairs:
                    joined = "Table data — " + "; ".join(pairs) + "."
                    if not _is_form_table_content(joined):
                        lines.append(joined)
            elif len(cells) == 2:
                label, val = cells[0], normalize_narrative_symbols(cells[1])
                if val and not is_table_dump(val):
                    line = f"{label}: {val}."
                    if not _is_form_table_content(line):
                        lines.append(line)
            else:
                joined = "; ".join(normalize_narrative_symbols(c) for c in cells if c)
                if joined and not is_table_dump(joined) and not _is_form_table_content(joined):
                    lines.append(f"Table row: {joined}.")

        for row in tbl.get("rows", []):
            if not isinstance(row, dict):
                continue
            pairs = [
                f"{k}: {normalize_narrative_symbols(v)}"
                for k, v in row.items()
                if _clean(v) and not is_table_dump(str(v))
            ]
            if pairs:
                joined = "Table row — " + "; ".join(pairs) + "."
                if not _is_form_table_content(joined):
                    lines.append(joined)
    return lines


def _section_quality_ok(section: str) -> bool:
    flat = repair_pdf_text(section)
    if len(flat) < 120:
        return False
    glued_runs = len(re.findall(r"[a-z]{18,}", flat, re.I))
    space_ratio = flat.count(" ") / max(len(flat), 1)
    return glued_runs <= 3 and space_ratio >= 0.12


def _find_first_patient_section(text: str) -> str:
    """Locate patient-1 case block even when PDF glues section numbers."""
    repaired = repair_pdf_text(text)
    start = re.search(
        r"\d{1,3}-year-old\s+(?:wo\s*)?man\s+with\s+generalized\s+MG\b",
        repaired,
        re.I,
    )
    if not start:
        start = re.search(
            r"\d{1,3}-year-old\s+(?:wo\s*)?man\s+with\s+[^.]{5,40}\b",
            repaired,
            re.I,
        )
    if not start:
        return ""
    end = re.search(r"3\.2\.?\s*Patient\s*2\b", repaired[start.start() :], re.I)
    section = repaired[start.start() : start.start() + end.start()] if end else repaired[start.start() : start.start() + 3500]
    return section if _section_quality_ok(section) else ""


def extract_case_section_narrative(text: str) -> list[str]:
    """Extract first patient case section and return categorized narrative bullets."""
    section = _find_first_patient_section(text)
    if not section:
        return []

    section = normalize_narrative_symbols(repair_pdf_text(section))
    bullets: list[str] = []
    patient_bits: list[str] = []
    drug_bits: list[str] = []
    ae_bits: list[str] = []
    treatment_bits: list[str] = []
    outcome_bits: list[str] = []

    for sent in _split_sentences(section):
        low = sent.lower()
        if re.search(r"\b(?:weakness|lesion|infarction|stroke|embol|diplopia|tec\b|symptom)", low):
            ae_bits.append(sent)
        elif re.search(r"\b(?:ivig|immunoglobulin|infusion|dose|mg/kg|prescribed|administer)", low):
            drug_bits.append(sent)
        elif re.search(
            r"\b(?:warfarin|prednisolone|tacrolimus|discontinu|therapy|treatment|aspirin|clopidogrel)",
            low,
        ):
            treatment_bits.append(sent)
        elif re.search(r"\b(?:discharged|improved|outcome|wheelchair|died|recovered|resolved)", low):
            outcome_bits.append(sent)
        elif re.search(r"\b(?:patient|woman|man|year-old|mg|myasthenia|dyspnea|intubation)", low):
            patient_bits.append(sent)

    for line in figure_captions_to_narrative(section):
        ae_bits.append(line)

    if patient_bits:
        bullets.append(f"- Patient Information: {' '.join(patient_bits[:2])}")
    if drug_bits:
        bullets.append(f"- Suspected Drug Information: {' '.join(drug_bits[:2])}")
    if ae_bits:
        bullets.append("- Adverse Event:")
        for ae in ae_bits[:5]:
            if ae.startswith("Figure "):
                bullets.append(f"- Imaging finding ({ae})")
                continue
            coding = code_adverse_event(ae)
            if coding:
                bullets.append(f"- {format_meddra(coding, ae)}")
            else:
                bullets.append(f"- {ae}")
    if treatment_bits:
        bullets.append(f"- Treatment Process: {' '.join(treatment_bits[:2])}")
    if outcome_bits:
        bullets.append(f"- Final outcome: {' '.join(outcome_bits[:2])}")

    return bullets


def build_structured_narrative_from_fields(
    patient: dict[str, str],
    drug: dict[str, str],
    reaction: dict[str, Any],
    text: str,
    tables: list[dict[str, Any]] | None,
) -> list[str]:
    """Build reference-style 7+13 bullets from extracted fields + table/figure prose."""
    parts: list[str] = []

    demo: list[str] = []
    if patient.get("patient_sex") and patient["patient_sex"] != "UK":
        demo.append(patient["patient_sex"])
    if patient.get("patient_age") and patient["patient_age"] != "UK":
        demo.append(f"age {patient['patient_age']}")
    if demo:
        parts.append(f"- Patient Information: The patient is a {', '.join(demo)}.")

    drug_name = drug.get("suspect_drug_name") or drug.get("suspect_drug_active_substance") or ""
    if drug_name and drug_name != "UK":
        dose = drug.get("suspect_drug_dose", "UK")
        route = drug.get("suspect_drug_route", "UK")
        indication = drug.get("suspect_drug_indication", "UK")
        bits = [drug_name]
        if dose != "UK":
            bits.append(f"at {dose}")
        if route != "UK":
            bits.append(f"via {route}")
        line = f"- Suspected Drug Information: The suspected drug is {' '.join(bits)}"
        if indication != "UK":
            line += f" for {indication}"
        line += "."
        parts.append(line)

    events = reaction.get("labeled_events") or []
    ae_lines: list[str] = []
    if events:
        parts.append("- Adverse Event:")
        for ev in events[:5]:
            display = ev.get("meddra_display") or ev.get("verbatim", "")
            if display:
                ae_lines.append(f"- {display}")
    else:
        ae = reaction.get("labeled_ae") or reaction.get("reaction_verbatim") or reaction.get("reaction_meddra_pt")
        if ae and ae != "UK":
            parts.append("- Adverse Event:")
            coding = code_adverse_event(str(ae))
            ae_lines.append(f"- {format_meddra(coding, str(ae)) if coding else ae}")

    for row_line in inline_tables_to_narrative(text):
        low = row_line.lower()
        if "summary:" in low or low.startswith("table 1 describes"):
            continue
        if _is_narrative_noise(row_line):
            continue
        age = patient.get("patient_age", "")
        sex = patient.get("patient_sex", "")
        if age and age != "UK":
            if f"{age}-year-old" not in low and f"age {age}" not in low:
                if re.search(r"\d{1,3}-year-old", row_line):
                    continue
        if sex and sex != "UK" and sex.lower().startswith("f") and "female" not in low and "male" in low:
            continue
        if sex and sex != "UK" and sex.lower().startswith("m") and "male" in low and "female" in low:
            continue
        ae_lines.append(f"- {row_line}")

    for fig_line in figure_captions_to_narrative(text):
        age = patient.get("patient_age", "")
        if age and age != "UK":
            fm = re.search(r"[FM]/(\d{1,3})", fig_line, re.I)
            if fm and fm.group(1) != age:
                continue
        ae_lines.append(f"- Imaging finding: {fig_line}")

    parts.extend(ae_lines[:6])

    outcome = reaction.get("reaction_outcome")
    if outcome and outcome != "UK":
        parts.append(f"- Final outcome: {outcome}")

    for line in structured_tables_to_narrative(tables or []):
        parts.append(f"- {line}")

    return parts


def enrich_narrative_with_structured_sources(
    text: str,
    tables: list[dict[str, Any]] | None,
    existing_parts: list[str],
    *,
    patient: dict[str, str] | None = None,
    drug: dict[str, str] | None = None,
    reaction: dict[str, Any] | None = None,
) -> list[str]:
    """Add table/figure/case prose; avoid duplicating existing bullets."""
    case_bullets = extract_case_section_narrative(text)
    if case_bullets:
        for line in inline_tables_to_narrative(text):
            if "summary:" in line.lower():
                continue
            bullet = f"- {line}"
            if not any(line.lower()[:60] in b.lower() for b in case_bullets):
                case_bullets.append(bullet)
        for line in figure_captions_to_narrative(text):
            bullet = f"- Imaging finding: {line}"
            if not any(line.lower()[:60] in b.lower() for b in case_bullets):
                case_bullets.append(bullet)
        return case_bullets

    if patient and drug and reaction:
        structured = build_structured_narrative_from_fields(patient, drug, reaction, text, tables)
        if structured:
            return structured

    parts = list(existing_parts)
    seen = {p.lower()[:100] for p in parts}

    for line in inline_tables_to_narrative(text):
        bullet = f"- {line}"
        key = bullet.lower()[:100]
        if key not in seen:
            seen.add(key)
            parts.append(bullet)

    for line in structured_tables_to_narrative(tables or []):
        bullet = f"- {line}"
        key = bullet.lower()[:100]
        if key not in seen:
            seen.add(key)
            parts.append(bullet)

    for line in figure_captions_to_narrative(text):
        bullet = f"- Imaging/Laboratory (figure): {line}"
        key = bullet.lower()[:100]
        if key not in seen:
            seen.add(key)
            parts.append(bullet)

    return parts
