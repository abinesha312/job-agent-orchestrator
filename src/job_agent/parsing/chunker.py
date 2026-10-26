"""Section-aware chunking.

Splits resume text into sections by recognising common resume headings, then packs
lines/bullets inside each section into chunks of at most ``max_chars``. A chunk never
spans two sections. Each chunk carries metadata: resume_id, version, section, order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical section name -> heading aliases (lower-case, no punctuation).
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "profile", "objective", "about me",
                "career summary", "career objective", "professional profile"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "relevant experience"),
    "education": ("education", "academic background", "education and training"),
    "skills": ("skills", "technical skills", "core skills", "core competencies", "competencies",
               "technologies", "tech stack", "skills and tools"),
    "projects": ("projects", "selected projects", "personal projects", "academic projects",
                 "key projects"),
    "certifications": ("certifications", "certificates", "licenses and certifications",
                       "certifications and licenses"),
    "publications": ("publications", "research", "research and publications", "patents"),
    "awards": ("awards", "honors", "honors and awards", "achievements", "awards and honors"),
    "leadership": ("leadership", "volunteer", "volunteering", "activities",
                   "leadership and activities", "volunteer experience"),
}
_ALIAS_TO_SECTION = {alias: name for name, aliases in SECTION_ALIASES.items() for alias in aliases}
HEADER_SECTION = "header"  # text before the first heading (name, contact line)

_BULLET_RE = re.compile(r"^\s*[•●▪◦‣\-\*–]\s+")
_NORMALISE_RE = re.compile(r"[^a-z& ]+")


@dataclass
class Chunk:
    text: str
    section: str
    order: int
    section_order: int
    metadata: dict = field(default_factory=dict)


def _heading_section(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 40 or _BULLET_RE.match(stripped):
        return None
    key = _NORMALISE_RE.sub(" ", stripped.lower().replace("&", " and ")).strip()
    key = re.sub(r"\s+", " ", key)
    return _ALIAS_TO_SECTION.get(key)


def detect_sections(text: str) -> list[tuple[str, list[str]]]:
    """Return ``[(section, lines), ...]`` in document order. Empty sections are dropped."""
    sections: list[tuple[str, list[str]]] = [(HEADER_SECTION, [])]
    for raw in text.splitlines():
        line = raw.rstrip()
        name = _heading_section(line)
        if name is not None:
            sections.append((name, []))
            continue
        sections[-1][1].append(line)
    return [(name, lines) for name, lines in sections if any(ln.strip() for ln in lines)]


def _units(lines: list[str]) -> list[str]:
    """Group lines into atomic units: a bullet plus its wrapped continuation lines,
    or a paragraph of consecutive non-bullet lines separated by blank lines."""
    units: list[str] = []
    current: list[str] = []
    current_is_bullet = False

    def flush() -> None:
        nonlocal current
        if current:
            units.append(" ".join(s.strip() for s in current if s.strip()))
        current = []

    for line in lines:
        if not line.strip():
            flush()
            current_is_bullet = False
            continue
        if _BULLET_RE.match(line):
            flush()
            current = [line]
            current_is_bullet = True
        elif current_is_bullet and line[:1].islower():
            current.append(line)  # wrapped continuation of a bullet
        else:
            if current_is_bullet:
                flush()
                current_is_bullet = False
            current.append(line)
            # Non-bullet lines (titles, dates, company lines) stand alone.
            flush()
    flush()
    return [u for u in units if u]


def _split_long(unit: str, max_chars: int) -> list[str]:
    if len(unit) <= max_chars:
        return [unit]
    parts: list[str] = []
    buf = ""
    for word in unit.split():
        if buf and len(buf) + 1 + len(word) > max_chars:
            parts.append(buf)
            buf = word
        else:
            buf = f"{buf} {word}".strip()
    if buf:
        parts.append(buf)
    return parts


def chunk_resume(
    text: str,
    *,
    resume_id: str,
    version: int,
    max_chars: int = 800,
    extra_metadata: dict | None = None,
) -> list[Chunk]:
    """Chunk resume text section-by-section with per-chunk metadata."""
    chunks: list[Chunk] = []
    order = 0
    for section, lines in detect_sections(text):
        pieces: list[str] = []
        for unit in _units(lines):
            pieces.extend(_split_long(unit, max_chars))
        buf: list[str] = []
        size = 0
        section_order = 0

        def emit(section: str = section) -> None:
            nonlocal order, section_order, buf, size
            if not buf:
                return
            body = "\n".join(buf)
            meta = {
                "resume_id": resume_id,
                "version": version,
                "section": section,
                "order": order,
                "section_order": section_order,
                "char_count": len(body),
                **(extra_metadata or {}),
            }
            chunks.append(Chunk(body, section, order, section_order, meta))
            order += 1
            section_order += 1
            buf, size = [], 0

        for piece in pieces:
            if buf and size + 1 + len(piece) > max_chars:
                emit()
            buf.append(piece)
            size += len(piece) + 1
        emit()
    return chunks
