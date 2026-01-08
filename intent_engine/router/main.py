"""
Intent Detection Router Service - FastAPI Application

This is the single entry point for all intent detection inference decisions.
It orchestrates cheap classifiers, gating policy, and escalation to long-chain reasoning.
"""

import time
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
import asyncio

from ..models.intent_models import (
    InferenceRequest,
    InferenceResponse,
    IntentDecision,
    InferenceRun,
    ClassifierOutput,
    ModelType,
    Session,
    BrowsingEvent,
    GatingConfig
)
from .gating import GatingPolicy, get_balanced_policy
from ..classifiers.rasa_classifier import RasaClassifier
from ..classifiers.mistral_classifier import MistralClassifier
from ..escalation.deepseek_reasoner import DeepSeekReasoner
from .database import DatabaseClient


# FastAPI app
app = FastAPI(
    title="Intent Detection Router",
    description="Router service for intent classification with confidence-based escalation",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

INFERENCE_REQUESTS = Counter(
    'intent_inference_requests_total',
    'Total number of inference requests',
    ['status']
)

INFERENCE_LATENCY = Histogram(
    'intent_inference_latency_seconds',
    'Inference latency in seconds',
    ['model', 'escalated'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ESCALATION_RATE = Gauge(
    'intent_escalation_rate',
    'Current escalation rate'
)

MODEL_ERRORS = Counter(
    'intent_model_errors_total',
    'Total number of model errors',
    ['model']
)

GATING_REASONS = Counter(
    'intent_gating_reasons_total',
    'Gating decision reasons',
    ['reason_type']
)


# Global state (in production, use dependency injection)
class RouterState:
    def __init__(self):
        self.db_client: Optional[DatabaseClient] = None
        self.rasa_classifier: Optional[RasaClassifier] = None
        self.mistral_classifier: Optional[MistralClassifier] = None
        self.deepseek_reasoner: Optional[DeepSeekReasoner] = None
        self.gating_policy: GatingPolicy = get_balanced_policy()


state = RouterState()


@app.on_event("startup")
async def startup():
    """Initialize all components on startup"""
    # Initialize database client
    state.db_client = DatabaseClient()
    await state.db_client.connect()

    # Initialize classifiers
    state.rasa_classifier = RasaClassifier()
    state.mistral_classifier = MistralClassifier()
    state.deepseek_reasoner = DeepSeekReasoner()

    # Initialize gating policy
    gating_config = GatingConfig()  # Load from config file in production
    state.gating_policy = GatingPolicy(gating_config)

    print("✓ Router service initialized")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    if state.db_client:
        await state.db_client.disconnect()
    print("✓ Router service shutdown")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": state.db_client is not None,
            "rasa": state.rasa_classifier is not None,
            "mistral": state.mistral_classifier is not None,
            "deepseek": state.deepseek_reasoner is not None
        }
    }


@app.post("/infer", response_model=InferenceResponse)
async def infer_intent(request: InferenceRequest) -> InferenceResponse:
    """
    Main inference endpoint.

    Process flow:
    1. Fetch/update session state
    2. Run cheap classifier (Rasa primary, Mistral as scorer)
    3. Apply gating policy
    4. Escalate to DeepSeek if needed
    5. Record decision and inference runs
    6. Return structured response
    """
    start_time = time.time()
    inference_runs: List[InferenceRun] = []

    try:
        # Step 1: Fetch or create session
        session = await state.db_client.get_or_create_session(
            session_id=request.session_id,
            event_count=len(request.events)
        )

        # Step 2: Run cheap classifier
        # Primary: Rasa (for known patterns)
        rasa_start = time.time()
        try:
            rasa_output = await state.rasa_classifier.classify(request.events)
            rasa_latency = (time.time() - rasa_start) * 1000

            inference_runs.append(InferenceRun(
                decision_id=uuid4(),  # Will be updated with actual decision_id
                model_id=ModelType.RASA,
                input_event_count=len(request.events),
                output=rasa_output.dict(),
                latency_ms=rasa_latency,
                success=True
            ))

            INFERENCE_LATENCY.labels(model='rasa', escalated='false').observe(rasa_latency / 1000)

        except Exception as e:
            MODEL_ERRORS.labels(model='rasa').inc()
            # Fall back to Mistral if Rasa fails
            rasa_output = None
            print(f"Rasa classifier error: {e}")

        # Secondary: Mistral (as scorer/fallback)
        mistral_start = time.time()
        try:
            mistral_output = await state.mistral_classifier.classify(request.events)
            mistral_latency = (time.time() - mistral_start) * 1000

            inference_runs.append(InferenceRun(
                decision_id=uuid4(),
                model_id=ModelType.MISTRAL_SMALL,
                input_event_count=len(request.events),
                output=mistral_output.dict(),
                latency_ms=mistral_latency,
                success=True
            ))

            INFERENCE_LATENCY.labels(model='mistral', escalated='false').observe(mistral_latency / 1000)

        except Exception as e:
            MODEL_ERRORS.labels(model='mistral').inc()
            mistral_output = None
            print(f"Mistral classifier error: {e}")

        # Choose best cheap classifier output
        cheap_output = _choose_best_classifier_output(rasa_output, mistral_output)

        if not cheap_output:
            raise HTTPException(
                status_code=503,
                detail="All cheap classifiers failed"
            )

        # Step 3: Apply gating policy
        gating_decision = state.gating_policy.should_escalate(
            classifier_output=cheap_output,
            session=session
        )

        # Track gating reason
        reason_type = gating_decision.reason.split(':')[0] if ':' in gating_decision.reason else 'other'
        GATING_REASONS.labels(reason_type=reason_type).inc()

        # Step 4: Escalate if needed
        final_intent = cheap_output.intent
        final_confidence = cheap_output.confidence
        model_used = cheap_output.model_id
        was_escalated = False

        if gating_decision.should_escalate or request.force_escalation:
            deepseek_start = time.time()
            try:
                escalation_output = await state.deepseek_reasoner.reason(
                    events=request.events,
                    cheap_output=cheap_output,
                    session=session
                )
                deepseek_latency = (time.time() - deepseek_start) * 1000

                inference_runs.append(InferenceRun(
                    decision_id=uuid4(),
                    model_id=ModelType.DEEPSEEK_REASONING,
                    input_event_count=len(request.events),
                    output=escalation_output.dict(),
                    latency_ms=deepseek_latency,
                    success=True
                ))

                # Use escalation output
                final_intent = escalation_output.final_intent
                final_confidence = escalation_output.confidence
                model_used = ModelType.DEEPSEEK_REASONING
                was_escalated = True

                INFERENCE_LATENCY.labels(model='deepseek', escalated='true').observe(deepseek_latency / 1000)

            except Exception as e:
                MODEL_ERRORS.labels(model='deepseek').inc()
                print(f"DeepSeek escalation error: {e}")
                # Fall back to cheap classifier output
                # (Already set above)

        # Step 5: Create decision record
        decision = IntentDecision(
            session_id=request.session_id,
            intent=final_intent,
            confidence=final_confidence,
            was_escalated=was_escalated,
            gating_decision=gating_decision,
            source_event_ids=[e.event_id for e in request.events],
            model_used=model_used
        )

        # Update inference runs with decision_id
        for run in inference_runs:
            run.decision_id = decision.decision_id

        # Step 6: Write to database
        await state.db_client.write_decision(decision, inference_runs)

        # Update metrics
        total_latency = (time.time() - start_time) * 1000
        INFERENCE_REQUESTS.labels(status='success').inc()

        if was_escalated:
            ESCALATION_RATE.set(
                await state.db_client.get_escalation_rate(window_hours=1)
            )

        return InferenceResponse(
            decision=decision,
            inference_runs=inference_runs,
            total_latency_ms=total_latency
        )

    except HTTPException:
        raise
    except Exception as e:
        INFERENCE_REQUESTS.labels(status='error').inc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


def _choose_best_classifier_output(
    rasa_output: Optional[ClassifierOutput],
    mistral_output: Optional[ClassifierOutput]
) -> Optional[ClassifierOutput]:
    """
    Choose the best classifier output from Rasa and Mistral.

    Strategy:
    1. If only one succeeded, use it
    2. If both succeeded, use Rasa if confidence > 0.8, else use higher confidence
    """
    if not rasa_output and not mistral_output:
        return None

    if not rasa_output:
        return mistral_output

    if not mistral_output:
        return rasa_output

    # Both succeeded: use Rasa for high-confidence known patterns
    if rasa_output.confidence > 0.8:
        return rasa_output

    # Otherwise use higher confidence
    return rasa_output if rasa_output.confidence >= mistral_output.confidence else mistral_output


@app.get("/stats")
async def get_stats():
    """Get current statistics"""
    stats = await state.db_client.get_stats()
    return stats


@app.post("/config/gating")
async def update_gating_config(config: GatingConfig):
    """Update gating policy configuration"""
    state.gating_policy = GatingPolicy(config)
    return {"status": "updated", "config": config.dict()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
