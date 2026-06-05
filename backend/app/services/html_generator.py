"""CIOMS Form I — HTML table layout (aligned fields, print-friendly)."""

from __future__ import annotations

import html
import re
from pathlib import Path

from app.services.cioms_mapping import build_cioms_context

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "cioms_form.html"


def _soft_wrap(text: str, chunk: int = 48) -> str:
    """Break very long tokens (PDF glue text) so table cells can wrap."""

    def repl(m: re.Match[str]) -> str:
        s = m.group(0)
        if len(s) <= chunk:
            return s
        return " ".join(s[i : i + chunk] for i in range(0, len(s), chunk))

    return re.sub(rf"\S{{{chunk + 1},}}", repl, text)


def _escape_multiline(text: str) -> str:
    wrapped = _soft_wrap(text)
    return html.escape(wrapped).replace("\n", "<br>")


def generate_cioms_html(cioms: dict, case_id: int) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    ctx = build_cioms_context(cioms, case_id)
    for key, value in ctx.items():
        safe = _escape_multiline(value)
        template = template.replace(f"{{{{{key}}}}}", safe)
    leftover = re.findall(r"\{\{(\w+)\}\}", template)
    if leftover:
        raise ValueError(f"Unresolved CIOMS HTML placeholders: {', '.join(leftover)}")
    return template


def generate_cioms_html_file(cioms: dict, case_id: int, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_cioms_html(cioms, case_id), encoding="utf-8")
    return output_path
