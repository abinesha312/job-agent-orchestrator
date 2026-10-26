"""LiteLLM-backed embedder. Default model: Gemini (``gemini/gemini-embedding-001``).

Requires the ``llm`` extra (``pip install -e .[llm]``) and credentials in the
environment (``GEMINI_API_KEY``, or Vertex AI via ``vertex_ai/...`` models with
``VERTEXAI_PROJECT``/``VERTEXAI_LOCATION``). Not exercised by the test suite.
"""

from __future__ import annotations


class LiteLLMEmbedder:
    def __init__(self, model: str = "gemini/gemini-embedding-001", dim: int = 768,
                 batch_size: int = 64) -> None:
        self.model = model
        self.dim = dim
        self.name = f"litellm:{model}"
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("LiteLLM not installed: pip install -e '.[llm]'") from exc

        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # `dimensions` maps to Gemini's output_dimensionality so vectors fit vector(768).
            resp = litellm.embedding(model=self.model, input=batch, dimensions=self.dim)
            for item in resp.data:
                emb = item["embedding"] if isinstance(item, dict) else item.embedding
                if len(emb) != self.dim:
                    raise ValueError(
                        f"{self.model} returned dim {len(emb)}, expected {self.dim}; "
                        "set EMBEDDING_DIM and the migration's vector width to match"
                    )
                out.append(list(emb))
        return out
