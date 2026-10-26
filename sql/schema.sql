-- Generated reference DDL: `alembic upgrade head --sql`. Alembic (alembic/versions) is the source of truth.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE jobs (
    job_id UUID NOT NULL, 
    company VARCHAR(255) NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    source VARCHAR(32) NOT NULL, 
    url TEXT NOT NULL, 
    jd_text TEXT NOT NULL, 
    jd_embedding VECTOR(768), 
    posted_at TIMESTAMP WITH TIME ZONE, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (job_id), 
    UNIQUE (url)
);

CREATE INDEX ix_jobs_jd_embedding_hnsw ON jobs USING hnsw (jd_embedding vector_cosine_ops);

CREATE TABLE resume_versions (
    version_id UUID NOT NULL, 
    resume_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    parent_id UUID, 
    job_id UUID, 
    file_path TEXT NOT NULL, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (version_id), 
    CONSTRAINT uq_resume_versions_resume_version UNIQUE (resume_id, version), 
    FOREIGN KEY(parent_id) REFERENCES resume_versions (version_id) ON DELETE SET NULL, 
    FOREIGN KEY(job_id) REFERENCES jobs (job_id) ON DELETE SET NULL
);

CREATE INDEX ix_resume_versions_resume_id ON resume_versions (resume_id);

CREATE TABLE resume_chunks (
    id UUID NOT NULL, 
    resume_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    section VARCHAR(64) NOT NULL, 
    chunk_order INTEGER NOT NULL, 
    text TEXT NOT NULL, 
    embedding VECTOR(768), 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_resume_chunks_resume_version ON resume_chunks (resume_id, version);

CREATE INDEX ix_resume_chunks_embedding_hnsw ON resume_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE matches (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    resume_version UUID NOT NULL, 
    match_score FLOAT NOT NULL, 
    missing_skills TEXT[] DEFAULT '{}' NOT NULL, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_matches_job_version UNIQUE (job_id, resume_version), 
    FOREIGN KEY(job_id) REFERENCES jobs (job_id) ON DELETE CASCADE, 
    FOREIGN KEY(resume_version) REFERENCES resume_versions (version_id) ON DELETE CASCADE
);

CREATE TYPE application_status AS ENUM ('discovered', 'matched', 'tailored', 'awaiting_approval', 'approved', 'applied', 'rejected');

CREATE TABLE applications (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    status application_status DEFAULT 'discovered' NOT NULL, 
    approved_by_user BOOLEAN DEFAULT false NOT NULL, 
    applied_at TIMESTAMP WITH TIME ZONE, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_applications_approval_required CHECK (status NOT IN ('approved', 'applied') OR approved_by_user = true), 
    FOREIGN KEY(job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
);

CREATE INDEX ix_applications_job_id ON applications (job_id);

CREATE TABLE contacts (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    title VARCHAR(255), 
    email VARCHAR(320), 
    source VARCHAR(32) DEFAULT 'apollo' NOT NULL, 
    verified BOOLEAN DEFAULT false NOT NULL, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
);

CREATE INDEX ix_contacts_job_id ON contacts (job_id);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

COMMIT;

