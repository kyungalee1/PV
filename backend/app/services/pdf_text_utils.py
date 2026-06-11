"""Repair common PDF text extraction artifacts (spacing, glued words)."""

from __future__ import annotations

import re

# e.g. "a r t i c l e i n f o" from two-column / positioned PDF text
_SPACED_CHAR_RUN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z0-9]\s){4,}"
    r"[A-Za-z0-9]"
    r"(?![A-Za-z0-9])",
)

# e.g. "c linical" when a line break splits a word (not "a patient")
_LINE_BREAK_FRAG = re.compile(r"\b([b-hj-z])\s+([a-z]{2,})\b", re.I)

# Insert spaces before common words when PDF glues them (longest first, min 4 chars)
_COMMON_WORDS = sorted(
    [
        "administration", "understand", "frequency", "features", "clinical",
        "hypertension", "hospitalization", "presentation", "complication",
        "university", "hospital", "republic", "october", "november", "december",
        "january", "february", "history", "patient", "related", "study",
        "received", "accepted", "abstract", "article", "keywords", "persistent",
        "diplopia", "after", "with", "from", "aimed", "under", "current", "info",
    ],
    key=len,
    reverse=True,
)

_GLUED_TOKEN = re.compile(r"[A-Za-z]{7,}")


def insert_missing_word_spaces(text: str) -> str:
    """Split long glued tokens using common English word boundaries."""

    def fix_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if " " in token:
            return token
        result = re.sub(r"^The(?=current)", "The ", token, flags=re.I)
        for word in _COMMON_WORDS:
            result = re.sub(rf"(?<=[a-z])(?={word}(?=[a-z]|$))", " ", result, flags=re.I)
        result = re.sub(r"(?<=[a-z]{3})(?=to(?:[a-z]{3,}|$))", " ", result, flags=re.I)
        result = re.sub(r"(?<=[a-z]{4})(?=the(?:[a-z]{3,}|$))", " ", result, flags=re.I)
        result = re.sub(r"(?<=[a-z]{5})(?=and(?=[a-z]{1,2}$))", " ", result, flags=re.I)
        return result

    for _ in range(2):
        text = _GLUED_TOKEN.sub(fix_token, text)
    return text


def collapse_spaced_characters(text: str) -> str:
    """Join characters separated by spaces: 'a r t i c l e' -> 'article'."""

    def repl(match: re.Match[str]) -> str:
        return match.group(0).replace(" ", "")

    return _SPACED_CHAR_RUN.sub(repl, text)


def split_glued_words(text: str) -> str:
    """Insert missing spaces: 'UniversityHospital' -> 'University Hospital'."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)
    text = re.sub(r",(?!\s)", ", ", text)
    text = re.sub(r";(?!\s)", "; ", text)
    return text


def merge_linebreak_fragments(text: str) -> str:
    """Fix 'c linicalfeatures' / 'wa sno' style breaks from wrapped PDF lines."""
    text = _LINE_BREAK_FRAG.sub(r"\1\2", text)
    text = re.sub(r"\bandc\b", "and c", text, flags=re.I)
    text = re.sub(r"\b([a-z]{2,})\s+([a-z])([a-z]{2,})\b", r"\1\2 \3", text)
    return text


def repair_pdf_text(text: str) -> str:
    """Full cleanup pipeline for pdfplumber extract_text output."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = collapse_spaced_characters(text)
    text = merge_linebreak_fragments(text)
    # Fix "ofKorea" before camelCase split turns it into "of Korea"
    text = re.sub(r"(?<=[a-z])of(?=[a-zA-Z])", " of ", text, flags=re.I)
    text = split_glued_words(text)
    text = insert_missing_word_spaces(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
