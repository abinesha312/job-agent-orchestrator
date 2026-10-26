import math

import pytest

from job_agent.config import Settings
from job_agent.embeddings import Embedder, FakeEmbedder, get_embedder
from job_agent.embeddings.litellm_embedder import LiteLLMEmbedder


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_embedder_deterministic_and_normalised():
    e = FakeEmbedder(dim=768)
    a1, a2 = e.embed(["Python FastAPI"]), FakeEmbedder(768).embed(["Python FastAPI"])
    assert a1 == a2
    assert len(a1[0]) == 768
    assert math.isclose(math.sqrt(sum(v * v for v in a1[0])), 1.0, rel_tol=1e-9)
    assert isinstance(e, Embedder)


def test_fake_embedder_similarity_is_lexical():
    e = FakeEmbedder(dim=768)
    q, near, far = e.embed(["python fastapi postgres", "fastapi python services", "watercolor painting"])
    assert cos(q, near) > cos(q, far)


def test_factory_selects_backend_without_calling_apis():
    assert isinstance(get_embedder(Settings(embedding_backend="fake")), FakeEmbedder)
    lit = get_embedder(Settings(embedding_backend="litellm"))
    assert isinstance(lit, LiteLLMEmbedder) and lit.model.startswith("gemini/")
    with pytest.raises(ValueError):
        get_embedder(Settings(embedding_backend="nope"))
