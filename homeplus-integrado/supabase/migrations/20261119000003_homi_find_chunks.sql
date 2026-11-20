-- T18 FIND REAL — hybrid retrieval index
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
SET search_path = public, extensions;
CREATE SCHEMA IF NOT EXISTS find;

CREATE TABLE IF NOT EXISTS find.find_chunks (
    chunk_id            TEXT PRIMARY KEY,
    household_id        TEXT NOT NULL,
    document_id         TEXT NOT NULL,
    document_version    INTEGER NOT NULL,
    owner_id            TEXT NOT NULL,
    visibility          TEXT NOT NULL,
    sensitivity         TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    asset_id            TEXT,
    mime_type           TEXT NOT NULL,
    section             TEXT,
    chunk_index         INTEGER NOT NULL,
    text                TEXT NOT NULL,
    token_estimate      INTEGER NOT NULL DEFAULT 0,
    content_hash        TEXT NOT NULL,
    pipeline_version    TEXT NOT NULL,
    chunk_config_version TEXT NOT NULL,
    parser_version      TEXT,
    title               TEXT,
    permissions         JSONB NOT NULL DEFAULT '{}'::jsonb,
    restrictions        JSONB NOT NULL DEFAULT '[]'::jsonb,
    category            TEXT,
    updated_at          TIMESTAMPTZ,
    embedding           vector(1024),
    tsv                 tsvector,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    embedding_model      TEXT NOT NULL,
    embedding_version   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_find_chunks_household ON find.find_chunks (household_id);
CREATE INDEX IF NOT EXISTS idx_find_chunks_document ON find.find_chunks (document_id, document_version);
CREATE INDEX IF NOT EXISTS idx_find_chunks_active ON find.find_chunks (active);
CREATE INDEX IF NOT EXISTS idx_find_chunks_owner ON find.find_chunks (owner_id);
CREATE INDEX IF NOT EXISTS idx_find_chunks_visibility ON find.find_chunks (visibility);

-- pgvector index (cosine). For small volumes HNSW is fine.
CREATE INDEX IF NOT EXISTS idx_find_chunks_embedding ON find.find_chunks
    USING hnsw (embedding vector_cosine_ops);

-- FTS index
CREATE INDEX IF NOT EXISTS idx_find_chunks_tsv ON find.find_chunks USING gin (tsv);

-- trigger to maintain tsv (Spanish-ish: use 'simple' to preserve codes/product names; can switch to 'spanish')
CREATE OR REPLACE FUNCTION find.find_chunks_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('simple', coalesce(NEW.title, '') || ' ' || NEW.text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_find_chunks_tsv'
          AND tgrelid = 'find.find_chunks'::regclass
    ) THEN
        CREATE TRIGGER trg_find_chunks_tsv
            BEFORE INSERT OR UPDATE ON find.find_chunks
            FOR EACH ROW EXECUTE FUNCTION find.find_chunks_tsv_update();
    END IF;
END;
$$;
