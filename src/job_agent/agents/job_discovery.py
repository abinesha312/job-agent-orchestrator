"""Job discovery agent — STUB (Phase 4).

Official/public APIs only (no LinkedIn scraping, no CAPTCHA bypass):
  - Greenhouse Job Board API: GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
  - Lever Postings API:       GET https://api.lever.co/v0/postings/{company}?mode=json
  - Adzuna Search API:        GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
                              ?app_id=...&app_key=...&what=...&where=...  (needs ADZUNA_APP_ID/KEY)

TODO(phase-4):
  - Normalise each posting to a ``jobs`` row (company, title, source, url, jd_text, posted_at,
    raw payload in metadata), dedupe on url, embed jd_text into jd_embedding.
  - Create an ``applications`` row with status=discovered.
  - Respect rate limits; schedule via Cloud Tasks in production.
  - Exit criterion: 50 jobs ingested and scored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobPosting:
    company: str
    title: str
    source: str  # "greenhouse" | "lever" | "adzuna"
    url: str
    jd_text: str
    posted_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


def fetch_greenhouse(board_token: str) -> list[JobPosting]:
    raise NotImplementedError("Phase 4: Greenhouse fetcher not implemented yet")


def fetch_lever(company: str) -> list[JobPosting]:
    raise NotImplementedError("Phase 4: Lever fetcher not implemented yet")


def fetch_adzuna(query: str, *, where: str = "", country: str = "us", page: int = 1) -> list[JobPosting]:
    raise NotImplementedError("Phase 4: Adzuna fetcher not implemented yet")


def discover_jobs(target_roles: list[str]) -> list[JobPosting]:
    """Fan out to all sources for the target roles and dedupe. TODO(phase-4)."""
    raise NotImplementedError("Phase 4: job discovery not implemented yet")
