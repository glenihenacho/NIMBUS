# Intent Detection Engine – Production Architecture

**Status:** Ready for Opus implementation
**Date:** 2026-01-04
**Context:** Intent detection pipeline for PAT ecosystem (bridges browser behavior → data segments)

---

## Executive Summary

The **intent detection engine** transforms raw browsing behavior (from Ungoogled-Chromium browser) into monetizable data segments for the PAT marketplace.

**Architecture:** Input → Cheap classifier → Confidence gate → Escalate to long-chain → Structured output

**Stack:**
- **Ingestion:** RudderStack (self-hosted)
- **Storage:** BigQuery (raw events) + Postgres (operational)
- **Cheap classifier:** Rasa Pro + Mistral-small (hybrid)
- **Escalation:** DeepSeek reasoning (gated)
- **Serving:** FastAPI router service
- **Inference runtime:** vLLM (Mistral + DeepSeek)
- **Monitoring:** Prometheus + Grafana

---

## System Architecture

### Data Flow (Complete)

```
┌─────────────────────────────────────────────┐
│  PAT Browser (Ungoogled-Chromium)           │
│  ├─ Track: URL, time, title, interactions  │
│  └─ Emit: RudderStack events               │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  RudderStack (Event Transport)              │
│  ├─ Tracking plan enforced                 │
│  ├─ Schema validation                       │
│  └─ Route to: BigQuery + Postgres          │
└────────────────┬────────────────────────────┘
                 ↓
        ┌────────┴────────┐
        ↓                 ↓
   ┌─────────┐      ┌──────────┐
   │BigQuery │      │Postgres  │
   ├─────────┤      ├──────────┤
   │Raw      │      │Sessions  │
   │Events   │      │Routing   │
   │(immut.) │      │State     │
   └────┬────┘      └────┬─────┘
        └────────┬───────┘
                 ↓
┌─────────────────────────────────────────────┐
│  Intent Detection Router (FastAPI)          │
│  ├─ Fetch event bundle                     │
│  ├─ Run cheap classifier (Rasa + Mistral)  │
│  ├─ Apply gating policy                    │
│  └─ Escalate if needed (DeepSeek)         │
└────────────────┬────────────────────────────┘
                 ↓
        ┌────────┴────────┐
        ↓                 ↓
   ┌──────────┐      ┌──────────┐
   │Rasa Pro  │      │vLLM      │
   │(determin)│      │(Mistral) │
   └────┬─────┘      └────┬─────┘
        └─────┬──────────┘
              ↓
    [Gating policy evaluation]
    ├─ If cheap_conf < 0.70 → escalate
    ├─ If intent HIGH_RISK and conf < 0.85 → escalate
    ├─ If high_value_session and conf < 0.80 → escalate
    └─ If top2_margin < 0.10 → escalate
              ↓
    ┌─────────────────────────┐
    │ vLLM (DeepSeek)        │
    │ (Long-chain reasoning) │
    │ [Gated, expensive]     │
    └────────┬────────────────┘
             ↓
┌─────────────────────────────────────────────┐
│  Inference Decision (JSON)                  │
│  ├─ final_intent                           │
│  ├─ confidence                             │
│  ├─ supporting_signals[event_ids]          │
│  ├─ alternatives[]                         │
│  ├─ recommended_action                     │
│  ├─ model_id, policy_version               │
│  └─ latency_ms                             │
└────────────────┬────────────────────────────┘
                 ↓
        ┌────────┴────────────┐
        ↓                     ↓
   ┌─────────────┐       ┌──────────┐
   │Postgres     │       │BigQuery  │
   │Intent       │       │Inference │
   │Decisions    │       │Runs      │
   │(ops)        │       │(audit)   │
   └─────────────┘       └──────────┘
        ↓
┌─────────────────────────────────────────────┐
│  Data Segments Pipeline                     │
│  ├─ Aggregate intents into segments         │
│  ├─ Confidence scoring (0.70-0.95)          │
│  ├─ Time windowing (7D, 30D, etc.)          │
│  └─ Submit to Marketplace API               │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│  PAT Marketplace (Broker Model)             │
│  → Segments listed at ASK price             │
│  → Settlement at atomic level               │
└─────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Ingestion Layer (RudderStack)

**Self-hosted RudderStack data plane:**

```yaml
# Tracking plan (enforced schema)
events:
  - page_view:
      properties:
        url: string (required)
        referrer: string
        time_spent_seconds: integer
        title: string
  - user_interaction:
      properties:
        interaction_type: enum[click, scroll, form_submit]
        element_selector: string
        timestamp: integer
  - session_start:
      properties:
        session_id: uuid
        user_id: uuid
        timestamp: integer

destinations:
  - type: bigquery
    dataset: pat_events
    table: events_raw
    partition_by: date
  - type: postgres
    schema: public
    table: events_realtime (TTL: 30 days)
```

**Destinations:**
- **BigQuery:** Immutable event lake, append-only, partitioned by date
- **Postgres:** Operational reads, sessions, routing state (with TTL)

---

### 2. Storage Layer

**BigQuery (analytics/monetization):**
```sql
-- Raw events (immutable)
CREATE TABLE pat_events.events_raw (
  event_id STRING,
  event_type STRING,
  user_id STRING,
  session_id STRING,
  timestamp TIMESTAMP,
  properties JSON,
  _partition_date DATE
)
PARTITION BY _partition_date
CLUSTER BY user_id, session_id;

-- Inference runs (audit trail)
CREATE TABLE pat_events.inference_runs (
  run_id STRING,
  source_event_ids ARRAY<STRING>,
  cheap_classifier_output JSON,
  escalated BOOLEAN,
  long_chain_output JSON,
  final_decision JSON,
  latency_ms INTEGER,
  timestamp TIMESTAMP
);

-- Intent decisions (for monetization)
CREATE TABLE pat_events.intent_decisions (
  decision_id STRING,
  user_id STRING,
  final_intent STRING,
  confidence FLOAT64,
  segment_id STRING,
  ask_price INTEGER,
  timestamp TIMESTAMP
);
```

**Postgres (operational):**
```sql
-- Sessions (routing state)
CREATE TABLE sessions (
  session_id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  created_at TIMESTAMP,
  last_activity TIMESTAMP,
  event_count INTEGER,
  value_score FLOAT,
  status VARCHAR(20) -- active, escalated, resolved
);

-- Inference decisions (operational)
CREATE TABLE intent_decisions (
  decision_id UUID PRIMARY KEY,
  user_id UUID,
  final_intent VARCHAR(50),
  confidence FLOAT,
  run_id UUID REFERENCES inference_runs,
  created_at TIMESTAMP
);

-- Rate limits (if needed)
CREATE TABLE escalation_counters (
  user_id UUID,
  window_start TIMESTAMP,
  escalation_count INTEGER,
  PRIMARY KEY (user_id, window_start)
);
```

---

### 3. Cheap Classifier Layer

**Hybrid approach: Rasa Pro + Mistral-small**

**Rasa Pro:**
- Deterministic NLU pipeline for known intents
- Fast inference (<50ms)
- Handles intent classification from DOM/metadata
- Confidence thresholds pre-configured

**Mistral-small (via vLLM):**
- Parallel scorer when Rasa confidence is borderline
- Semantic elasticity for evolving intent taxonomy
- Lightweight model (~7B parameters)
- Batched inference for throughput

**Router decision logic:**
```python
def classify(event_bundle):
    # Step 1: Rasa classification
    rasa_result = rasa.parse(event_bundle)
    rasa_intent = rasa_result.intent
    rasa_conf = rasa_result.confidence

    # Step 2: Mistral scoring (if Rasa confidence < 0.75)
    if rasa_conf < 0.75:
        mistral_result = mistral.score(event_bundle, candidates=[rasa_intent])
        mistral_conf = mistral_result.confidence
        # Use ensemble: average confidence
        final_conf = (rasa_conf + mistral_conf) / 2
    else:
        final_conf = rasa_conf

    # Step 3: Gating policy
    return {
        "intent": rasa_intent,
        "confidence": final_conf,
        "classifier": "rasa" if final_conf > 0.75 else "rasa+mistral",
        "escalate": should_escalate(rasa_intent, final_conf)
    }
```

---

### 4. Gating Policy (Default Thresholds)

```python
def should_escalate(intent, confidence, session_value=None):
    """
    Escalate to DeepSeek reasoning if any condition is true.
    """

    # Condition 1: Low confidence on any intent
    if confidence < 0.70:
        return True, "low_confidence"

    # Condition 2: High-risk intents require higher confidence
    HIGH_RISK_INTENTS = ["purchase_intent", "financial_intent", "personal_data"]
    if intent in HIGH_RISK_INTENTS and confidence < 0.85:
        return True, "high_risk_low_confidence"

    # Condition 3: High-value sessions require higher confidence
    if session_value and session_value > 100 and confidence < 0.80:
        return True, "high_value_low_confidence"

    # Condition 4: Ambiguity between top intents
    if top2_margin < 0.10:  # Intent probabilities too close
        return True, "ambiguous"

    return False, None
```

---

### 5. Escalation Layer (DeepSeek)

**Long-chain reasoning model (gated, expensive):**

```python
def escalate_to_deepseek(event_bundle, cheap_result):
    """
    Expensive multi-step reasoning for ambiguous/high-value cases.
    """

    prompt = f"""
    Given the following browsing events, determine the user's primary intent.

    Events:
    {format_events(event_bundle)}

    Cheap classifier result: {cheap_result.intent} ({cheap_result.confidence:.2f})

    Analyze:
    1. What is the primary intent signal?
    2. Are there conflicting signals?
    3. What confidence level is justified?
    4. What are alternative interpretations?

    Output JSON:
    {{
      "final_intent": "...",
      "confidence": 0.XX,
      "reasoning": "...",
      "alternatives": [...]
    }}
    """

    result = deepseek.reason(prompt)  # vLLM inference
    return {
        "final_intent": result.final_intent,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "alternatives": result.alternatives,
        "model": "deepseek-reasoning"
    }
```

**Escalation rate targets:**
- Day 1: ~10-15% escalation rate (conservative)
- Mature: ~5% escalation rate (once classifiers are well-tuned)

---

### 6. FastAPI Router Service

**Single entry point for all inference:**

```python
from fastapi import FastAPI, BackgroundTasks
from sqlalchemy import create_engine
from google.cloud import bigquery

app = FastAPI()
pg_engine = create_engine("postgresql://...")
bq_client = bigquery.Client()

@app.post("/api/infer/intent")
async def infer_intent(event_bundle: dict, background_tasks: BackgroundTasks):
    """
    Main inference endpoint.

    Request:
      {
        "session_id": "...",
        "user_id": "...",
        "events": [...]
      }

    Response:
      {
        "decision_id": "...",
        "final_intent": "purchase_intent",
        "confidence": 0.85,
        "supporting_signals": ["event_id_1", "event_id_2"],
        "alternatives": [{"intent": "research_intent", "confidence": 0.12}],
        "recommended_action": "create_segment",
        "model_id": "rasa+mistral",
        "latency_ms": 42
      }
    """

    decision_id = uuid.uuid4()
    start_time = time.time()

    # Step 1: Cheap classification
    cheap_result = classify(event_bundle)

    # Step 2: Gating policy
    should_escalate, reason = gating_policy(cheap_result)

    # Step 3: Escalate if needed
    if should_escalate:
        final_result = escalate_to_deepseek(event_bundle, cheap_result)
        model_used = "deepseek-reasoning"
    else:
        final_result = cheap_result
        model_used = "rasa+mistral"

    latency_ms = (time.time() - start_time) * 1000

    # Step 4: Construct response
    response = {
        "decision_id": str(decision_id),
        "final_intent": final_result.intent,
        "confidence": final_result.confidence,
        "supporting_signals": extract_signal_ids(event_bundle),
        "alternatives": final_result.get("alternatives", []),
        "recommended_action": determine_action(final_result),
        "model_id": model_used,
        "policy_version": "1.0",
        "latency_ms": int(latency_ms)
    }

    # Step 5: Async write to both DBs
    background_tasks.add_task(
        write_decision,
        decision_id=decision_id,
        response=response,
        event_bundle=event_bundle
    )

    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow()}
```

---

### 7. Inference Runtime (vLLM)

**Mistral-small + DeepSeek served via vLLM:**

```bash
# Start Mistral-small (cheap path)
python -m vllm.entrypoints.openai_api_server \
  --model mistralai/Mistral-7B-Instruct-v0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.8 \
  --tensor-parallel-size 1

# Start DeepSeek (escalation path)
python -m vllm.entrypoints.openai_api_server \
  --model deepseek-ai/deepseek-coder-33b-instruct \
  --port 8001 \
  --gpu-memory-utilization 0.8 \
  --tensor-parallel-size 1
```

**Router client (FastAPI calls vLLM via HTTP):**
```python
import httpx

async def mistral_score(event_bundle):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/chat/completions",
            json={
                "model": "Mistral-7B-Instruct-v0.1",
                "messages": [{"role": "user", "content": build_prompt(event_bundle)}],
                "temperature": 0.3,
                "max_tokens": 200
            }
        )
    return response.json()

async def deepseek_reason(event_bundle):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/v1/chat/completions",
            json={
                "model": "deepseek-coder-33b-instruct",
                "messages": [{"role": "user", "content": build_reasoning_prompt(event_bundle)}],
                "temperature": 0.5,
                "max_tokens": 500
            }
        )
    return response.json()
```

---

### 8. Monitoring & Observability

**Prometheus metrics (primary):**

```python
from prometheus_client import Counter, Histogram, Gauge

# Latency
inference_latency_ms = Histogram(
    'inference_latency_ms',
    'Inference latency in milliseconds',
    buckets=[10, 25, 50, 100, 250, 500, 1000]
)

# Classification results
intent_counter = Counter(
    'intent_decisions_total',
    'Total intent decisions by intent type',
    ['intent', 'model', 'escalated']
)

# Escalation rate
escalation_rate = Gauge(
    'escalation_rate_pct',
    'Percentage of decisions escalated to long-chain'
)

# Confidence distribution
confidence_histogram = Histogram(
    'decision_confidence',
    'Confidence score distribution',
    buckets=[0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99]
)

# Model quality
error_rate = Counter(
    'inference_errors_total',
    'Total inference errors',
    ['model', 'error_type']
)

# Cost tracking
cost_per_intent = Counter(
    'cost_per_intent_usd',
    'Cost per resolved intent (cheap vs. escalated)',
    ['model']
)
```

**Grafana dashboards:**
1. **Real-time inference** – p50/p95/p99 latency, request rate, escalation %
2. **Intent distribution** – Top intents by volume, distribution shifts
3. **Model quality** – Confidence distribution, error rates, top confusion pairs
4. **Cost analysis** – Cost per intent cheap vs. escalated, ROI

**OpenSearch logs (audit trail):**
- Every inference run: request, cheap result, gating decision, final result
- Error logs with context (event bundle, model output, traceback)
- Searchable by user_id, session_id, decision_id

---

## Data Segments Pipeline

**From intent decisions → data segments:**

```python
def create_segment_from_intents(user_id, time_window="7D"):
    """
    Aggregate user's intent decisions into a monetizable segment.
    """

    # Fetch intent decisions for user in time window
    decisions = query_intent_decisions(user_id, time_window)

    if len(decisions) < 5:
        return None  # Insufficient signal

    # Determine dominant intent
    intent_counts = Counter([d.final_intent for d in decisions])
    dominant_intent, count = intent_counts.most_common(1)[0]

    # Calculate confidence (average over decisions)
    avg_confidence = mean([d.confidence for d in decisions])

    # Create segment
    segment = {
        "segment_id": generate_id(),
        "type": dominant_intent.upper(),
        "window": time_window,
        "confidence": round(avg_confidence, 2),
        "count": count,
        "users_contributing": 1,
        "created_at": datetime.utcnow(),
        "source_event_ids": [d.event_id for d in decisions]
    }

    # Submit to marketplace API
    submit_to_marketplace(segment)

    return segment
```

**Segment eligibility criteria (from browser handoff):**
- ✅ 5+ intent signals in time window
- ✅ Confidence ≥ 0.70
- ✅ Time window specified (7D, 30D, etc.)
- ✅ Intent type maps to marketplace taxonomy

---

## Deployment Architecture

**Day 1 single-VM stack:**

```
┌──────────────────────────────────────────┐
│  VM (e.g., GCP n2-standard-8)            │
├──────────────────────────────────────────┤
│                                          │
│  Docker Compose services:                │
│  ├─ rudderstack-dataplane (port 8080)   │
│  ├─ router-api (FastAPI, port 8000)     │
│  ├─ rasa-pro (port 5005)                │
│  ├─ vllm-mistral (port 8001)            │
│  ├─ vllm-deepseek (port 8002)           │
│  ├─ postgres (port 5432)                │
│  ├─ prometheus (port 9090)              │
│  ├─ grafana (port 3000)                 │
│  └─ opensearch (port 9200)              │
│                                          │
│  External:                               │
│  ├─ BigQuery (GCP)                      │
│  └─ PAT Marketplace API                 │
└──────────────────────────────────────────┘
```

**Scale to K8s when:**
- Inference latency becomes bottleneck
- Escalation rate exceeds 20%
- Daily events > 10M

---

## Implementation Priorities for Opus

### Phase 1: Data Pipeline
1. Deploy RudderStack (self-hosted)
   - Configure tracking plan enforcement
   - Route to BigQuery + Postgres
   - Validate schema on ingest

2. Set up storage
   - BigQuery dataset + tables
   - Postgres schema + indexes
   - Test event replay capability

### Phase 2: Cheap Classifier
1. Deploy Rasa Pro
   - Pre-trained NLU models for known intents
   - Configure intent taxonomy
   - Test on sample browsing events

2. Deploy vLLM (Mistral-small)
   - Model download + setup
   - OpenAI API compatibility layer
   - Batch inference optimization

### Phase 3: Router Service
1. Implement FastAPI router
   - Cheap classification endpoint
   - Gating policy evaluation
   - Async writes to BigQuery + Postgres

2. Integrate LLM clients
   - vLLM HTTP clients (Mistral, DeepSeek)
   - Error handling + retries
   - Rate limiting

### Phase 4: Escalation
1. Deploy vLLM (DeepSeek)
   - Expensive model, gated
   - Long-chain reasoning prompts
   - Cost tracking

2. Refine gating policy
   - Monitor escalation rate
   - Adjust thresholds based on metrics
   - A/B test Rasa vs. Mistral configurations

### Phase 5: Monitoring
1. Prometheus + Grafana
   - Dashboards for latency, intent distribution, quality
   - Alerting on high error rates, slow p99

2. OpenSearch + Kibana
   - Log aggregation for audit trail
   - Searchable inference runs

### Phase 6: Segments Pipeline
1. Implement segment creation
   - Aggregate intent decisions
   - Filter for eligibility
   - Submit to marketplace API

2. Monitor segment monetization
   - Track ask price per segment
   - Measure payout velocity
   - A/B test confidence thresholds

---

## Cost Model (Day 1)

**Assumptions:** 10K browsers, ~100 events/day = 1M events/day

| Component | Cost | Notes |
|-----------|------|-------|
| Rasa Pro | $500/mo | Per-instance license |
| vLLM (Mistral) | $100/mo | GPU time (shared) |
| vLLM (DeepSeek) | $200/mo | GPU time (larger model) |
| Postgres | $50/mo | Self-hosted VM |
| BigQuery | $50/mo | 1M events @ $0.05/GB scan |
| RudderStack | $100/mo | Self-hosted license |
| Prometheus + Grafana | $30/mo | Self-hosted |
| **Total** | **~$1,030/mo** | Scales to 100M events/day |

**Per-intent cost breakdown:**
- Cheap (Rasa + Mistral): ~$0.00001
- Escalated (DeepSeek): ~$0.0005
- Average (at 10% escalation): ~$0.00006/intent

---

## Key Design Decisions

1. **Hybrid cheap classifier** – Rasa (deterministic) + Mistral (elastic)
   - Best of both worlds: stability + semantic flexibility

2. **Gating policy over always-escalate** – Only expensive model when uncertain
   - Keeps costs low, quality high

3. **BigQuery + Postgres split** – Analytics vs. operations
   - Immutable event lake enables re-inference, replays, monetization audits

4. **Self-hosted stack** – Full control, no vendor lock-in
   - RudderStack, vLLM, Postgres all self-hosted
   - Can migrate models/vendors freely

5. **Async writes** – No blocking on DB operations
   - Router responds immediately, decisions written in background

6. **Decision audit trail** – Every inference run logged
   - Supports model quality monitoring, debugging, compliance

---

**Ready for Opus:** Yes. This handoff clarifies:
- End-to-end data pipeline (RudderStack → BigQuery/Postgres → Intent Router → Segments)
- Cheap classifier architecture (Rasa + Mistral hybrid)
- Gating policy with default thresholds (0.70, 0.85, 0.80, 0.10)
- Escalation to DeepSeek (expensive, gated)
- FastAPI router as single inference entry point
- Monitoring stack (Prometheus + Grafana + OpenSearch)
- Segment creation from intent decisions
- Day 1 full-stack deployment (single VM, Docker Compose)
- Cost model and scaling path
