# Investment Research Platform MVP

## Database

The local database `investment_research_mvp` has been verified with:

- `uuid-ossp`
- `pg_trgm`
- `vector`
- 15 tables
- 82 indexes

Run schema verification:

```bash
psql -d investment_research_mvp -f scripts/verify_schema.sql
```

## Backend

Install dependencies:

```bash
python3 -m pip install -e .
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/system/info
```

## Implemented Scope

P0:

- Health check
- System info
- Company create/list/detail
- Document upload
- Document ingest for TXT/Markdown/CSV/JSON/HTML/PDF/DOCX files
- Document list/detail/chunks/preview/delete
- Hybrid retrieval using PostgreSQL trigram matching and pgvector similarity
- Synchronous QA with LLM answers, task execution, and persisted citations
- Task create/list/detail/runs

P1:

- Tags and document/asset tag binding
- Minimal Agent/Skill routing endpoint
- Structured memo generation endpoint with research asset persistence
- Structured daily report endpoint with research asset persistence
- Research asset save/list/detail/update/revisions/export
- Prompt template list/create

## Current Parser Limit

The current implementation supports text-like files plus PDF and DOCX through `pymupdf` and `python-docx`.
Production use still needs larger real-document regression coverage for tables, scanned PDFs, and noisy layouts.

## Smoke Test

Run the API smoke test against the local database:

```bash
python3 scripts/smoke_api.py
```

The script verifies TXT, DOCX, and PDF ingest, chunk creation, search, QA task execution, persisted citations, Agent routing, memo/daily asset generation, asset export, and the unified `{code, message, data}` response envelope.

## Retrieval Evaluation

Run a small retrieval quality check against curated JSONL cases:

```bash
python3 scripts/eval_retrieval.py --cases evals/retrieval_cases.jsonl
```

Each case defines a query and expected keywords that should appear in the top-k retrieved chunks. Use this after changing embedding, chunking, or reranking logic.
