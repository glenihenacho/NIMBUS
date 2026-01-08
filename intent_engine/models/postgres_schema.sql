-- Intent Detection Engine - Postgres Operational Schema
--
-- Purpose: Fast operational reads for routing, session state, and recent features
-- Complement: BigQuery for immutable analytics lake

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For text search if needed

-- Sessions table (operational state)
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id_hash VARCHAR(64) NOT NULL,
    event_count INTEGER DEFAULT 0,
    current_sequence INTEGER DEFAULT 0,
    value_score DECIMAL(5,3) DEFAULT 0.0,
    risk_level VARCHAR(20) DEFAULT 'LOW' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_sessions_user_hash (user_id_hash),
    INDEX idx_sessions_updated (updated_at DESC)
);

-- Intent decisions table (final decisions used by product)
CREATE TABLE IF NOT EXISTS intent_decisions (
    decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id),
    intent VARCHAR(50) NOT NULL CHECK (intent IN (
        'PURCHASE_INTENT',
        'RESEARCH_INTENT',
        'COMPARISON_INTENT',
        'ENGAGEMENT_INTENT',
        'NAVIGATION_INTENT',
        'UNKNOWN'
    )),
    confidence DECIMAL(5,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    was_escalated BOOLEAN NOT NULL,
    model_used VARCHAR(50) NOT NULL,

    -- Gating decision details
    gating_should_escalate BOOLEAN NOT NULL,
    gating_reason TEXT,
    gating_cheap_confidence DECIMAL(5,3),
    gating_top2_margin DECIMAL(5,3),
    gating_risk_level VARCHAR(20),
    gating_high_value_session BOOLEAN,

    -- Metadata
    source_event_ids UUID[] DEFAULT '{}',
    policy_version VARCHAR(20) DEFAULT '1.0.0',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_decisions_session (session_id),
    INDEX idx_decisions_intent (intent),
    INDEX idx_decisions_created (created_at DESC),
    INDEX idx_decisions_escalated (was_escalated, created_at DESC)
);

-- Inference runs table (each model run, linked to decision)
CREATE TABLE IF NOT EXISTS inference_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    decision_id UUID NOT NULL REFERENCES intent_decisions(decision_id),
    model_id VARCHAR(50) NOT NULL CHECK (model_id IN (
        'rasa',
        'mistral-small',
        'deepseek-reasoning'
    )),
    input_event_count INTEGER NOT NULL,
    output JSONB NOT NULL, -- Serialized classifier/escalation output
    latency_ms DECIMAL(10,2) NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    INDEX idx_runs_decision (decision_id),
    INDEX idx_runs_model (model_id, created_at DESC),
    INDEX idx_runs_latency (model_id, latency_ms),
    INDEX idx_runs_errors (success, created_at DESC) WHERE success = false
);

-- Rate limits table (optional, for throttling)
CREATE TABLE IF NOT EXISTS rate_limits (
    key VARCHAR(255) PRIMARY KEY, -- e.g., "session:{session_id}:deepseek:hour"
    count INTEGER DEFAULT 0,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_rate_limits_expires (expires_at)
);

-- Escalation counters (track escalation patterns)
CREATE TABLE IF NOT EXISTS escalation_counters (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    hour_bucket TIMESTAMP WITH TIME ZONE NOT NULL, -- Truncated to hour
    escalation_count INTEGER DEFAULT 0,
    total_inferences INTEGER DEFAULT 0,

    UNIQUE(session_id, hour_bucket),
    INDEX idx_escalation_session (session_id, hour_bucket DESC)
);

-- Model performance cache (for monitoring)
CREATE TABLE IF NOT EXISTS model_performance (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    total_runs INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_latency_ms DECIMAL(10,2),
    p95_latency_ms DECIMAL(10,2),
    p99_latency_ms DECIMAL(10,2),

    UNIQUE(model_id, date),
    INDEX idx_perf_model_date (model_id, date DESC)
);

-- Intent distribution (for drift detection)
CREATE TABLE IF NOT EXISTS intent_distribution (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour < 24),
    intent VARCHAR(50) NOT NULL,
    count INTEGER DEFAULT 0,

    UNIQUE(date, hour, intent),
    INDEX idx_dist_date_hour (date DESC, hour DESC)
);

-- Functions

-- Update session timestamp on changes
CREATE OR REPLACE FUNCTION update_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_session_timestamp();

-- Materialized view for recent high-confidence decisions
CREATE MATERIALIZED VIEW IF NOT EXISTS recent_high_confidence_decisions AS
SELECT
    decision_id,
    session_id,
    intent,
    confidence,
    was_escalated,
    created_at
FROM intent_decisions
WHERE confidence >= 0.85
  AND created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;

CREATE UNIQUE INDEX ON recent_high_confidence_decisions (decision_id);
CREATE INDEX ON recent_high_confidence_decisions (intent, created_at DESC);

-- Refresh function (call periodically via cron or trigger)
CREATE OR REPLACE FUNCTION refresh_recent_decisions()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY recent_high_confidence_decisions;
END;
$$ LANGUAGE plpgsql;

-- View for escalation rate by session
CREATE VIEW escalation_rate_by_session AS
SELECT
    session_id,
    COUNT(*) as total_decisions,
    SUM(CASE WHEN was_escalated THEN 1 ELSE 0 END) as escalated_count,
    ROUND(
        SUM(CASE WHEN was_escalated THEN 1 ELSE 0 END)::numeric /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as escalation_rate_pct
FROM intent_decisions
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY session_id
HAVING COUNT(*) >= 3
ORDER BY escalation_rate_pct DESC;

-- View for model latency statistics
CREATE VIEW model_latency_stats AS
SELECT
    model_id,
    COUNT(*) as total_runs,
    ROUND(AVG(latency_ms), 2) as avg_latency_ms,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms), 2) as p50_latency_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 2) as p95_latency_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms), 2) as p99_latency_ms,
    ROUND(MIN(latency_ms), 2) as min_latency_ms,
    ROUND(MAX(latency_ms), 2) as max_latency_ms
FROM inference_runs
WHERE created_at >= NOW() - INTERVAL '1 hour'
  AND success = true
GROUP BY model_id;

-- Comments
COMMENT ON TABLE sessions IS 'Session operational state for routing decisions';
COMMENT ON TABLE intent_decisions IS 'Final intent decisions used by product';
COMMENT ON TABLE inference_runs IS 'Individual model inference runs for auditing';
COMMENT ON TABLE rate_limits IS 'Rate limiting for expensive operations';
COMMENT ON TABLE escalation_counters IS 'Track escalation patterns for optimization';
COMMENT ON TABLE model_performance IS 'Daily model performance aggregates';
COMMENT ON TABLE intent_distribution IS 'Hourly intent distribution for drift detection';

-- Cleanup old data (retention policy)
-- Run this via cron: DELETE FROM inference_runs WHERE created_at < NOW() - INTERVAL '30 days';
-- Run this via cron: DELETE FROM intent_decisions WHERE created_at < NOW() - INTERVAL '90 days';
