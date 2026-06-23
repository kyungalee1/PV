"""Sanitize CIOMS field values extracted from PDF forms (checkboxes, labels, symbols)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

UK = "UK"
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_DATE = re.compile(
    r"(\d{1,2})[-/\s]"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"[-/\s](\d{4})",
    re.I,
)
NARRATIVE_DISPLAY_MAX = 850

_CHECKED = r"[◉●☑✓√]"
_UNCHECKED = r"[○☐□]"

_FORM_DUMP = re.compile(
    r"Table row|Subject/Patient Details|Gender:\s*[◉○●]|"
    r"\b4\.\s*Severity\b|Ethnicity:|not checked Hispanic|"
    r"Hispanic/Latino|Asian\s+not checked|Native Hawaiian|"
    r"DD/MMM/YYYY|\(cm\)\s*Weight",
    re.I,
)


def _clean(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def extract_sex_from_text(text: str) -> str:
    """Find sex from checkbox forms: ◉ M ○ F, etc."""
    if not text:
        return ""
    for pat in (
        rf"(?:{_CHECKED})\s*M\b",
        rf"\bM\s*(?:{_CHECKED})",
        r"3\.?\s*Sex[^\n]{0,40}(?:◉|●|☑|✓)\s*M\b",
    ):
        if re.search(pat, text, re.I):
            return "male"
    for pat in (
        rf"(?:{_CHECKED})\s*F\b",
        rf"\bF\s*(?:{_CHECKED})",
        r"3\.?\s*Sex[^\n]{0,40}(?:◉|●|☑|✓)\s*F\b",
    ):
        if re.search(pat, text, re.I):
            return "female"
    m = re.search(rf"({_CHECKED})\s*([MF])\b", text, re.I)
    if m:
        return "male" if m.group(2).upper() == "M" else "female"
    return ""


def sanitize_sex(raw: str, *, full_text: str = "") -> str:
    """Return only male/female/UK — never height, weight, or DOB text."""
    from_text = extract_sex_from_text(full_text) if full_text else ""
    if from_text:
        return from_text

    s = _clean(raw)
    if not s or s.upper() == UK:
        return UK

    checked_m = re.search(rf"{_CHECKED}\s*M\b", s, re.I)
    checked_f = re.search(rf"{_CHECKED}\s*F\b", s, re.I)
    if checked_m and not checked_f:
        return "male"
    if checked_f and not checked_m:
        return "female"
    if checked_m and checked_f:
        return "male" if checked_m.start() < checked_f.start() else "female"

    if re.search(r"height|weight|dob|\(cm\)|\(kg\)|dd/mm", s, re.I):
        if re.search(r"\bmale\b", s, re.I):
            return "male"
        if re.search(r"\bfemale\b", s, re.I):
            return "female"
        lone = re.match(r"^([MF])$", s, re.I)
        if lone:
            return "male" if lone.group(1).upper() == "M" else "female"
        return UK

    low = s.lower()
    if low in ("m", "male", "man", "남", "남성"):
        return "male"
    if low in ("f", "female", "woman", "여", "여성"):
        return "female"
    if len(s) <= 12 and re.fullmatch(r"[MF]", s, re.I):
        return "male" if s.upper() == "M" else "female"
    return UK


def sanitize_age(raw: str) -> str:
    s = _clean(raw)
    if not s or s.upper() == UK:
        return UK
    if re.search(r"height|weight|dob|\(cm\)|\(kg\)", s, re.I):
        m = re.search(r"(\d{1,3})\s*(?:years?|yrs?|yo\b|month)", s, re.I)
        if m:
            unit = "month" if "month" in s.lower() else "Year"
            if "month" in s.lower():
                return f"{m.group(1)} month"
            return m.group(1)
        return UK
    m = re.search(r"(\d{1,3})\s*month", s, re.I)
    if m:
        return f"{m.group(1)} month"
    m = re.search(r"(\d{1,3})", s)
    if m and len(s) <= 20:
        return m.group(1)
    return s[:30] if len(s) <= 30 else UK


def sanitize_weight(raw: str) -> str:
    s = _clean(raw)
    if not s or s.upper() == UK:
        return UK
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)?", s, re.I)
    if m:
        return m.group(1)
    return UK if re.search(r"height|dob|sex|\(cm\)", s, re.I) else s[:20]


def sanitize_outcome(raw: str) -> str:
    s = _clean(raw)
    if not s or s.upper() == UK:
        return UK
    s = re.sub(rf"^({_CHECKED}|{_UNCHECKED})\s*", "", s)
    s = re.sub(rf"\s*({_CHECKED}|{_UNCHECKED})\s*", " ", s)
    s = _clean(s)
    for word in (
        "Recovered",
        "Recovering",
        "Not recovered",
        "Fatal",
        "Unknown",
        "Resolved",
        "Resolved with sequelae",
    ):
        if re.search(rf"\b{re.escape(word)}\b", s, re.I):
            return word if word[0].isupper() else word.capitalize()
    return s[:90] if len(s) <= 90 else UK


def parse_onset_date(text: str) -> str:
    """Extract a single YYYY-MM-DD from free text (field 4-6)."""
    if not text or str(text).strip().upper() == UK:
        return ""
    s = _clean(text)
    if _DATE_ONLY.match(s):
        return s

    m = _MONTH_DATE.search(s)
    if m:
        candidate = f"{m.group(1)} {m.group(2)} {m.group(3)}"
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

    for m in re.finditer(
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
        r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4})",
        s,
        re.I,
    ):
        raw = m.group(1).replace("/", "-").replace(".", "-")
        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
            "%d %B %Y",
            "%d %B, %Y",
            "%B %d, %Y",
            "%B %d %Y",
        ):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


_MONTH_NAME = (
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December"
)


def parse_flexible_date(text: str) -> str:
    """Partial or full calendar text: YYYY-MM-DD, YYYY-MM, YYYY, or month name."""
    if not text or str(text).strip().upper() == UK:
        return ""
    s = _clean(text)
    full = parse_onset_date(s)
    if full:
        return full

    m = re.match(r"^(\d{4})[-/.](\d{1,2})$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    m = re.match(r"^(\d{4})$", s)
    if m:
        return m.group(1)

    m = re.search(rf"({_MONTH_NAME})\s+(\d{{4}})", s, re.I)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %Y").strftime("%Y-%m")
        except ValueError:
            pass

    m = re.search(rf"(\d{{4}})\s+({_MONTH_NAME})", s, re.I)
    if m:
        try:
            return datetime.strptime(f"{m.group(2)} {m.group(1)}", "%B %Y").strftime("%Y-%m")
        except ValueError:
            pass

    m = re.match(rf"^({_MONTH_NAME})$", s, re.I)
    if m:
        return m.group(1).title()

    m = re.search(r"\b(19|20)\d{2}\b", s)
    if m:
        return m.group(0)

    m = re.search(r"\b(0?[1-9]|1[0-2])\b", s)
    if m and len(s) <= 4:
        return f"{int(m.group(1)):02d}"

    return ""


def parse_birth_date(text: str) -> str:
    """Date of birth — accept full or partial dates (year, month, year-month)."""
    return parse_flexible_date(text) or ""


def format_reaction_onset_field(cioms: dict[str, Any]) -> str:
    """Field 4-6 — onset date(s); supports multi-reaction 'Term: date; ...' format."""
    for key in ("reaction_onset_display", "reaction_onset_date"):
        raw = str(cioms.get(key) or "").strip()
        if raw and raw.upper() != UK:
            if ";" in raw or (":" in raw and len(raw) > 12):
                return raw
            parsed = parse_flexible_date(raw)
            if parsed:
                return parsed
    for key in ("reaction_verbatim", "reaction_meddra_pt", "narrative"):
        parsed = parse_flexible_date(str(cioms.get(key) or ""))
        if parsed:
            return parsed
    return UK


def contains_form_dump(text: str) -> bool:
    return bool(_FORM_DUMP.search(text)) or text.count("◉") + text.count("○") >= 4


def extract_severity_prose(text: str) -> str:
    """Convert ○ Grade 1 ◉ Grade 3 (Severe) … to one sentence."""
    if not text:
        return ""
    m = re.search(
        rf"{_CHECKED}\s*Grade\s*(\d)\s*\(([^)]+)\)",
        text,
        re.I,
    )
    if m:
        return f"The reaction severity was Grade {m.group(1)} ({m.group(2).strip()})."
    m = re.search(r"Grade\s*(\d)\s*\(([^)]+)\)", text, re.I)
    if m and re.search(r"severe|moderate|mild|life threatening", m.group(2), re.I):
        return f"The reaction severity was Grade {m.group(1)} ({m.group(2).strip()})."
    return ""


def extract_dob_prose(text: str) -> str:
    m = re.search(
        r"DOB\s*[:：]?\s*(\d{1,2}[/\-][A-Za-z]{3}[/\-]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        text,
        re.I,
    )
    if not m:
        return ""
    return f"born on {m.group(1)}"


def expand_form_symbols_to_prose(text: str) -> str:
    """Rewrite checkbox / grade / gender blocks as short prose."""
    if not text:
        return text
    out = text

    sev = extract_severity_prose(out)
    if sev:
        out = re.sub(
            rf"(?:4\.\s*)?Severity\s*:.*?Grade\s*\d\s*\([^)]+\).*?(?=\n|$)",
            sev,
            out,
            flags=re.I,
        )
        out = re.sub(
            rf"(?:{_UNCHECKED}|{_CHECKED})\s*Grade\s*\d\s*\([^)]+\)(?:\s*(?:{_UNCHECKED}|{_CHECKED})\s*Grade\s*\d\s*\([^)]+\))*",
            "",
            out,
            flags=re.I,
        )

    gender = extract_sex_from_text(out)
    if gender:
        out = re.sub(
            rf"Gender\s*:\s*(?:{_CHECKED}|{_UNCHECKED})?\s*[MF]\s*(?:{_UNCHECKED}|{_CHECKED})?\s*[MF][^\n.]{{0,120}}",
            f"The patient's gender is {gender}.",
            out,
            flags=re.I,
        )

    out = re.sub(rf"({_CHECKED}|{_UNCHECKED})\s*", "", out)
    out = re.sub(r"\bnot checked\b", "", out, flags=re.I)
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()


def strip_form_dumps(text: str) -> str:
    """Remove table/form checkbox dumps from narrative."""
    if not text:
        return text
    blocks = re.split(r"\n\s*\n", text)
    kept: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith("- Table row") or block.startswith("Table row"):
            continue
        if contains_form_dump(block) and not any(
            h in block for h in ("Patient Information:", "Suspected Drug Information:", "Final outcome")
        ):
            continue
        lines: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("- Table row") or line.startswith("Table row"):
                continue
            if _FORM_DUMP.search(line) and "Information:" not in line:
                continue
            if line.count("◉") + line.count("○") >= 3 and "Information:" not in line:
                continue
            lines.append(line)
        block = "\n".join(lines).strip()
        if block:
            kept.append(block)
    return "\n\n".join(kept)


def summarize_narrative(text: str, max_len: int = NARRATIVE_DISPLAY_MAX) -> str:
    """Keep structured sections; shorten when over max_len."""
    text = strip_form_dumps(text)
    if not text:
        return UK
    if len(text) <= max_len:
        return text

    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return _clean(text)[:max_len]

    per_section = max(100, max_len // max(len(parts), 1))
    shortened: list[str] = []
    for part in parts:
        if len(part) <= per_section:
            shortened.append(part)
            continue
        cut = part[: per_section - 3].rsplit(" ", 1)[0]
        shortened.append((cut or part[: per_section - 3]) + "...")

    result = "\n\n".join(shortened)
    if len(result) <= max_len:
        return result
    return result[: max_len - 3].rsplit(" ", 1)[0] + "..."


def prepare_narrative_for_display(cioms: dict[str, Any]) -> str:
    """Final 7+13: prose only, symbols expanded, form dumps removed, summarized if long."""
    raw = _clean(cioms.get("narrative"))
    payload = dict(cioms)
    payload["_source_text"] = raw or payload.get("_source_text", "")

    text = build_prose_narrative_from_cioms(payload)
    if text == UK and raw:
        text = strip_form_dumps(raw)

    sev = extract_severity_prose(raw or str(payload.get("_source_text", "")))
    if sev and "severity was Grade" not in text and "Grade 3" not in text:
        if "- Adverse Event:" in text:
            text = text.replace("- Adverse Event:", f"- Adverse Event: {sev}", 1)
        elif text != UK:
            text = f"{text}\n\n- Adverse Event: {sev}"

    return summarize_narrative(text)


def is_structured_narrative(text: str) -> bool:
    s = _clean(text)
    if not s:
        return False
    markers = (
        "Patient Information:",
        "Suspected Drug Information:",
        "Adverse Event:",
        "Treatment Process:",
        "Final outcome",
        "Report and Overall Opinion:",
    )
    return any(m in s for m in markers)


def build_prose_narrative_from_cioms(cioms: dict[str, Any]) -> str:
    """Field 7+13 — full narrative prose (no checkbox symbols or label dumps)."""
    sections: list[str] = []
    full_text = _clean(cioms.get("_source_text", ""))

    sex = sanitize_sex(_clean(cioms.get("patient_sex")), full_text=full_text)
    age = sanitize_age(cioms.get("patient_age"))
    weight = sanitize_weight(cioms.get("patient_weight_kg"))

    demo: list[str] = []
    if age != UK:
        demo.append(f"{age}-old" if age.endswith("month") else f"age {age}")
    if sex != UK:
        demo.append(sex)
    if weight != UK:
        demo.append(f"weighing {weight} kilograms")
    dob_note = extract_dob_prose(full_text)
    if dob_note and dob_note not in " ".join(demo):
        demo.append(dob_note)
    if demo:
        sections.append(f"- Patient Information: The patient is a {', '.join(demo)}.")

    drug_name = _clean(cioms.get("suspect_drug_name"))
    substance = _clean(cioms.get("suspect_drug_active_substance"))
    dose = _clean(cioms.get("suspect_drug_dose"))
    route = _clean(cioms.get("suspect_drug_route"))
    indication = _clean(cioms.get("suspect_drug_indication"))
    if drug_name and drug_name != UK:
        bits = [drug_name]
        if substance and substance != UK and substance.lower() not in drug_name.lower():
            bits.append(f"({substance})")
        drug_line = f"- Suspected Drug Information: The suspected drug is {' '.join(bits)}"
        extras: list[str] = []
        if dose and dose != UK:
            extras.append(f"dose {dose}")
        if route and route != UK:
            extras.append(f"route {route}")
        if indication and indication != UK:
            extras.append(f"indication {indication}")
        if extras:
            drug_line += f", administered {'; '.join(extras)}"
        drug_line += "."
        sections.append(drug_line)

    ae = (
        _clean(cioms.get("reaction_verbatim"))
        or _clean(cioms.get("reaction_meddra_pt"))
        or UK
    )
    severity = extract_severity_prose(full_text)
    if ae != UK:
        ae_line = f"- Adverse Event: The patient developed {ae}"
        if severity:
            m = re.search(r"Grade\s*(\d)\s*\(([^)]+)\)", severity, re.I)
            if m:
                ae_line += f", with severity Grade {m.group(1)} ({m.group(2).strip()})"
        ae_line += ", suspected to be related to the suspect drug."
        sections.append(ae_line)
    elif severity:
        sections.append(f"- Adverse Event: {severity}")

    outcome = sanitize_outcome(cioms.get("reaction_outcome", ""))
    if outcome != UK:
        low = outcome.lower()
        if low.startswith("recov"):
            sections.append(f"- Final outcome for the patient: The patient recovered.")
        else:
            sections.append(f"- Final outcome for the patient: The outcome was {outcome.lower()}.")

    causality = _clean(cioms.get("causality_assessment"))
    if causality and causality != UK:
        sections.append(f"- Report and Overall Opinion: {causality}")

    return "\n\n".join(sections) if sections else UK
