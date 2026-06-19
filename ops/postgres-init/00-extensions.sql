-- Runs once on first init of the self-hosted Postgres data dir (--profile localdb).
-- Enables pgvector so the tender_embeddings vector column + ivfflat index work.
CREATE EXTENSION IF NOT EXISTS vector;
