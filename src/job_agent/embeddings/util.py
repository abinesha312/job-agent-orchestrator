from __future__ import annotations

import math
import time
from collections.abc import Callable

from job_agent.embeddings.base import Embedder
from job_agent.errors import LlmFailure


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def embed_texts(
    embedder: Embedder,
    texts: list[str],
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    if not texts:
        return []
    delay = 0.05
    vecs: list[list[float]] | None = None
    for attempt in range(1, attempts + 1):
        try:
            vecs = embedder.embed(texts)
            break
        except Exception as exc:
            if attempt >= attempts:
                raise LlmFailure(f"embedder failed: {exc}") from exc
            sleep(delay)
            delay *= 2
    if vecs is None or len(vecs) != len(texts):
        raise LlmFailure(f"embedder returned {0 if vecs is None else len(vecs)} vectors for {len(texts)} texts")
    dim = getattr(embedder, "dim", None)
    if dim is not None:
        for vec in vecs:
            if len(vec) != dim:
                raise LlmFailure(f"embedding dim {len(vec)} != {dim}")
    return vecs
