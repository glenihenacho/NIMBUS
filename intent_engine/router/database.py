"""
Database client for the router service.

Handles connections to Postgres for operational reads/writes.
"""

import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from ..models.intent_models import (
    Session,
    IntentDecision,
    InferenceRun,
    RiskLevel
)


class DatabaseClient:
    """Async Postgres client for router operations"""

    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or "postgresql://user:password@localhost:5432/intent_engine"
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        print(f"✓ Database pool created")

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("✓ Database pool closed")

    async def get_or_create_session(
        self,
        session_id: str,
        event_count: int,
        user_id_hash: str = "unknown"
    ) -> Session:
        """Get existing session or create new one"""
        async with self.pool.acquire() as conn:
            # Try to fetch existing
            row = await conn.fetchrow(
                """
                SELECT session_id, user_id_hash, event_count, current_sequence,
                       value_score, risk_level, created_at, updated_at
                FROM sessions
                WHERE session_id = $1
                """,
                session_id
            )

            if row:
                # Update event count
                await conn.execute(
                    """
                    UPDATE sessions
                    SET event_count = event_count + $2,
                        updated_at = NOW()
                    WHERE session_id = $1
                    """,
                    session_id,
                    event_count
                )

                return Session(
                    session_id=row['session_id'],
                    user_id_hash=row['user_id_hash'],
                    event_count=row['event_count'] + event_count,
                    current_sequence=row['current_sequence'],
                    value_score=float(row['value_score']),
                    risk_level=RiskLevel(row['risk_level']),
                    created_at=row['created_at'],
                    updated_at=datetime.utcnow()
                )
            else:
                # Create new session
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, user_id_hash, event_count)
                    VALUES ($1, $2, $3)
                    """,
                    session_id,
                    user_id_hash,
                    event_count
                )

                return Session(
                    session_id=session_id,
                    user_id_hash=user_id_hash,
                    event_count=event_count,
                    current_sequence=0,
                    value_score=0.0,
                    risk_level=RiskLevel.LOW
                )

    async def write_decision(
        self,
        decision: IntentDecision,
        inference_runs: List[InferenceRun]
    ):
        """Write intent decision and associated inference runs"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Insert decision
                await conn.execute(
                    """
                    INSERT INTO intent_decisions (
                        decision_id, session_id, intent, confidence, was_escalated,
                        model_used, gating_should_escalate, gating_reason,
                        gating_cheap_confidence, gating_top2_margin, gating_risk_level,
                        gating_high_value_session, source_event_ids, policy_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    decision.decision_id,
                    decision.session_id,
                    decision.intent.value,
                    decision.confidence,
                    decision.was_escalated,
                    decision.model_used.value,
                    decision.gating_decision.should_escalate,
                    decision.gating_decision.reason,
                    decision.gating_decision.cheap_confidence,
                    decision.gating_decision.top2_margin,
                    decision.gating_decision.risk_level.value,
                    decision.gating_decision.high_value_session,
                    [str(eid) for eid in decision.source_event_ids],
                    "1.0.0"
                )

                # Insert inference runs
                for run in inference_runs:
                    await conn.execute(
                        """
                        INSERT INTO inference_runs (
                            run_id, decision_id, model_id, input_event_count,
                            output, latency_ms, success, error_message
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        run.run_id,
                        decision.decision_id,
                        run.model_id.value,
                        run.input_event_count,
                        run.output,
                        run.latency_ms,
                        run.success,
                        run.error_message
                    )

    async def get_escalation_rate(self, window_hours: int = 1) -> float:
        """Get escalation rate for the past N hours"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN was_escalated THEN 1 ELSE 0 END) as escalated
                FROM intent_decisions
                WHERE created_at >= NOW() - INTERVAL '1 hour' * $1
                """,
                window_hours
            )

            if row and row['total'] > 0:
                return float(row['escalated']) / float(row['total'])
            return 0.0

    async def get_stats(self) -> Dict[str, Any]:
        """Get current statistics for monitoring"""
        async with self.pool.acquire() as conn:
            # Last hour stats
            stats_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_decisions,
                    SUM(CASE WHEN was_escalated THEN 1 ELSE 0 END) as escalated_count,
                    AVG(confidence) as avg_confidence,
                    COUNT(DISTINCT session_id) as unique_sessions
                FROM intent_decisions
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                """
            )

            # Model latency
            latency_rows = await conn.fetch(
                """
                SELECT
                    model_id,
                    AVG(latency_ms) as avg_latency,
                    MAX(latency_ms) as max_latency,
                    COUNT(*) as run_count
                FROM inference_runs
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                  AND success = true
                GROUP BY model_id
                """
            )

            return {
                "last_hour": {
                    "total_decisions": stats_row['total_decisions'],
                    "escalated_count": stats_row['escalated_count'],
                    "escalation_rate": round(
                        float(stats_row['escalated_count']) / float(stats_row['total_decisions']),
                        3
                    ) if stats_row['total_decisions'] > 0 else 0,
                    "avg_confidence": round(float(stats_row['avg_confidence']), 3) if stats_row['avg_confidence'] else 0,
                    "unique_sessions": stats_row['unique_sessions']
                },
                "model_latency": [
                    {
                        "model": row['model_id'],
                        "avg_latency_ms": round(float(row['avg_latency']), 2),
                        "max_latency_ms": round(float(row['max_latency']), 2),
                        "run_count": row['run_count']
                    }
                    for row in latency_rows
                ],
                "timestamp": datetime.utcnow().isoformat()
            }
