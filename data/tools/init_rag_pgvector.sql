CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id TEXT PRIMARY KEY,
    text_content TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_file TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding vector NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_source_file ON rag_documents (source_file);
CREATE INDEX IF NOT EXISTS idx_rag_documents_metadata ON rag_documents USING GIN (metadata);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rag_documents_updated_at ON rag_documents;
CREATE TRIGGER trg_rag_documents_updated_at
BEFORE UPDATE ON rag_documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
