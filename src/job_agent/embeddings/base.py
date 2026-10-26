from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Anything that turns a batch of strings into fixed-width float vectors."""

    dim: int
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...
