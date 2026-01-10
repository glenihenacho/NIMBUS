"""
FastAPI Intent Detection Router

Single entry point for all inference per HANDOFF_intent_detection_engine.md.

Architecture:
- Cheap classifier: Rasa Open Source + Mistral-small (hybrid)
- Gating policy: Escalate when uncertain
- Escalation: DeepSeek reasoning (expensive, gated)
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .llm_clients import HybridClassifier, DeepSeekClient, GatingPolicy
from .schema import BrowserEvent, IntentInference

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PAT Intent Detection Router",
    description="Hybrid intent detection: Rasa + Mistral + DeepSeek",
    version="1.0.0"
)

# Initialize clients (Rasa + Mistral hybrid, DeepSeek escalation)
hybrid_classifier: Optional[HybridClassifier] = None
deepseek_client: Optional[DeepSeekClient] = None
gating_policy: Optional[GatingPolicy] = None


class InferRequest(BaseModel):
    """Request for intent inference."""
    session_id: str
    user_id: str
    events: list[dict]
    session_value: Optional[float] = None


class InferResponse(BaseModel):
    """Response from intent inference."""
    decision_id: str
    final_intent: str
    confidence: float
    supporting_signals: list[str]
    alternatives: list[dict]
    recommended_action: str
    model_id: str
    policy_version: str
    latency_ms: int
    escalated: bool
    escalation_reason: Optional[str]


@app.on_event("startup")
async def startup():
    """Initialize clients on startup."""
    global hybrid_classifier, deepseek_client, gating_policy

    hybrid_classifier = HybridClassifier()
    deepseek_client = DeepSeekClient()
    gating_policy = GatingPolicy()

    logger.info("Intent router started - Hybrid (Rasa+Mistral) + DeepSeek initialized")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if hybrid_classifier:
        await hybrid_classifier.close()
    if deepseek_client:
        await deepseek_client.close()

    logger.info("Intent router stopped")


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.post("/api/infer/intent", response_model=InferResponse)
async def infer_intent(request: InferRequest, background_tasks: BackgroundTasks):
    """
    Main inference endpoint per HANDOFF_intent_detection_engine.md.

    Flow:
    1. Run hybrid classifier (Rasa + Mistral)
    2. Apply gating policy
    3. Escalate to DeepSeek if needed
    4. Return decision with metadata
    """
    decision_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Step 1: Hybrid classification (Rasa + Mistral)
        cheap_result = await hybrid_classifier.classify(request.events)

        top_intent = cheap_result.get("top_intent", "NAVIGATION_INTENT")
        confidence = cheap_result.get("confidence", 0.5)
        scores = cheap_result.get("scores", {})
        classifier_used = cheap_result.get("classifier", "hybrid")

        # Step 2: Gating policy
        should_escalate, reason = gating_policy.should_escalate(
            intent=top_intent,
            confidence=confidence,
            scores=scores,
            session_value=request.session_value
        )

        # Step 3: Escalate if needed
        if should_escalate:
            logger.info(f"Escalating to DeepSeek: {reason}")
            final_result = await deepseek_client.reason(request.events, cheap_result)
            model_used = final_result.get("model", "deepseek-reasoning")
            final_intent = final_result.get("final_intent", top_intent)
            final_confidence = final_result.get("confidence", confidence)
            alternatives = final_result.get("alternatives", [])
        else:
            model_used = classifier_used
            final_intent = top_intent
            final_confidence = confidence
            alternatives = [
                {"intent": k, "confidence": v}
                for k, v in scores.items()
                if k != final_intent
            ][:3]  # Top 3 alternatives

        latency_ms = int((time.time() - start_time) * 1000)

        # Extract supporting signal IDs
        supporting_signals = [
            e.get("event_id", f"event_{i}")
            for i, e in enumerate(request.events)
        ]

        # Determine recommended action
        recommended_action = _determine_action(final_intent, final_confidence)

        response = InferResponse(
            decision_id=decision_id,
            final_intent=final_intent,
            confidence=round(final_confidence, 3),
            supporting_signals=supporting_signals,
            alternatives=alternatives,
            recommended_action=recommended_action,
            model_id=model_used,
            policy_version="1.0",
            latency_ms=latency_ms,
            escalated=should_escalate,
            escalation_reason=reason
        )

        # Background task: Write to storage (BigQuery + Postgres)
        background_tasks.add_task(
            _write_decision,
            decision_id=decision_id,
            response=response,
            request=request
        )

        return response

    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _determine_action(intent: str, confidence: float) -> str:
    """Determine recommended action based on intent and confidence."""
    if confidence >= 0.70:
        return "create_segment"
    elif confidence >= 0.50:
        return "collect_more_signals"
    else:
        return "discard"


def _write_decision(decision_id: str, response: InferResponse, request: InferRequest):
    """
    Write decision to storage (sync background task).

    Note: Using sync function for BackgroundTasks compatibility.
    In production: Write to BigQuery (audit) + Postgres (operational)
    """
    import json

    logger.info(f"Recording decision {decision_id}: {response.final_intent} ({response.confidence})")

    # Prepare record for storage
    record = {
        "decision_id": decision_id,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "final_intent": response.final_intent,
        "confidence": response.confidence,
        "model_id": response.model_id,
        "escalated": response.escalated,
        "escalation_reason": response.escalation_reason,
        "latency_ms": response.latency_ms,
        "event_count": len(request.events),
        "timestamp": datetime.utcnow().isoformat()
    }

    # Production implementation would:
    # 1. Write to BigQuery: pat_events.inference_runs (audit trail)
    # 2. Write to Postgres: intent_decisions (operational)
    #
    # Example BigQuery write:
    # from google.cloud import bigquery
    # client = bigquery.Client()
    # table_id = "pat_events.inference_runs"
    # client.insert_rows_json(table_id, [record])
    #
    # Example Postgres write:
    # from sqlalchemy import create_engine
    # engine.execute(intent_decisions.insert().values(**record))

    logger.debug(f"Decision record: {json.dumps(record)}")


# CLI entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
