# PAT Intent Detection Engine

Backend pipeline for detecting web browsing intent signals and creating monetizable data segments.

**NOTE:** This is the data ingestion + intent inference layer. For the user-facing browser, see `HANDOFF_user_browser_architecture.md`.

## Overview

This pipeline processes raw browsing events (from Ungoogled-Chromium browser) through a hybrid intent detection system:
- **Cheap classifier**: Rasa Pro + Mistral-small (via vLLM)
- **Escalation**: DeepSeek reasoning (gated, expensive)
- **Output**: Structured intent signals → data segments → marketplace

## Features

- **Hybrid intent detection**: Rasa (deterministic) + Mistral (semantic) + DeepSeek (reasoning)
- **RudderStack ingestion**: Event transport, schema validation, tracking plan enforcement
- **BigQuery + Postgres**: Immutable event lake + operational state
- **Gating policy**: Escalate to long-chain only when uncertain (confidence < 0.70)
- **Segment creation**: Aggregate intents into marketplace-ready segments
- **Marketplace integration**: Submit segments at ASK prices determined by broker algorithm

## Architecture Stack

**See HANDOFF_intent_detection_engine.md for complete spec.**

- **Ingestion**: RudderStack (self-hosted data plane)
- **Storage**: BigQuery (raw events) + Postgres (operational)
- **Cheap Classifier**: Rasa Pro + Mistral-small (vLLM)
- **Escalation**: DeepSeek reasoning (vLLM, gated)
- **Serving**: FastAPI router (single inference entry point)
- **Monitoring**: Prometheus + Grafana + OpenSearch

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install models locally or use vLLM
pip install vllm
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `RUDDERSTACK_WRITE_KEY`: RudderStack write key
- `BIGQUERY_PROJECT_ID`: GCP BigQuery project
- `POSTGRES_URI`: PostgreSQL connection string
- `VLLM_MISTRAL_URL`: vLLM endpoint for Mistral (http://localhost:8001)
- `VLLM_DEEPSEEK_URL`: vLLM endpoint for DeepSeek (http://localhost:8002)
- `PAT_MARKETPLACE_API_KEY`: API key for marketplace submission

## Usage

### Start Intent Router (FastAPI)

```bash
# Ensure vLLM services are running first
python -m vllm.entrypoints.openai_api_server --model mistralai/Mistral-7B-Instruct-v0.1 --port 8001
python -m vllm.entrypoints.openai_api_server --model deepseek-ai/deepseek-coder-33b-instruct --port 8002

# Start router service
python -m src.router
```

### Infer Intent

```python
import httpx
import asyncio

async def infer_intent(event_bundle):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/infer/intent",
            json={
                "session_id": "abc-123",
                "user_id": "user-456",
                "events": event_bundle
            }
        )
    return response.json()

# Response includes: decision_id, final_intent, confidence, supporting_signals, alternatives
```

### Running Tests

```bash
pytest tests/
```

## Data Segments

Segments are identified by:
- **Type**: PURCHASE_INTENT, RESEARCH_INTENT, COMPARISON_INTENT, etc.
- **Time Window**: How recent the signals are (e.g., 7D = 7 days)
- **Confidence Range**: The confidence score range (e.g., 0.70-0.85)

Example segment ID: `PURCHASE_INTENT|7D|0.70-0.85`

## Architecture

```
┌──────────────────────────┐
│  Ungoogled-Chromium      │
│  (User Browser)          │
│  + Canonical Events      │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│  RudderStack             │
│  (Event Transport)       │
└────────────┬─────────────┘
             ↓
    ┌────────┴──────────┐
    ↓                   ↓
┌─────────┐       ┌──────────┐
│BigQuery │       │Postgres  │
│(Raw)    │       │(Ops)     │
└────┬────┘       └────┬─────┘
     └────────┬─────────┘
              ↓
┌──────────────────────────────────┐
│  FastAPI Router (Inference)      │
├──────────────────────────────────┤
│ ├─ Rasa Pro (cheap classifier)  │
│ ├─ Mistral-small (vLLM, scorer) │
│ ├─ Gating policy (escalate?)     │
│ └─ DeepSeek (vLLM, long-chain)  │
└────────────┬─────────────────────┘
             ↓
┌──────────────────────────┐
│  Segment Creation        │
│  (Aggregate intents)     │
└────────────┬─────────────┘
             ↓
┌──────────────────────────┐
│  PAT Marketplace         │
│  (Atomic Settlement)     │
└──────────────────────────┘
```

**See HANDOFF_intent_detection_engine.md for complete architecture.**

## Testing

```bash
pytest tests/
```

## License

MIT
