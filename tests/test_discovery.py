import httpx
import respx

from job_agent.agents.job_discovery import (
    discover_jobs,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    import_from_url,
    import_manual,
    persist_jobs,
)
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.records import BoardRef
from job_agent.storage.pipeline import InMemoryPipelineStore

GH = {
    "jobs": [
        {
            "id": 101,
            "title": "Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/101",
            "updated_at": "2026-01-02T00:00:00Z",
            "location": {"name": "Austin, TX"},
            "company_name": "Example Corp",
            "content": "<p>Must have: Python, FastAPI, PostgreSQL, Docker.</p>",
        },
        {
            "id": 102,
            "title": "Account Executive",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/102",
            "content": "<p>Sell things. Must have: Salesforce.</p>",
        },
    ]
}

LEVER = [
    {
        "id": "abc",
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/example/abc",
        "descriptionPlain": "Must have: Python, FastAPI, PostgreSQL, Docker. Build APIs.",
        "createdAt": 1767225600000,
        "categories": {"location": "Remote", "team": "Eng"},
    }
]

ASHBY = {
    "jobs": [
        {
            "id": "ash-1",
            "title": "Backend Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/example/ash-1",
            "descriptionPlain": "Must have: Python, FastAPI, PostgreSQL, Docker.",
            "publishedAt": "2026-02-01T00:00:00.000Z",
            "location": "Remote",
            "isListed": True,
        },
        {
            "id": "hidden",
            "title": "Secret Role",
            "jobUrl": "https://jobs.ashbyhq.com/example/hidden",
            "descriptionPlain": "Must have: Python. This one is unlisted.",
            "isListed": False,
        },
    ]
}


def test_parses_each_board():
    with respx.mock:
        respx.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").mock(
            return_value=httpx.Response(200, json=GH)
        )
        respx.get(url__regex=r"https://api\.lever\.co/.*").mock(
            return_value=httpx.Response(200, json=LEVER)
        )
        respx.get(url__regex=r"https://api\.ashbyhq\.com/.*").mock(
            return_value=httpx.Response(200, json=ASHBY)
        )
        gh = fetch_greenhouse("example")
        lever = fetch_lever("example")
        ash = fetch_ashby("example")
    assert len(gh) == 2 and gh[0].source == "greenhouse" and "FastAPI" in gh[0].jd_text
    assert gh[0].company == "Example Corp"
    assert len(lever) == 1 and lever[0].source == "lever" and lever[0].posted_at is not None
    assert len(ash) == 1 and ash[0].source == "ashby"


def test_one_bad_board_does_not_kill_the_run():
    with respx.mock:
        respx.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").mock(
            return_value=httpx.Response(200, json=GH)
        )
        respx.get(url__regex=r"https://api\.lever\.co/.*").mock(
            return_value=httpx.Response(404, text="missing")
        )
        result = discover_jobs(
            [BoardRef("greenhouse", "example"), BoardRef("lever", "nope"), BoardRef("nope", "x")],
            roles=["backend"],
            sleep=lambda _s: None,
        )
    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Backend Engineer"
    assert len(result.errors) == 2
    assert any("lever" in err for err in result.errors)


def test_dedupe_and_manual_import(tmp_path):
    store = InMemoryPipelineStore(tmp_path / "runs.jsonl")
    embedder = FakeEmbedder(32)
    manual = import_manual(
        company="Example Corp",
        title="Backend Engineer",
        url="https://boards.greenhouse.io/example/jobs/101",
        jd_text="Must have: Python, FastAPI, PostgreSQL, Docker. We ship APIs.",
    )
    with respx.mock:
        respx.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").mock(
            return_value=httpx.Response(200, json=GH)
        )
        found = discover_jobs([BoardRef("greenhouse", "example")], roles=["backend"])
    saved, errors = persist_jobs(store, embedder, [manual, *found.jobs])
    assert not errors
    assert len(store.list_jobs()) == 1
    assert sum(1 for _, created in saved if created) == 1
    again, _ = persist_jobs(store, embedder, [manual])
    assert again[0][1] is False
    assert len(store.list_applications()) == 1


def test_import_url_strips_html():
    page = "<html><title>Backend Engineer</title><body><p>Must have: Python, Docker.</p></body></html>"
    with respx.mock:
        respx.get("https://jobs.example.com/1").mock(return_value=httpx.Response(200, text=page))
        post = import_from_url("https://jobs.example.com/1", company="Example Corp")
    assert "Python" in post.jd_text
    assert "<p>" not in post.jd_text
    assert post.source == "manual"
    assert post.title == "Backend Engineer"
