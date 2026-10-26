import inspect
import uuid
from datetime import UTC, datetime

import httpx
import respx

from job_agent.agents import email_finder
from job_agent.agents.email_finder import find_contacts, pattern_guesses
from job_agent.records import StoredJob


def _job(**meta):
    return StoredJob(
        job_id=uuid.uuid4(), company="Example Corp", title="Backend Engineer",
        source="manual", url="https://jobs.example.com/1",
        jd_text="Must have: Python.", posted_at=None, metadata=meta,
        created_at=datetime.now(UTC),
    )


def test_page_email_is_unverified():
    page = "<p>Email recruiting@example.com about the role.</p>"
    with respx.mock:
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, text=page))
        found = find_contacts(_job(website="https://example.com"), max_contacts=3)
    assert found
    assert all(c.verified is False for c in found)
    assert found[0].email == "recruiting@example.com"
    assert found[0].source == "public_page"
    assert found[0].confidence > 0.4


def test_pattern_guess_when_pages_fail():
    with respx.mock:
        respx.get(url__regex=r".*").mock(return_value=httpx.Response(404, text="nope"))
        found = find_contacts(_job(), max_contacts=3, retries=1)
    assert found
    assert all(c.verified is False for c in found)
    assert all(c.source == "pattern_guess" for c in found)
    assert all(c.email and c.email.endswith("@example.com") for c in found)
    guesses = pattern_guesses("Example Corp")
    assert guesses[0].confidence < 0.5


def test_module_does_not_send():
    src = inspect.getsource(email_finder)
    assert "smtplib" not in src
    assert "apollo" not in src.lower()
    assert not hasattr(email_finder, "send_outreach_email")
