-- Database initialization script
-- This creates the database if it doesn't exist

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for better performance on text searches
-- These will be applied after table creation

CREATE TYPE subscriptiontier AS ENUM ('FREE', 'STARTER', 'PRO', 'BUSINESS');
CREATE TYPE providertype AS ENUM ('VEO3', 'SORA2', 'KLING');
CREATE TYPE jobstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED');
CREATE TYPE transactiontype AS ENUM ('CREDIT_PURCHASE', 'VIDEO_GENERATION', 'REFUND', 'BONUS');
