from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from job_agent.agents.company_sources import COMPANIES, fetch_amazon, fetch_openai, search_companies
from job_agent.api.app import create_app
from job_agent.config import Settings


@pytest.fixture()
def client(tmp_path):
    settings = Settings(database_url="", run_log_path=tmp_path / "r.jsonl", upload_dir=tmp_path,
                        history_path=tmp_path / "h.json")
    return TestClient(create_app(settings=settings))


def test_lists_the_six_companies(client):
    body = client.get("/companies").json()
    assert [c["id"] for c in body["companies"]] == ["amd", "apple", "microsoft", "amazon", "openai", "anthropic"]
    assert len(COMPANIES) == 6


def test_unknown_company_rejected(client):
    r = client.post("/companies/search", json={"companies": ["nope"], "query": "x"})
    assert r.status_code == 400


@respx.mock
def test_amazon_uses_one_company_name_and_keeps_entity():
    respx.get("https://www.amazon.jobs/en/search.json").mock(return_value=httpx.Response(200, json={"jobs": [{
        "title": "Software Development Engineer", "company_name": "Amazon Web Services, Inc.",
        "description": "Build large distributed systems for customers around the world.",
        "basic_qualifications": "3+ years of professional software development", "job_path": "/en/jobs/1/x",
        "id_icims": "1", "normalized_location": "Seattle, Washington, USA",
    }]}))
    [post] = fetch_amazon("sde", limit=5, retries=1)
    assert post.company == "Amazon" and post.metadata["entity"] == "Amazon Web Services, Inc."
    assert post.url == "https://www.amazon.jobs/en/jobs/1/x"


@respx.mock
def test_openai_is_filtered_by_query_and_named():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/openai").mock(return_value=httpx.Response(200, json={"jobs": [
        {"title": "Research Engineer", "descriptionPlain": "Work on frontier models and training systems.",
         "jobUrl": "https://jobs.ashbyhq.com/openai/1", "id": "1"},
        {"title": "Recruiter", "descriptionPlain": "Hire great people for the company worldwide.",
         "jobUrl": "https://jobs.ashbyhq.com/openai/2", "id": "2"},
    ]}))
    posts = fetch_openai("engineer", limit=10, retries=1)
    assert [p.title for p in posts] == ["Research Engineer"] and posts[0].company == "OpenAI"


@respx.mock
def test_one_company_failing_keeps_the_rest():
    respx.get("https://careers.amd.com/api/jobs").mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    respx.get("https://api.ashbyhq.com/posting-api/job-board/openai").mock(return_value=httpx.Response(200, json={"jobs": [
        {"title": "Engineer", "descriptionPlain": "Build and ship reliable systems at scale.",
         "jobUrl": "https://jobs.ashbyhq.com/openai/9", "id": "9"}]}))
    found, errors = search_companies(["amd", "openai"], "engineer", retries=1)
    assert len(found) == 1 and len(errors) == 1 and errors[0].startswith("amd:")
