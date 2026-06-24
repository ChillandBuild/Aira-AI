# Embeddings Service

> 15 nodes · cohesion 0.23

## Key Concepts

- **_semantic_search()** (7 connections) — `backend/app/services/knowledge_service.py`
- **embeddings.py** (6 connections) — `backend/app/services/embeddings.py`
- **_call_jina()** (6 connections) — `backend/app/services/embeddings.py`
- **embed_texts()** (6 connections) — `backend/app/services/embeddings.py`
- **embed_query()** (6 connections) — `backend/app/services/embeddings.py`
- **to_pgvector()** (6 connections) — `backend/app/services/embeddings.py`
- **EmbeddingError** (4 connections) — `backend/app/services/embeddings.py`
- **str** (4 connections) — `backend/app/services/embeddings.py`
- **float** (4 connections) — `backend/app/services/embeddings.py`
- **Raised when the embedding provider is unavailable or returns a bad shape.** (1 connections) — `backend/app/services/embeddings.py`
- **Embed a batch of documents/chunks. Splits into provider-safe batches.** (1 connections) — `backend/app/services/embeddings.py`
- **Embed a single search query (query task tunes for asymmetric retrieval).** (1 connections) — `backend/app/services/embeddings.py`
- **Serialize a float list to a pgvector literal string for ::vector casts.** (1 connections) — `backend/app/services/embeddings.py`
- **Vector similarity via Jina embeddings + match_knowledge_chunks RPC.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Vector similarity via Jina embeddings + match_knowledge_chunks RPC.** (1 connections) — `backend/app/services/knowledge_service.py`

## Relationships

- [[Knowledge Base (pgvector RAG)]] (5 shared connections)
- [[Config]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/services/embeddings.py`
- `backend/app/services/knowledge_service.py`

## Audit Trail

- EXTRACTED: 49 (89%)
- INFERRED: 6 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*