from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from urllib import request
from urllib.error import URLError

from app.core.config import get_settings
from app.core.exceptions import AppError


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _embed_ollama_subprocess(model: str, text: str, expected_dim: int) -> list[float]:
    """Call ollama CLI via subprocess (most reliable for local ollama)."""
    result = subprocess.run(
        ["ollama", "run", model, text],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise AppError(2101, f"ollama subprocess failed: {result.stderr[:200]}", 502)
    # Parse the output: it's a JSON array like [-0.01, 0.02, ...]
    stdout = result.stdout.strip()
    vector = json.loads(stdout)
    if not isinstance(vector, list) or len(vector) != expected_dim:
        raise ValueError(
            f"embedding dimension mismatch: expected {expected_dim}, "
            f"got {len(vector) if isinstance(vector, list) else type(vector)}"
        )
    return [float(v) for v in vector]


def embed_text(text: str) -> list[float]:
    settings = get_settings()
    if settings.embedding_base_url and settings.embedding_api_key:
        try:
            if settings.embedding_provider == "ollama-local":
                return _embed_ollama_subprocess(
                    settings.embedding_model,
                    text,
                    settings.embedding_dim,
                )
            return _embed_openai_compatible(
                settings.embedding_base_url,
                settings.embedding_api_key,
                settings.embedding_model,
                text,
                settings.embedding_dim,
            )
        except (URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
            raise AppError(2101, "embedding service unavailable or returned invalid vector", 502) from exc
    return _embed_local_hash(text, settings.embedding_dim)


def embedding_provider() -> str:
    settings = get_settings()
    if settings.embedding_base_url and settings.embedding_api_key:
        return settings.embedding_provider or "external"
    return "local_hash"


def _embed_openai_compatible(base_url: str, api_key: str, model: str, text: str, expected_dim: int) -> list[float]:
    url = base_url.rstrip("/") + "/embeddings"
    body = json.dumps({"model": model, "input": text}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    vector = payload["data"][0]["embedding"]
    if len(vector) != expected_dim:
        raise ValueError(f"embedding dimension mismatch: expected {expected_dim}, got {len(vector)}")
    return [float(value) for value in vector]


def _embed_local_hash(text: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    tokens = TOKEN_RE.findall(text.lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
