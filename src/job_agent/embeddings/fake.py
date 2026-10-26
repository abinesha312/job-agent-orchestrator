"""Deterministic, offline embedder for tests and local dev.

Uses signed feature hashing of lower-cased word tokens, L2-normalised. Same input ->
same vector on every machine, and texts sharing words get positive cosine similarity,
so retrieval tests are meaningful without any API key. Not a semantic model.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


class FakeEmbedder:
    name = "fake-hash"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]
