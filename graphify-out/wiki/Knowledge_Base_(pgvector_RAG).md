# Knowledge Base (pgvector RAG)

> 24 nodes · cohesion 0.15

## Key Concepts

- **get_knowledge_context()** (14 connections) — `backend/app/services/knowledge_service.py`
- **knowledge_service.py** (13 connections) — `backend/app/services/knowledge_service.py`
- **str** (10 connections) — `backend/app/services/knowledge_service.py`
- **_index_chunks()** (10 connections) — `backend/app/services/knowledge_service.py`
- **reindex_tenant()** (8 connections) — `backend/app/services/knowledge_service.py`
- **process_document()** (6 connections) — `backend/app/services/knowledge_service.py`
- **_full_text_context()** (5 connections) — `backend/app/services/knowledge_service.py`
- **_keyword_search()** (5 connections) — `backend/app/services/knowledge_service.py`
- **_chunk_text()** (4 connections) — `backend/app/services/knowledge_service.py`
- **UUID** (4 connections) — `backend/app/services/knowledge_service.py`
- **extract_text_from_file()** (4 connections) — `backend/app/services/knowledge_service.py`
- **_format_excerpts()** (3 connections) — `backend/app/services/knowledge_service.py`
- **bytes** (2 connections) — `backend/app/services/knowledge_service.py`
- **Split text into overlapping windows, preferring paragraph/sentence boundaries.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Chunk → embed → replace this document's chunks. Returns chunk count.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Legacy full-text injection — used as the embedding-failure fallback.     Campaig** (1 connections) — `backend/app/services/knowledge_service.py`
- **Postgres full-text + trigram match — no external API, language-agnostic tokens.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Retrieve the most relevant knowledge-base excerpts for this tenant's message.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Re-chunk + embed every indexed document for a tenant (backfill for pre-RAG docs)** (1 connections) — `backend/app/services/knowledge_service.py`
- **Legacy full-text injection — used as the embedding-failure fallback.     Campaig** (1 connections) — `backend/app/services/knowledge_service.py`
- **Postgres full-text + trigram match — no external API, language-agnostic tokens.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Retrieve the most relevant knowledge-base excerpts for this tenant's message.** (1 connections) — `backend/app/services/knowledge_service.py`
- **Re-chunk + embed every indexed document for a tenant (backfill for pre-RAG docs)** (1 connections) — `backend/app/services/knowledge_service.py`
- **Return full text of all indexed documents for this tenant, ready to inject into** (1 connections) — `backend/app/services/knowledge_service.py`

## Relationships

- [[Embeddings Service]] (5 shared connections)
- [[Operator Console & Audit]] (3 shared connections)
- [[Config]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)
- [[Templates API]] (1 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Knowledge API]] (1 shared connections)

## Source Files

- `backend/app/services/knowledge_service.py`

## Audit Trail

- EXTRACTED: 89 (90%)
- INFERRED: 10 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*