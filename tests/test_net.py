import httpx
import pytest
import respx

from job_agent.agents.job_discovery import fetch_greenhouse
from job_agent.embeddings.util import embed_texts
from job_agent.errors import HttpFailure, LlmFailure
from job_agent.net import request


def test_retries_then_succeeds():
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
    with respx.mock:
        route = respx.get(url).mock(side_effect=[
            httpx.Response(503, text="busy"),
            httpx.Response(200, json={"jobs": []}),
        ])
        posts = fetch_greenhouse("example", sleep=lambda _s: None, retries=3)
    assert posts == []
    assert route.call_count == 2


def test_404_does_not_retry():
    url = "https://example.test/missing"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(404, text="no"))
        try:
            request("GET", url, retries=4, sleep=lambda _s: None)
            raised = False
        except HttpFailure as exc:
            raised = True
            assert exc.retryable is False
            assert exc.status == 404
    assert raised
    assert route.call_count == 1


def test_embed_retries_then_raises():
    class Boom:
        name = "boom"
        dim = 4

        def embed(self, texts):
            raise RuntimeError("down")

    with pytest.raises(LlmFailure):
        embed_texts(Boom(), ["hi"], attempts=2, sleep=lambda _s: None)
