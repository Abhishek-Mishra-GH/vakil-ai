-- VakilAI -- Full multi-tenant schema
-- Safe to re-run in development.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    bar_council_id  TEXT,
    phone           TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    case_number     TEXT,
    court_name      TEXT,
    court_number    TEXT,
    opposing_party  TEXT,
    hearing_date    TIMESTAMPTZ,
    hearing_time    TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('active', 'closed', 'adjourned'))
);

CREATE TABLE IF NOT EXISTS documents (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_id              UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    filename             TEXT NOT NULL,
    original_filename    TEXT NOT NULL,
    file_url             TEXT NOT NULL,
    cloudinary_public_id TEXT,
    processing_status    TEXT NOT NULL DEFAULT 'pending',
    processing_error     TEXT,
    page_count           INTEGER,
    detected_language    TEXT NOT NULL DEFAULT 'en',
    was_translated       BOOLEAN NOT NULL DEFAULT FALSE,
    ocr_confidence_avg   FLOAT,
    clause_count         INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        processing_status IN (
            'pending', 'ocr_running', 'chunking', 'embedding', 'analyzing', 'ready', 'failed'
        )
    )
);

CREATE TABLE IF NOT EXISTS chunks (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_id          UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content          TEXT NOT NULL,
    content_original TEXT,
    page_number      INTEGER NOT NULL,
    bbox_x0          FLOAT,
    bbox_y0          FLOAT,
    bbox_x1          FLOAT,
    bbox_y1          FLOAT,
    chunk_index      INTEGER NOT NULL,
    section_header   TEXT,
    embedding        vector(1536),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS insights (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clause_type         TEXT NOT NULL,
    summary             TEXT NOT NULL,
    anomaly_flag        TEXT NOT NULL,
    anomaly_reason      TEXT,
    statutory_reference TEXT,
    statutory_id        TEXT,
    page_number         INTEGER NOT NULL,
    bbox_x0             FLOAT,
    bbox_y0             FLOAT,
    bbox_x1             FLOAT,
    bbox_y1             FLOAT,
    source_chunk_id     UUID REFERENCES chunks(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (anomaly_flag IN ('HIGH_RISK', 'MEDIUM_RISK', 'STANDARD'))
);

CREATE TABLE IF NOT EXISTS contradictions (
    id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id   UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_a_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    doc_b_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    claim_a   TEXT NOT NULL,
    claim_b   TEXT NOT NULL,
    page_a    INTEGER,
    page_b    INTEGER,
    bbox_x0_a FLOAT,
    bbox_y0_a FLOAT,
    bbox_x1_a FLOAT,
    bbox_y1_a FLOAT,
    bbox_x0_b FLOAT,
    bbox_y0_b FLOAT,
    bbox_x1_b FLOAT,
    bbox_y1_b FLOAT,
    severity  TEXT NOT NULL,
    explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (severity IN ('HIGH', 'MEDIUM'))
);

CREATE TABLE IF NOT EXISTS hearing_briefs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id             UUID NOT NULL UNIQUE REFERENCES cases(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    core_contention     TEXT NOT NULL,
    timeline            JSONB NOT NULL DEFAULT '[]'::jsonb,
    offensive_arguments JSONB NOT NULL DEFAULT '[]'::jsonb,
    defensive_arguments JSONB NOT NULL DEFAULT '[]'::jsonb,
    weak_points         JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_legal_issues    JSONB NOT NULL DEFAULT '[]'::jsonb,
    precedents          JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    documents_used      JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS moot_sessions (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id        UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'active',
    exchange_count INTEGER NOT NULL DEFAULT 0,
    summary        JSONB,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at       TIMESTAMPTZ,
    CHECK (status IN ('active', 'ended'))
);

CREATE TABLE IF NOT EXISTS moot_messages (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id     UUID NOT NULL REFERENCES moot_sessions(id) ON DELETE CASCADE,
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    weak_point_hit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (role IN ('user', 'assistant'))
);

CREATE TABLE IF NOT EXISTS qa_sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qa_messages (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id       UUID NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    retrieved_chunks JSONB,
    cannot_determine BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_hearing_date ON cases(hearing_date);

CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);

CREATE INDEX IF NOT EXISTS idx_chunks_case_id ON chunks(case_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_fts
    ON chunks USING GIN (to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_insights_document_id ON insights(document_id);
CREATE INDEX IF NOT EXISTS idx_insights_case_id ON insights(case_id);
CREATE INDEX IF NOT EXISTS idx_insights_anomaly_flag ON insights(anomaly_flag);

CREATE INDEX IF NOT EXISTS idx_contradictions_case_id ON contradictions(case_id);

CREATE INDEX IF NOT EXISTS idx_moot_messages_session_id ON moot_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_qa_messages_session_id ON qa_messages(session_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases;
CREATE TRIGGER trg_cases_updated_at
BEFORE UPDATE ON cases
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
