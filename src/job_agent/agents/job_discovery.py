"""Pull public job posts. Greenhouse, Lever, Ashby, or something you paste in."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from job_agent.embeddings.util import embed_texts
from job_agent.errors import ApplyPilotError, HttpFailure
from job_agent.log import event
from job_agent.net import request
from job_agent.records import BoardRef, JobPosting, StoredJob
from job_agent.text import clip, html_to_text, normalize_url

MAX_JD = 20_000


def _parse_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:  # lever sends ms
            stamp /= 1000
        try:
            return datetime.fromtimestamp(stamp, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _posting(company, title, source, url, jd, posted_at=None, metadata=None) -> JobPosting | None:
    text = (jd or "").strip()
    if len(text) < 20 or not url:
        return None
    return JobPosting(
        company=clip(company, 255) or "Unknown",
        title=clip(title, 255) or "Untitled",
        source=source,
        url=normalize_url(url),
        jd_text=text[:MAX_JD],
        posted_at=posted_at,
        metadata=metadata or {},
    )


def fetch_greenhouse(board_token: str, *, client: httpx.Client | None = None, timeout: float = 15,
                     retries: int = 3, sleep: Callable[[float], None] = time.sleep) -> list[JobPosting]:
    token = board_token.strip().strip("/")
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    # content=true is what actually includes the description
    resp = request("GET", url, client=client, params={"content": "true"}, timeout=timeout,
                   retries=retries, sleep=sleep)
    try:
        payload = resp.json()
    except Exception as exc:
        raise HttpFailure(f"greenhouse returned junk for {token}", url=url, retryable=False) from exc
    company_fallback = token.replace("-", " ").title()
    out: list[JobPosting] = []
    for job in payload.get("jobs") or []:
        raw = job.get("content") or ""
        text = html_to_text(raw) if "<" in raw else raw
        loc = (job.get("location") or {}).get("name") or ""
        posting = _posting(
            job.get("company_name") or company_fallback,
            job.get("title") or "",
            "greenhouse",
            job.get("absolute_url") or "",
            text or (job.get("title") or ""),
            _parse_dt(job.get("updated_at")),
            {"location": loc, "external_id": str(job.get("id") or ""), "board": token},
        )
        if posting:
            out.append(posting)
    return out


def fetch_lever(company: str, *, client: httpx.Client | None = None, timeout: float = 15,
                retries: int = 3, sleep: Callable[[float], None] = time.sleep) -> list[JobPosting]:
    slug = company.strip().strip("/")
    url = f"https://api.lever.co/v0/postings/{slug}"
    resp = request("GET", url, client=client, params={"mode": "json"}, timeout=timeout,
                   retries=retries, sleep=sleep)
    try:
        payload = resp.json()
    except Exception as exc:
        raise HttpFailure(f"lever returned junk for {slug}", url=url, retryable=False) from exc
    if isinstance(payload, dict):
        payload = payload.get("postings") or payload.get("data") or []
    label = slug.replace("-", " ").title()
    out: list[JobPosting] = []
    for job in payload or []:
        text = job.get("descriptionPlain") or html_to_text(job.get("description") or "")
        cats = job.get("categories") or {}
        posting = _posting(
            label,
            job.get("text") or "",
            "lever",
            job.get("hostedUrl") or job.get("applyUrl") or "",
            text,
            _parse_dt(job.get("createdAt")),
            {"location": cats.get("location") or "", "team": cats.get("team") or "",
             "external_id": str(job.get("id") or ""), "board": slug},
        )
        if posting:
            out.append(posting)
    return out


def fetch_ashby(board: str, *, client: httpx.Client | None = None, timeout: float = 15,
                retries: int = 3, sleep: Callable[[float], None] = time.sleep) -> list[JobPosting]:
    slug = board.strip().strip("/")
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = request("GET", url, client=client, timeout=timeout, retries=retries, sleep=sleep)
    try:
        payload = resp.json()
    except Exception as exc:
        raise HttpFailure(f"ashby returned junk for {slug}", url=url, retryable=False) from exc
    label = slug.replace("-", " ").title()
    out: list[JobPosting] = []
    for job in payload.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        text = job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml") or "")
        link = job.get("jobUrl") or job.get("applyUrl") or ""
        posting = _posting(
            label,
            job.get("title") or "",
            "ashby",
            link,
            text,
            _parse_dt(job.get("publishedAt")),
            {"location": job.get("location") or "", "department": job.get("department") or "",
             "external_id": str(job.get("id") or ""), "board": slug},
        )
        if posting:
            out.append(posting)
    return out


_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def _role_ok(posting: JobPosting, roles: list[str]) -> bool:
    if not roles:
        return True
    blob = f"{posting.title}\n{posting.jd_text}".lower()
    return any(role.strip().lower() in blob for role in roles if role.strip())


class DiscoverResult:
    def __init__(self, jobs: list[JobPosting], errors: list[str]) -> None:
        self.jobs = jobs
        self.errors = errors


def discover_jobs(
    boards: list[BoardRef],
    *,
    roles: list[str] | None = None,
    client: httpx.Client | None = None,
    timeout: float = 15,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> DiscoverResult:
    """One bad board doesn't drop the others."""
    found: list[JobPosting] = []
    errors: list[str] = []
    seen: set[str] = set()
    for board in boards:
        fn = _FETCHERS.get((board.source or "").lower())
        if fn is None:
            errors.append(f"unknown source {board.source}")
            continue
        try:
            posts = fn(board.token, client=client, timeout=timeout, retries=retries, sleep=sleep)
        except Exception as exc:
            msg = f"{board.source}:{board.token}: {exc}"
            errors.append(msg)
            event("discover", ok=False, source=board.source, token=board.token, error=str(exc)[:300])
            continue
        for post in posts:
            if not _role_ok(post, roles or []):
                continue
            if post.url in seen:
                continue
            seen.add(post.url)
            found.append(post)
    return DiscoverResult(found, errors)


def import_manual(*, company: str, title: str, url: str, jd_text: str,
                  posted_at: datetime | None = None) -> JobPosting:
    posting = _posting(company, title, "manual", url, jd_text, posted_at, {"imported": "paste"})
    if posting is None:
        raise ValueError("need a url and some job text")
    return posting


def import_from_url(url: str, *, client: httpx.Client | None = None, company: str = "",
                    title: str = "", timeout: float = 15, retries: int = 2,
                    sleep: Callable[[float], None] = time.sleep) -> JobPosting:
    resp = request("GET", url, client=client, timeout=timeout, retries=retries, sleep=sleep)
    raw = resp.text or ""
    text = html_to_text(raw)
    if not title:
        import re
        m = re.search(r"(?is)<title>(.*?)</title>", raw)
        title = html_to_text(m.group(1)) if m else "Untitled role"
    if not company:
        from urllib.parse import urlsplit
        company = urlsplit(url).netloc or "Unknown"
    posting = _posting(company, title, "manual", url, text, None, {"imported": "url"})
    if posting is None:
        raise HttpFailure("page had almost no text", url=url, retryable=False)
    return posting


def persist_jobs(store, embedder, postings: list[JobPosting]) -> tuple[list[tuple[StoredJob, bool]], list[str]]:
    saved: list[tuple[StoredJob, bool]] = []
    errors: list[str] = []
    for post in postings:
        try:
            try:
                emb = embed_texts(embedder, [post.jd_text], attempts=2)[0]
            except ApplyPilotError as exc:
                event("embed_jd", ok=False, url=post.url, error=str(exc)[:200])
                emb = None
            job, created = store.upsert_job(post, emb)
            if created:
                store.get_or_create_application(job.job_id)
            saved.append((job, created))
        except Exception as exc:
            errors.append(f"{post.url}: {exc}")
            event("persist_job", ok=False, url=post.url, error=str(exc)[:300])
    return saved, errors
