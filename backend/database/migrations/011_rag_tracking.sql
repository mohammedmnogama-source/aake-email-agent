-- Migration 011: RAG tracking
-- Adds rag_indexed column to emails table.
-- 0 = not yet indexed to ChromaDB
-- 1 = indexed (safe to skip on future backfill runs)

ALTER TABLE emails ADD COLUMN rag_indexed INTEGER NOT NULL DEFAULT 0;
