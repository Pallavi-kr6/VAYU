-- supabase.sql
-- ─────────────────────────────────────────────────────────
-- VAYU — Supabase schema
-- Run in Supabase Dashboard → SQL Editor (or via supabase db push)
-- ─────────────────────────────────────────────────────────

-- Enable UUID extension (optional, for future use)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Agent cache (mirrors in-memory IntelligenceBus) ───────
CREATE TABLE IF NOT EXISTS agent_cache (
    key         TEXT PRIMARY KEY,
    data        JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_cache_updated
    ON agent_cache (updated_at DESC);

-- ── Live AQI reading history ──────────────────────────────
CREATE TABLE IF NOT EXISTS city_readings (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT NOT NULL,
    pm25        REAL,
    pm10        REAL,
    aqi         INT,
    pollutants  JSONB DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_city_readings_city_time
    ON city_readings (city, recorded_at DESC);

-- ── Chatbot / WhatsApp conversation logs ──────────────────
CREATE TABLE IF NOT EXISTS chat_logs (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT,
    phone       TEXT,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    message     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_logs_city_time
    ON chat_logs (city, created_at DESC);

-- ── Enforcement polluter registry ─────────────────────────
CREATE TABLE IF NOT EXISTS polluters (
    id          TEXT PRIMARY KEY,
    city        TEXT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('industrial', 'construction', 'vehicle', 'biomass')),
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    violations  INT NOT NULL DEFAULT 0,
    last_check  DATE
);

CREATE INDEX IF NOT EXISTS idx_polluters_city
    ON polluters (city);

-- ── Seed polluter data (shared across cities for demo) ────
INSERT INTO polluters (id, city, name, type, lat, lon, violations, last_check) VALUES
    ('IND001', NULL, 'Bharat Steel Rolling Mill',       'industrial',   28.63, 77.21, 3, '2025-11-10'),
    ('CON001', NULL, 'Apex Infrastructure Site A',      'construction', 28.61, 77.19, 1, '2025-12-01'),
    ('CON002', NULL, 'DDA Housing Project Sector 9',    'construction', 28.65, 77.22, 2, '2025-10-15'),
    ('VEH001', NULL, 'Old Diesel Bus Depot Anand Vihar','vehicle',      28.64, 77.32, 5, '2025-09-20'),
    ('BIO001', NULL, 'Unauthorized Waste Burning Site', 'biomass',      28.58, 77.25, 4, '2025-11-28')
ON CONFLICT (id) DO NOTHING;

-- ── Row Level Security (backend uses service role key) ────
ALTER TABLE agent_cache   ENABLE ROW LEVEL SECURITY;
ALTER TABLE city_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_logs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE polluters     ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS; anon read policies for dashboard (optional)
CREATE POLICY "anon_read_agent_cache" ON agent_cache
    FOR SELECT TO anon USING (true);

CREATE POLICY "anon_read_city_readings" ON city_readings
    FOR SELECT TO anon USING (true);

CREATE POLICY "anon_read_polluters" ON polluters
    FOR SELECT TO anon USING (true);
