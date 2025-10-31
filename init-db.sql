-- Database initialization script
-- This creates the database if it doesn't exist

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for better performance on text searches
-- These will be applied after table creation