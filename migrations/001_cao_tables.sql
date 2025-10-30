CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cao_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID,
    cao_name TEXT NOT NULL,
    article_number TEXT NOT NULL,
    title TEXT,
    full_text TEXT NOT NULL,
    processing_status TEXT DEFAULT 'parsed',
    processing_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cao_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES cao_articles(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    start_position INTEGER,
    end_position INTEGER,
    token_count INTEGER,
    chunk_reasoning TEXT,
    embedding vector(1024),
    embedding_model TEXT DEFAULT 'voyage-law-2',
    embedding_input TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(article_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS cao_chunk_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES cao_chunks(id) ON DELETE CASCADE,
    analysis_data JSONB NOT NULL,
    reasoning_trace TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chunk_id)
);

CREATE TABLE IF NOT EXISTS cao_article_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_article_id UUID REFERENCES cao_articles(id) ON DELETE CASCADE,
    target_article_number TEXT NOT NULL,
    reference_type TEXT NOT NULL,
    context TEXT,
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON cao_articles(processing_status);
CREATE INDEX IF NOT EXISTS idx_articles_cao ON cao_articles(cao_name);
CREATE INDEX IF NOT EXISTS idx_chunks_article ON cao_chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_analysis_chunk ON cao_chunk_analysis(chunk_id);
CREATE INDEX IF NOT EXISTS idx_analysis_themes ON cao_chunk_analysis USING gin ((analysis_data->'themes'));
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON cao_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
