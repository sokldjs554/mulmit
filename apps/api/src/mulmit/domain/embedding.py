"""Text embeddings behind a tiny interface.

* ``HashingEmbedder`` — deterministic signed feature hashing over hangul character n-grams plus
  taxonomy keywords. No network, no model download; good enough to cluster "스마트쉘터 설치" with
  "스마트 버스정류장 조성" and to make the demo and tests hermetic.
* ``VoyageEmbedder`` — Voyage AI (``voyage-3.5``, multilingual, Matryoshka dims) for production.

Both return L2-normalised vectors of ``dim`` so pgvector's cosine operator works the same.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Literal, Protocol

import httpx

from mulmit.domain.taxonomy import CATEGORIES
from mulmit.domain.text import char_ngrams, hangul_tokens

InputType = Literal["document", "query"]


class Embedder(Protocol):
    dim: int
    name: str

    async def embed(
        self, texts: Sequence[str], *, input_type: InputType = "document"
    ) -> list[list[float]]: ...


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


_KEYWORD_WEIGHTS = {
    kw.replace(" ", ""): 3.0 for info in CATEGORIES.values() for kw in info.keywords
}


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "big") % self.dim
        sign = 1.0 if digest[4] & 1 else -1.0
        return idx, sign

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        features: list[tuple[str, float]] = []
        features += [(f"2:{g}", 1.0) for g in char_ngrams(text, 2)]
        features += [(f"3:{g}", 1.5) for g in char_ngrams(text, 3)]
        features += [(f"w:{t}", 2.0) for t in hangul_tokens(text)]
        compact = text.replace(" ", "")
        features += [(f"k:{kw}", w) for kw, w in _KEYWORD_WEIGHTS.items() if kw and kw in compact]
        for feature, weight in features:
            idx, sign = self._bucket(feature)
            vec[idx] += sign * weight
        return _l2(vec)

    async def embed(
        self, texts: Sequence[str], *, input_type: InputType = "document"
    ) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class VoyageEmbedder:
    """https://docs.voyageai.com/reference/embeddings-api"""

    def __init__(
        self, api_key: str, *, model: str = "voyage-3.5", dim: int = 512, timeout: float = 30.0
    ) -> None:
        self.name = f"voyage:{model}:{dim}"
        self.dim = dim
        self._model = model
        self._client = httpx.AsyncClient(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def embed(
        self, texts: Sequence[str], *, input_type: InputType = "document"
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            batch = list(texts[i : i + 128])
            resp = await self._client.post(
                "/embeddings",
                json={
                    "input": batch,
                    "model": self._model,
                    "input_type": input_type,
                    "output_dimension": self.dim,
                },
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out += [_l2([float(x) for x in d["embedding"]]) for d in data]
        return out
