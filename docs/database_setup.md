# Database Setup

## Local verification result

Verified on PostgreSQL 18.4 with Homebrew `pgvector` 0.8.2.

- Extensions: `uuid-ossp`, `vector`, `pg_trgm`
- Tables: 15
- Indexes: 82
- Vector column: `document_chunks.embedding vector`
- Vector index: `idx_document_chunks_embedding` using `ivfflat (embedding vector_cosine_ops)`

The `ivfflat index created with little data` message during schema creation is a PostgreSQL notice from pgvector when indexing an empty table. It is not a schema creation failure.

## Commands

Install pgvector if PostgreSQL cannot see the `vector` extension:

```bash
brew install pgvector
```

Create a clean local database:

```bash
createdb investment_research_mvp
```

Apply the schema:

```bash
psql -d investment_research_mvp -v ON_ERROR_STOP=1 -f "06第一期数据库建表SQL初稿.sql"
```

Verify extensions, table count, vector column, and indexes:

```bash
psql -d investment_research_mvp -f scripts/verify_schema.sql
```

## Notes

The first failed attempt before pgvector was installed created only 13 tables because `document_chunks` failed on `VECTOR(1024)`, and `citations` then failed because it references `document_chunks`.
