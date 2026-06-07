CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'researcher',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_basic_info (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_code VARCHAR(32) NOT NULL UNIQUE,
    company_name VARCHAR(128) NOT NULL,
    company_short_name VARCHAR(128),
    exchange VARCHAR(32),
    market VARCHAR(32),
    industry_code_l1 VARCHAR(32),
    industry_name_l1 VARCHAR(128),
    industry_code_l2 VARCHAR(32),
    industry_name_l2 VARCHAR(128),
    security_type VARCHAR(32),
    list_date DATE,
    delist_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id VARCHAR(128) NOT NULL UNIQUE,
    title VARCHAR(512) NOT NULL,
    doc_type VARCHAR(32) NOT NULL,
    source VARCHAR(128),
    company_id UUID REFERENCES company_basic_info(id),
    company_code VARCHAR(32),
    company_name VARCHAR(128),
    industry VARCHAR(128),
    publish_date DATE,
    permission_level VARCHAR(16) NOT NULL DEFAULT 'internal',
    file_name VARCHAR(256) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size BIGINT,
    checksum VARCHAR(128),
    parent_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    document_version VARCHAR(32) NOT NULL DEFAULT '1.0',
    is_latest BOOLEAN NOT NULL DEFAULT TRUE,
    parse_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    parse_error TEXT,
    parse_retry_count INT NOT NULL DEFAULT 0,
    parse_strategy_version VARCHAR(32),
    ingested_by UUID REFERENCES users(id),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id VARCHAR(128) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    content_type VARCHAR(32) NOT NULL DEFAULT 'paragraph',
    page_no INT,
    position_start INT,
    position_end INT,
    char_start INT,
    char_end INT,
    section_title VARCHAR(256),
    section_path TEXT,
    token_count INT,
    summary_text TEXT,
    keyword_text TEXT,
    keywords_json JSONB,
    entities_json JSONB,
    metadata_json JSONB,
    is_important BOOLEAN NOT NULL DEFAULT FALSE,
    embedding_model VARCHAR(128),
    embedding VECTOR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_document_chunks_doc_chunk UNIQUE (document_id, chunk_id),
    CONSTRAINT uq_document_chunks_doc_index UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tag_code VARCHAR(64) NOT NULL UNIQUE,
    tag_name VARCHAR(128) NOT NULL,
    tag_type VARCHAR(32) NOT NULL,
    parent_id UUID REFERENCES tags(id) ON DELETE SET NULL,
    description TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (document_id, tag_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_type VARCHAR(32) NOT NULL,
    task_title VARCHAR(256),
    input_text TEXT,
    input_payload JSONB,
    output_payload JSONB,
    result_summary TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    priority VARCHAR(16) NOT NULL DEFAULT 'normal',
    route_agent VARCHAR(64),
    callback_url TEXT,
    request_id VARCHAR(128),
    created_by UUID REFERENCES users(id),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_type VARCHAR(16) NOT NULL,
    run_name VARCHAR(128) NOT NULL,
    input_payload JSONB,
    output_payload JSONB,
    status VARCHAR(16) NOT NULL,
    duration_ms INT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_type VARCHAR(32) NOT NULL,
    title VARCHAR(512) NOT NULL,
    content_markdown TEXT NOT NULL,
    summary TEXT,
    company_id UUID REFERENCES company_basic_info(id),
    company_code VARCHAR(32),
    industry VARCHAR(128),
    parent_asset_id UUID REFERENCES research_assets(id) ON DELETE SET NULL,
    root_asset_id UUID REFERENCES research_assets(id) ON DELETE SET NULL,
    version INT NOT NULL DEFAULT 1,
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset_revisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID NOT NULL REFERENCES research_assets(id) ON DELETE CASCADE,
    version INT NOT NULL,
    content_markdown TEXT NOT NULL,
    summary TEXT,
    updated_by UUID REFERENCES users(id),
    change_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_asset_revisions_asset_version UNIQUE (asset_id, version)
);

CREATE TABLE IF NOT EXISTS asset_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID NOT NULL REFERENCES research_assets(id) ON DELETE CASCADE,
    source_type VARCHAR(16) NOT NULL,
    source_ref_id UUID NOT NULL,
    source_id_text VARCHAR(128),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_asset_tags (
    asset_id UUID NOT NULL REFERENCES research_assets(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset_id, tag_id)
);

CREATE TABLE IF NOT EXISTS citations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES research_assets(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    citation_no INT NOT NULL,
    source_id VARCHAR(128) NOT NULL,
    page_no INT,
    position_start INT,
    position_end INT,
    quote_text TEXT,
    rank INT,
    relevance_score NUMERIC(6, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_key VARCHAR(128) NOT NULL UNIQUE,
    template_name VARCHAR(128) NOT NULL,
    agent_name VARCHAR(64),
    scenario VARCHAR(64),
    content TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(128) NOT NULL UNIQUE,
    config_group VARCHAR(64),
    config_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- P2 indexes: company fuzzy search and metadata filters. Can be moved to a later migration if initial writes are slow.
CREATE INDEX IF NOT EXISTS idx_company_basic_info_short_name
    ON company_basic_info USING gin (company_short_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_company_basic_info_industry_l1
    ON company_basic_info (industry_code_l1);

CREATE INDEX IF NOT EXISTS idx_company_basic_info_is_active
    ON company_basic_info (is_active);

-- P0 indexes: document list, ingest status, and retrieval filters.
CREATE INDEX IF NOT EXISTS idx_documents_doc_type
    ON documents (doc_type);

CREATE INDEX IF NOT EXISTS idx_documents_company_id
    ON documents (company_id);

CREATE INDEX IF NOT EXISTS idx_documents_company_code
    ON documents (company_code);

CREATE INDEX IF NOT EXISTS idx_documents_publish_date
    ON documents (publish_date);

CREATE INDEX IF NOT EXISTS idx_documents_parse_status
    ON documents (parse_status);

-- P2 indexes: source, version chain, compound filters, and fuzzy title search.
CREATE INDEX IF NOT EXISTS idx_documents_source
    ON documents (source);

CREATE INDEX IF NOT EXISTS idx_documents_checksum
    ON documents (checksum);

CREATE INDEX IF NOT EXISTS idx_documents_parent_document_id
    ON documents (parent_document_id);

CREATE INDEX IF NOT EXISTS idx_documents_is_latest
    ON documents (is_latest)
    WHERE is_latest = TRUE;

CREATE INDEX IF NOT EXISTS idx_documents_company_doc_type_publish
    ON documents (company_code, doc_type, publish_date DESC);

CREATE INDEX IF NOT EXISTS idx_documents_doc_type_parse_status
    ON documents (doc_type, parse_status);

CREATE INDEX IF NOT EXISTS idx_documents_title_trgm
    ON documents USING gin (title gin_trgm_ops);

-- P0 indexes: chunk lookup by document and stable chunk order.
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON document_chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index
    ON document_chunks (chunk_index);

-- P2 indexes: chunk debugging filters, entity search, keyword fuzzy search, and vector ANN.
CREATE INDEX IF NOT EXISTS idx_document_chunks_page_no
    ON document_chunks (page_no);

CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type
    ON document_chunks (content_type);

CREATE INDEX IF NOT EXISTS idx_document_chunks_is_important
    ON document_chunks (is_important);

CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_page_chunk
    ON document_chunks (document_id, page_no, chunk_index);

CREATE INDEX IF NOT EXISTS idx_document_chunks_entities_json
    ON document_chunks USING gin (entities_json);

CREATE INDEX IF NOT EXISTS idx_document_chunks_keyword_text_trgm
    ON document_chunks USING gin (keyword_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- P2 indexes: tag management and tag tree filtering.
CREATE INDEX IF NOT EXISTS idx_tags_tag_type
    ON tags (tag_type);

CREATE INDEX IF NOT EXISTS idx_tags_parent_id
    ON tags (parent_id);

CREATE INDEX IF NOT EXISTS idx_tags_status
    ON tags (status);

CREATE INDEX IF NOT EXISTS idx_document_tags_tag_id
    ON document_tags (tag_id);

-- P0 indexes: task status, timeline, and request tracing.
CREATE INDEX IF NOT EXISTS idx_tasks_task_type
    ON tasks (task_type);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks (status);

CREATE INDEX IF NOT EXISTS idx_tasks_route_agent
    ON tasks (route_agent);

CREATE INDEX IF NOT EXISTS idx_tasks_created_by
    ON tasks (created_by);

CREATE INDEX IF NOT EXISTS idx_tasks_created_at
    ON tasks (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_request_id
    ON tasks (request_id);

-- P2 index: compound task dashboard query.
CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at
    ON tasks (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_runs_task_id
    ON task_runs (task_id);

CREATE INDEX IF NOT EXISTS idx_task_runs_run_type
    ON task_runs (run_type);

-- P0 indexes: asset list and detail filters.
CREATE INDEX IF NOT EXISTS idx_research_assets_asset_type
    ON research_assets (asset_type);

CREATE INDEX IF NOT EXISTS idx_research_assets_company_id
    ON research_assets (company_id);

CREATE INDEX IF NOT EXISTS idx_research_assets_company_code
    ON research_assets (company_code);

CREATE INDEX IF NOT EXISTS idx_research_assets_status
    ON research_assets (status);

CREATE INDEX IF NOT EXISTS idx_research_assets_created_at
    ON research_assets (created_at DESC);

-- P2 indexes: asset relationship and compound filters.
CREATE INDEX IF NOT EXISTS idx_research_assets_parent_asset_id
    ON research_assets (parent_asset_id);

CREATE INDEX IF NOT EXISTS idx_research_assets_root_asset_id
    ON research_assets (root_asset_id);

CREATE INDEX IF NOT EXISTS idx_research_assets_company_asset_created
    ON research_assets (company_code, asset_type, created_at DESC);

-- P2 indexes: version history and asset source/tag relations.
CREATE INDEX IF NOT EXISTS idx_asset_revisions_asset_id
    ON asset_revisions (asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_sources_asset_id
    ON asset_sources (asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_sources_source_type
    ON asset_sources (source_type);

CREATE INDEX IF NOT EXISTS idx_research_asset_tags_tag_id
    ON research_asset_tags (tag_id);

-- P0 indexes: citation lookup by task, asset, document, and source.
CREATE INDEX IF NOT EXISTS idx_citations_task_id
    ON citations (task_id);

CREATE INDEX IF NOT EXISTS idx_citations_asset_id
    ON citations (asset_id);

CREATE INDEX IF NOT EXISTS idx_citations_document_id
    ON citations (document_id);

CREATE INDEX IF NOT EXISTS idx_citations_source_id
    ON citations (source_id);

CREATE INDEX IF NOT EXISTS idx_citations_task_citation_no
    ON citations (task_id, citation_no);

CREATE INDEX IF NOT EXISTS idx_citations_asset_citation_no
    ON citations (asset_id, citation_no);

-- P2 indexes: prompt and config management filters.
CREATE INDEX IF NOT EXISTS idx_prompt_templates_agent_name
    ON prompt_templates (agent_name);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_scenario
    ON prompt_templates (scenario);

CREATE INDEX IF NOT EXISTS idx_system_configs_group
    ON system_configs (config_group);
