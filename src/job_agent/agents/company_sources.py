"""Public job search for specific companies: AMD, Apple, Microsoft, Amazon, OpenAI, Anthropic.

Everything here reads the same public pages or JSON a visitor's browser reads. There is no login,
no Google OAuth and no application submission: none of these career sites accepts a third party
signing in on someone's behalf, and ApplyPilot never applies. ``apply_url`` points at the
company's own page, where you sign in and submit yourself.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from job_agent.agents.job_discovery import (
    _parse_dt,
    _posting,
    fetch_ashby,
    fetch_greenhouse,
)
from job_agent.net import request
from job_agent.records import JobPosting
from job_agent.text import html_to_text

Sleep = Callable[[float], None]


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    careers_url: str
    ats: str
    sign_in: str
    how: str


COMPANIES: tuple[Company, ...] = (
    Company("amd", "AMD", "https://careers.amd.com", "iCIMS",
            "AMD account on iCIMS (email and password)", "careers.amd.com public jobs API"),
    Company("apple", "Apple", "https://jobs.apple.com", "Apple Jobs",
            "Apple Account", "jobs.apple.com search page data (first page only, summaries)"),
    Company("microsoft", "Microsoft", "https://apply.careers.microsoft.com", "Eightfold",
            "Microsoft account", "apply.careers.microsoft.com public search and detail API"),
    Company("amazon", "Amazon", "https://www.amazon.jobs", "amazon.jobs",
            "Amazon account", "amazon.jobs public search.json"),
    Company("openai", "OpenAI", "https://jobs.ashbyhq.com/openai", "Ashby",
            "Email link or Google, chosen on the Ashby form", "Ashby public posting API"),
    Company("anthropic", "Anthropic", "https://job-boards.greenhouse.io/anthropic", "Greenhouse",
            "Email link or Google, chosen on the Greenhouse form", "Greenhouse public board API"),
)
BY_ID = {c.id: c for c in COMPANIES}


def _json(resp: httpx.Response, what: str) -> dict:
    try:
        return resp.json()
    except Exception as exc:
        raise ValueError(f"{what} returned something that is not JSON") from exc


def fetch_amd(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
              sleep: Sleep = time.sleep) -> list[JobPosting]:
    resp = request("GET", "https://careers.amd.com/api/jobs", client=client, timeout=timeout,
                   retries=retries, sleep=sleep, params={"keywords": query, "page": 1, "limit": limit})
    out = []
    for row in _json(resp, "amd").get("jobs") or []:
        d = row.get("data") or {}
        text = html_to_text(" ".join(filter(None, [d.get("description"), d.get("responsibilities"),
                                                  d.get("qualifications")])))
        p = _posting("AMD", d.get("title") or "", "amd",
                     f"https://careers.amd.com/careers-home/jobs/{d.get('req_id') or d.get('slug')}",
                     text, _parse_dt(d.get("posted_date")),
                     {"location": d.get("full_location") or d.get("location_name") or "",
                      "external_id": str(d.get("req_id") or ""), "apply_url": d.get("apply_url") or "",
                      "ats": "icims"})
        if p:
            out.append(p)
    return out[:limit]


def fetch_amazon(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
                 sleep: Sleep = time.sleep) -> list[JobPosting]:
    resp = request("GET", "https://www.amazon.jobs/en/search.json", client=client, timeout=timeout,
                   retries=retries, sleep=sleep,
                   params={"base_query": query, "result_limit": limit, "country": "USA"})
    out = []
    for j in _json(resp, "amazon").get("jobs") or []:
        text = html_to_text(" ".join(filter(None, [
            j.get("description"), j.get("basic_qualifications"), j.get("preferred_qualifications")])))
        path = j.get("job_path") or ""
        p = _posting("Amazon", j.get("title") or "", "amazon",
                     f"https://www.amazon.jobs{path}" if path else "", text, None,
                     {"location": j.get("normalized_location") or j.get("location") or "",
                      "external_id": str(j.get("id_icims") or j.get("id") or ""),
                      "apply_url": j.get("url_next_step") or "", "team": j.get("job_category") or "",
                      "entity": j.get("company_name") or ""})
        if p:
            out.append(p)
    return out[:limit]


def fetch_microsoft(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
                    sleep: Sleep = time.sleep) -> list[JobPosting]:
    base = "https://apply.careers.microsoft.com/api/pcsx"
    resp = request("GET", f"{base}/search", client=client, timeout=timeout, retries=retries, sleep=sleep,
                   params={"domain": "microsoft.com", "query": query, "start": 0, "sort_by": "relevance"})
    positions = ((_json(resp, "microsoft").get("data") or {}).get("positions")) or []
    out = []
    for pos in positions[:limit]:
        pid = pos.get("id")
        detail = request("GET", f"{base}/position_details", client=client, timeout=timeout, retries=retries,
                         sleep=sleep, params={"position_id": pid, "domain": "microsoft.com", "hl": "en"})
        d = (_json(detail, "microsoft detail").get("data")) or {}
        text = html_to_text(d.get("jobDescription") or "")
        posted = pos.get("postedTs")
        p = _posting("Microsoft", d.get("name") or pos.get("name") or "", "microsoft",
                     d.get("publicUrl") or f"https://apply.careers.microsoft.com/careers/job/{pid}",
                     text, _parse_dt(posted),
                     {"location": d.get("location") or ", ".join(pos.get("locations") or []),
                      "external_id": str(d.get("displayJobId") or pos.get("displayJobId") or pid),
                      "department": pos.get("department") or ""})
        if p:
            out.append(p)
    return out


_APPLE_STATE = re.compile(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);', re.S)


def fetch_apple(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
                sleep: Sleep = time.sleep) -> list[JobPosting]:
    """Reads the search results Apple embeds in its search page. First page only (about 20)."""
    resp = request("GET", "https://jobs.apple.com/en-us/search", client=client, timeout=timeout,
                   retries=retries, sleep=sleep,
                   params={"search": query, "location": "united-states-USA"})
    m = _APPLE_STATE.search(resp.text or "")
    if not m:
        raise ValueError("apple search page changed shape; no embedded results found")
    state = json.loads(json.loads(f'"{m.group(1)}"'))
    results = ((state.get("loaderData") or {}).get("search") or {}).get("searchResults") or []
    out = []
    for r in results[:limit]:
        pid, slug = r.get("positionId"), r.get("transformedPostingTitle") or ""
        locs = ", ".join(x.get("name", "") for x in (r.get("locations") or []) if isinstance(x, dict))
        p = _posting("Apple", r.get("postingTitle") or "", "apple",
                     f"https://jobs.apple.com/en-us/details/{pid}/{slug}" if pid else "",
                     r.get("jobSummary") or "", _parse_dt(r.get("postDateInGMT")),
                     {"location": locs, "external_id": str(r.get("reqId") or pid or ""),
                      "team": ((r.get("team") or {}).get("teamName")) or ""})
        if p:
            out.append(p)
    return out


def fetch_openai(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
                 sleep: Sleep = time.sleep) -> list[JobPosting]:
    posts = fetch_ashby("openai", client=client, timeout=timeout, retries=retries, sleep=sleep)
    for p in posts:
        p.company = "OpenAI"
    return _filter(posts, query)[:limit]


def fetch_anthropic(query: str, *, limit: int = 25, client=None, timeout: float = 15, retries: int = 3,
                    sleep: Sleep = time.sleep) -> list[JobPosting]:
    posts = fetch_greenhouse("anthropic", client=client, timeout=timeout, retries=retries, sleep=sleep)
    for p in posts:
        p.company = "Anthropic"
    return _filter(posts, query)[:limit]


def _filter(posts: list[JobPosting], query: str) -> list[JobPosting]:
    words = [w for w in re.split(r"[\s,]+", (query or "").lower()) if w]
    if not words:
        return posts
    return [p for p in posts if any(w in f"{p.title}\n{p.jd_text}".lower() for w in words)]


FETCHERS: dict[str, Callable[..., list[JobPosting]]] = {
    "amd": fetch_amd, "apple": fetch_apple, "microsoft": fetch_microsoft,
    "amazon": fetch_amazon, "openai": fetch_openai, "anthropic": fetch_anthropic,
}


def search_companies(ids: list[str], query: str, *, limit: int = 25, client=None, timeout: float = 15,
                     retries: int = 2, sleep: Sleep = time.sleep) -> tuple[list[JobPosting], list[str]]:
    """One company failing does not drop the others."""
    found: list[JobPosting] = []
    errors: list[str] = []
    for cid in ids:
        fn = FETCHERS.get(cid)
        if fn is None:
            errors.append(f"unknown company {cid}")
            continue
        try:
            found.extend(fn(query, limit=limit, client=client, timeout=timeout, retries=retries, sleep=sleep))
        except Exception as exc:
            errors.append(f"{cid}: {exc}")
    return found, errors
