-- FitnessOS Database Initialization Script
-- Run once when the database is first created.

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Optimize pgvector for cosine similarity
-- This index type is used for the embedding similarity search in the memory system
-- (created by Alembic after models are applied)
