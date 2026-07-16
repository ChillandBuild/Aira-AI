import logging

import httpx

from app.config_dynamic import require_tenant_setting

logger = logging.getLogger(__name__)

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_MODEL = "jina-embeddings-v3"
EMBED_DIM = 512  # Matryoshka-truncated; matches knowledge_chunks.embedding vector(512)
_MAX_BATCH = 100

# Jina task types tune the embedding for its role (asymmetric retrieval).
_TASK_DOCUMENT = "retrieval.passage"
_TASK_QUERY = "retrieval.query"


class EmbeddingError(RuntimeError):
    """Raised when the embedding provider is unavailable or returns a bad shape."""


async def _call_jina(inputs: list[str], task: str, tenant_id: str | None) -> list[list[float]]:
    """No fallback to a platform key -- every client gets their own jina_api_key, same
    policy as every other AI provider (operator decision, see decisions/log.md)."""
    try:
        api_key = require_tenant_setting("jina_api_key", tenant_id)
    except RuntimeError as e:
        raise EmbeddingError(str(e)) from e
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "task": task,
        "dimensions": EMBED_DIM,
        "input": inputs,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_JINA_URL, headers=headers, json=payload)
    if resp.status_code != 200:
        raise EmbeddingError(f"Jina {resp.status_code}: {resp.text[:300]}")
    rows = (resp.json() or {}).get("data") or []
    ordered = sorted(rows, key=lambda r: r.get("index", 0))
    vectors = [r["embedding"] for r in ordered]
    if len(vectors) != len(inputs):
        raise EmbeddingError(f"Jina returned {len(vectors)} vectors for {len(inputs)} inputs")
    # Guard against silent dim drift — the DB column is vector(512), so a wrong-dim vector
    # would fail every insert and mask RAG behind the full-text fallback.
    bad = next((len(v) for v in vectors if len(v) != EMBED_DIM), None)
    if bad is not None:
        raise EmbeddingError(f"Jina returned dim {bad}, expected {EMBED_DIM} — check model/dimensions")
    return vectors


async def embed_texts(texts: list[str], input_type: str = "document", tenant_id: str | None = None) -> list[list[float]]:
    """Embed a batch of documents/chunks. Splits into provider-safe batches."""
    clean = [t for t in (s.strip() for s in texts) if t]
    if not clean:
        return []
    task = _TASK_QUERY if input_type == "query" else _TASK_DOCUMENT
    out: list[list[float]] = []
    for i in range(0, len(clean), _MAX_BATCH):
        out.extend(await _call_jina(clean[i : i + _MAX_BATCH], task, tenant_id))
    return out


async def embed_query(text: str, tenant_id: str | None = None) -> list[float]:
    """Embed a single search query (query task tunes for asymmetric retrieval)."""
    vectors = await _call_jina([text.strip()], _TASK_QUERY, tenant_id)
    return vectors[0]


def to_pgvector(embedding: list[float]) -> str:
    """Serialize a float list to a pgvector literal string for ::vector casts."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"
