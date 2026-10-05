-- Migration: 002_add_document_metadata.sql
-- Description: Add metadata columns for real-time live ingestion to documents and images tables.
-- Safe, non-destructive forward migration using ADD COLUMN IF NOT EXISTS.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_count INT NOT NULL DEFAULT 0;

ALTER TABLE images ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE images ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE images ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100);
ALTER TABLE images ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'completed';
ALTER TABLE images ADD COLUMN IF NOT EXISTS chunk_count INT NOT NULL DEFAULT 0;

-- Indexes for content_hash lookup to support duplicate detection and idempotency
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_images_content_hash ON images(content_hash);
