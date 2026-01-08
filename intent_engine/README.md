# Intent Detection Engine

A production-grade, OSS-friendly ML pipeline for intent classification with confidence-based escalation.

## Architecture

```
Input → Cheap classifier → Confidence gate → Escalate to long-chain model → Structured output
```

## Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Ingestion** | RudderStack (self-hosted) | Event transport & tracking plan enforcement |
| **Storage** | BigQuery + Postgres | Analytics lake + operational serving |
| **Labeling** | Label Studio Cloud | Team review & dataset management |
| **Cheap Classifier** | Rasa Pro + Mistral-small | Known-intent stability + semantic elasticity |
| **Escalation** | DeepSeek (reasoning) | Complex/ambiguous/high-risk resolution |
| **Router Service** | FastAPI | Single inference entry point |
| **LLM Runtime** | vLLM | High-throughput model serving |
| **Monitoring** | Prometheus + Grafana | Metrics, alerts, drift detection |

## Directory Structure

```
intent_engine/
├── router/                 # FastAPI router service
│   ├── api/               # API endpoints
│   ├── gating.py          # Confidence gating policy
│   └── decision.py        # Decision logic
├── classifiers/           # Classifier implementations
│   ├── rasa_classifier.py # Rasa Pro integration
│   └── mistral_classifier.py # Mistral scorer
├── escalation/            # Escalation layer
│   └── deepseek_reasoner.py # DeepSeek long-chain
├── ingestion/             # Event ingestion
│   └── rudderstack_config.yml
├── models/                # Data models & schemas
│   ├── postgres_schema.sql
│   ├── bigquery_schema.json
│   └── intent_models.py
├── monitoring/            # Observability
│   ├── prometheus.yml
│   └── grafana_dashboards/
├── deployment/            # Deployment configs
│   └── docker-compose.yml
└── config/                # Configuration
    └── default.yaml
```

## Quick Start

```bash
# Start all services
docker-compose up -d

# Run router service
cd router && uvicorn main:app --reload

# Test inference
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "events": [...]}'
```

## Gating Policy

The router escalates to DeepSeek when:

- `cheap_conf < 0.70`, OR
- `intent in HIGH_RISK and cheap_conf < 0.85`, OR
- `high_value_session and cheap_conf < 0.80`, OR
- `top2_margin < 0.10`

## Integration with PAT Browser

The intent engine replaces the simple Qwen client in the browser agent:

```python
# Before: Direct Qwen API call
result = await qwen_client.analyze_page_content(url, content)

# After: Router-based inference
result = await router_client.infer(session_id, events)
```

## Development

See individual component READMEs for details:
- [Router Service](router/README.md)
- [Classifiers](classifiers/README.md)
- [Escalation](escalation/README.md)
- [Models](models/README.md)
- [Monitoring](monitoring/README.md)
