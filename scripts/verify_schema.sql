\set ON_ERROR_STOP on

WITH required_extensions(extname) AS (
    VALUES ('uuid-ossp'), ('vector'), ('pg_trgm')
),
installed_extensions AS (
    SELECT extname, extversion
    FROM pg_extension
    WHERE extname IN (SELECT extname FROM required_extensions)
)
SELECT
    r.extname,
    i.extversion,
    CASE WHEN i.extname IS NULL THEN 'missing' ELSE 'ok' END AS status
FROM required_extensions r
LEFT JOIN installed_extensions i ON i.extname = r.extname
ORDER BY r.extname;

SELECT
    COUNT(*) AS table_count,
    CASE WHEN COUNT(*) = 15 THEN 'ok' ELSE 'unexpected' END AS status
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

SELECT
    column_name,
    udt_name,
    CASE WHEN udt_name = 'vector' THEN 'ok' ELSE 'unexpected' END AS status
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'document_chunks'
  AND column_name = 'embedding';

SELECT
    COUNT(*) AS index_count,
    CASE WHEN COUNT(*) >= 82 THEN 'ok' ELSE 'unexpected' END AS status
FROM pg_indexes
WHERE schemaname = 'public';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
      'idx_company_basic_info_short_name',
      'idx_documents_title_trgm',
      'idx_document_chunks_embedding',
      'idx_citations_task_citation_no'
  )
ORDER BY indexname;
