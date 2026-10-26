"""Find a public email or guess a pattern. Never sends anything. Never verified."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from job_agent.net import request
from job_agent.records import StoredContact

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BAD_LOCAL = ("noreply", "no-reply", "donotreply", "do-not-reply", "sentry", "wixpress")
_BAD_TLD = {"png", "jpg", "jpeg", "gif", "svg", "css", "js", "webp"}
_GENERIC = {"recruiting", "recruitment", "jobs", "job", "careers", "career", "talent", "hello", "info", "hr"}


@dataclass
class FoundContact:
    name: str
    title: str | None
    email: str | None
    verified: bool
    source: str = "pattern_guess"
    confidence: float = 0.0
    page: str | None = None


def _company_domain(company: str) -> str:
    first = (company or "company").split(",")[0].split()[0]
    token = re.sub(r"[^a-z0-9]", "", first.lower()) or "company"
    return f"{token}.com"


def _clean_emails(text: str) -> list[str]:
    found = []
    seen = set()
    for match in _EMAIL_RE.findall(text or ""):
        email = match.strip(".,;:<>()[]").lower()
        local, _, domain = email.partition("@")
        tld = domain.rsplit(".", 1)[-1]
        if tld in _BAD_TLD or any(bad in local for bad in _BAD_LOCAL):
            continue
        if email in seen or not domain:
            continue
        seen.add(email)
        found.append(email)
    return found


def _name_for(email: str) -> tuple[str, str]:
    local = email.split("@", 1)[0]
    if local in _GENERIC or local.replace(".", "") in _GENERIC:
        return "Recruiting", "Talent team"
    pretty = " ".join(part.capitalize() for part in re.split(r"[._+\-]", local) if part)
    return pretty or "Recruiting", "Public page"


def _from_page(text: str, *, page_url: str) -> list[FoundContact]:
    contacts = []
    for email in _clean_emails(text):
        name, title = _name_for(email)
        contacts.append(FoundContact(
            name=name, title=title, email=email, verified=False,
            source="public_page", confidence=0.55, page=page_url,
        ))
    return contacts


def pattern_guesses(company: str) -> list[FoundContact]:
    domain = _company_domain(company)
    guesses = [
        ("Recruiting", "Talent team", f"recruiting@{domain}", 0.2),
        ("Jobs", "Careers inbox", f"jobs@{domain}", 0.15),
        ("Careers", "Careers page", f"careers@{domain}", 0.15),
    ]
    return [
        FoundContact(name, title, email, verified=False, source="pattern_guess", confidence=conf)
        for name, title, email, conf in guesses
    ]


def find_contacts(job, *, client: httpx.Client | None = None, max_contacts: int = 3,
                  timeout: float = 8, retries: int = 1) -> list[FoundContact]:
    """job needs .url, .company, .metadata. verified is always False."""
    pages = [job.url]
    website = (getattr(job, "metadata", None) or {}).get("website")
    if website:
        root = str(website).rstrip("/")
        pages.extend([root, root + "/careers", root + "/about"])
    else:
        domain = _company_domain(job.company)
        pages.extend([f"https://{domain}/careers", f"https://{domain}/about"])

    found: list[FoundContact] = []
    seen = set()
    for url in pages:
        if not url:
            continue
        try:
            resp = request("GET", url, client=client, timeout=timeout, retries=retries)
            batch = _from_page(resp.text or "", page_url=url)
        except Exception:
            continue
        for contact in batch:
            if not contact.email or contact.email in seen:
                continue
            seen.add(contact.email)
            found.append(contact)
            if len(found) >= max_contacts:
                return found

    for guess in pattern_guesses(job.company):
        if guess.email in seen:
            continue
        seen.add(guess.email)
        found.append(guess)
        if len(found) >= max_contacts:
            break
    return found[:max_contacts]


def to_stored(job_id: uuid.UUID, contacts: list[FoundContact]) -> list[StoredContact]:
    now = datetime.now(UTC)
    rows = []
    for c in contacts:
        rows.append(StoredContact(
            id=uuid.uuid4(),
            job_id=job_id,
            name=c.name,
            title=c.title,
            email=c.email,
            source=c.source,
            verified=False,  # we don't have a way to verify, so this stays false
            confidence=c.confidence,
            metadata={"confidence": c.confidence, "unverified": True, "page": c.page},
            created_at=now,
        ))
    return rows
