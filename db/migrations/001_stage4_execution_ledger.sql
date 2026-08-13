-- Readable Stage 4 execution-ledger contract.
-- LangGraph owns workflow checkpoints; this table only claims side effects.

CREATE TABLE IF NOT EXISTS inbox2action_execution_ledger (
    idempotency_key VARCHAR(64) PRIMARY KEY,
    thread_id VARCHAR(30) NOT NULL,
    action_id VARCHAR(128) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('claimed', 'executing', 'succeeded', 'failed', 'unknown')),
    error_code VARCHAR(64),
    attempt_count BIGINT NOT NULL CHECK (attempt_count >= 1),
    claimed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
