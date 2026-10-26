from __future__ import annotations

import html
import re
from urllib.parse import urlsplit, urlunsplit

_TAG_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_BLOCK_RE = re.compile(r"(?i)</(p|div|li|h[1-6]|tr)>")
_TAGS_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"[ \t]{2,}")
_NL_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAGS_RE.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return raw
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def clip(value: str, n: int) -> str:
    return (value or "").strip()[:n]
