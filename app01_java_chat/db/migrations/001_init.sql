-- CodeFixer AI — Phase 1 schema. Applied once at container start by the
-- `db-init` one-shot service in docker-compose.yml (psql -f, idempotent via
-- IF NOT EXISTS / ON CONFLICT DO NOTHING).

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL DEFAULT 'New conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    reasoning_tokens TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx ON chat_messages(session_id);

-- KPI-02 (Mean Time to Resolution) telemetry — one row per LLM provider call.
CREATE TABLE IF NOT EXISTS llm_call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    provider VARCHAR(64) NOT NULL,      -- 'openrouter/hermes-3' | 'openai/codex'
    model VARCHAR(128) NOT NULL,
    latency_ms INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- KPI-01 (Fix Accuracy Ratio) telemetry — one row per Worker execution.
CREATE TABLE IF NOT EXISTS code_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    language VARCHAR(32) NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    timed_out BOOLEAN NOT NULL DEFAULT false,
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- US-04 audit trail — one row per failover event.
CREATE TABLE IF NOT EXISTS failover_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    from_provider VARCHAR(64) NOT NULL,
    to_provider VARCHAR(64) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phase 1 demo user. Password hash below is a real bcrypt("demo1234", cost=12)
-- hash, generated directly (not fabricated) — a publicly-known dev-only
-- credential, never use in any real deployment. Override at seed time via a
-- real ADMIN_PASSWORD_HASH if you deploy this anywhere reachable.
INSERT INTO users (username, password_hash)
VALUES ('demo', '$2b$12$khulzHoI0ySYaC0boXpMuO6ek52b6pB/CG/KYpqmTELNfzv9UAvzy')
ON CONFLICT (username) DO NOTHING;
