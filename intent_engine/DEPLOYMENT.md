# Intent Detection Engine - Deployment Guide

Complete guide for deploying the intent detection engine in production.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Initial Setup](#initial-setup)
4. [Database Setup](#database-setup)
5. [Service Deployment](#service-deployment)
6. [Browser Integration](#browser-integration)
7. [Monitoring Setup](#monitoring-setup)
8. [Production Checklist](#production-checklist)
9. [Troubleshooting](#troubleshooting)
10. [Cost Estimation](#cost-estimation)

---

## Prerequisites

### Hardware Requirements

**Minimum (Development/Testing):**
- 8 CPU cores
- 32GB RAM
- 100GB SSD
- 1x GPU (8GB VRAM) for LLM serving

**Recommended (Production):**
- 16+ CPU cores
- 64GB+ RAM
- 500GB SSD
- 2x GPU (24GB VRAM each) for LLM serving
- Separate database server

### Software Requirements

- Docker 24.0+ with Docker Compose
- NVIDIA Docker runtime (for GPU support)
- PostgreSQL 15+ (if not using Docker)
- Python 3.11+
- Node.js 18+ (for browser agent)

### API Keys & Licenses

- **Rasa Pro License** (or use OSS Rasa with limitations)
- **GCP Account** (for BigQuery analytics storage)
- **Optional:** Mistral API key, DeepSeek API key (if using hosted vs self-hosted)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      PAT Browser (Client)                        │
│                     ↓ Events via RudderStack                     │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RudderStack Data Plane                        │
│          ↓ Postgres (operational)    ↓ BigQuery (analytics)     │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Router Service                       │
│  ┌────────────┐    ┌────────────┐    ┌──────────────────────┐  │
│  │Rasa (cheap)│ → │Gating Policy│ → │DeepSeek (escalation) │  │
│  │Mistral     │    │             │    │                      │  │
│  └────────────┘    └────────────┘    └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│              Monitoring (Prometheus + Grafana)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-org/NIMBUS.git
cd NIMBUS/intent_engine
```

### 2. Configure Environment

```bash
# Copy example environment file
cp deployment/.env.example deployment/.env

# Edit with your credentials
nano deployment/.env
```

Required variables:
- `POSTGRES_PASSWORD`: Secure database password
- `GCP_PROJECT_ID`: Google Cloud project for BigQuery
- `GCP_CREDENTIALS_JSON`: Path to GCP service account JSON
- `RASA_LICENSE_KEY`: Rasa Pro license key
- `GRAFANA_PASSWORD`: Grafana admin password

### 3. Set Up GPU Support (if using self-hosted LLMs)

```bash
# Install NVIDIA Docker runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

---

## Database Setup

### 1. Initialize Postgres Schema

```bash
# Start Postgres container
cd deployment
docker-compose up -d postgres

# Wait for Postgres to be ready
docker-compose exec postgres pg_isready

# Schema is auto-applied via initdb.d mount
# Verify:
docker-compose exec postgres psql -U intent_user -d intent_engine -c "\dt"
```

### 2. Set Up BigQuery

```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# Authenticate
gcloud auth application-default login

# Create dataset
bq mk --dataset --location=US ${GCP_PROJECT_ID}:intent_engine

# Create tables from schema
cd ../models
bq mk --table ${GCP_PROJECT_ID}:intent_engine.events_raw bigquery_schema.json
bq mk --table ${GCP_PROJECT_ID}:intent_engine.intent_inference_runs bigquery_schema.json
bq mk --table ${GCP_PROJECT_ID}:intent_engine.intent_decisions bigquery_schema.json
```

### 3. Create Views

```bash
# Create analytical views
bq query --use_legacy_sql=false < bigquery_views.sql
```

---

## Service Deployment

### Option A: All-in-One Docker Compose (Recommended for Development)

```bash
cd deployment

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f router-api
```

### Option B: Production Deployment (Kubernetes)

See [kubernetes/README.md](kubernetes/README.md) for production K8s manifests.

### 4. Verify Service Health

```bash
# Router API
curl http://localhost:8000/health

# Rasa
curl http://localhost:5005/health

# Prometheus
curl http://localhost:9091/-/healthy

# Grafana
curl http://localhost:3000/api/health
```

---

## Browser Integration

### 1. Update Browser Agent

Replace `QwenAPIClient` with `RouterClient`:

```python
# browser/src/agent.py

# OLD:
from .qwen_client import QwenAPIClient
qwen = QwenAPIClient()
agent = BrowserAgent(qwen)

# NEW:
from .router_client import RouterClient
router = RouterClient(router_endpoint="http://localhost:8000")
agent = BrowserAgent(router)
```

### 2. Configure RudderStack Browser SDK

```javascript
// In PAT Browser extension/content script
rudderanalytics.load(
  "YOUR_WRITE_KEY",
  "http://localhost:8080", // RudderStack data plane
  {
    trackingPlan: {
      strict: true,
      allowedEvents: [
        "page_viewed",
        "link_clicked",
        "scroll_depth",
        "product_viewed",
        "add_to_cart"
      ]
    }
  }
);

// Track events
rudderanalytics.track("page_viewed", {
  url: window.location.href,
  url_hash: hashUrl(window.location.href),
  scroll_depth: getScrollDepth(),
  time_on_page: getTimeOnPage()
});
```

### 3. Test End-to-End Flow

```bash
# Start browser agent
cd browser
python -m src.agent

# Browse some test URLs
# Check router logs for inference requests
docker-compose logs -f router-api

# Verify decisions in database
docker-compose exec postgres psql -U intent_user -d intent_engine \
  -c "SELECT intent, confidence, was_escalated FROM intent_decisions ORDER BY created_at DESC LIMIT 10;"
```

---

## Monitoring Setup

### 1. Access Grafana

```bash
# Open browser
open http://localhost:3000

# Login: admin / <GRAFANA_PASSWORD from .env>
```

### 2. Import Dashboards

1. Go to **Dashboards → Import**
2. Upload JSON files from `monitoring/grafana_dashboards/`
3. Select Prometheus as data source

**Key Dashboards:**
- Intent Engine Overview
- Model Performance
- Escalation Monitoring
- Cost Analysis

### 3. Configure Alerts

Edit `monitoring/alertmanager.yml`:

```yaml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK'
        channel: '#intent-alerts'
        title: 'Intent Engine Alert'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

Restart Alertmanager:
```bash
docker-compose restart alertmanager
```

---

## Production Checklist

### Security

- [ ] Change all default passwords in `.env`
- [ ] Enable SSL/TLS for all HTTP endpoints
- [ ] Restrict Postgres/Redis to internal network only
- [ ] Enable authentication for Prometheus/Grafana
- [ ] Set up firewall rules (only expose necessary ports)
- [ ] Rotate API keys regularly
- [ ] Enable audit logging

### Performance

- [ ] Configure Postgres connection pooling (pgBouncer)
- [ ] Set up Redis for session caching
- [ ] Tune vLLM batch size and GPU memory
- [ ] Enable HTTP/2 for FastAPI
- [ ] Set up CDN for static assets
- [ ] Configure rate limiting

### Reliability

- [ ] Set up database backups (pg_dump daily)
- [ ] Configure BigQuery snapshot scheduling
- [ ] Enable Postgres replication (primary + replica)
- [ ] Set up health check monitoring (uptime robot, etc.)
- [ ] Configure auto-restart policies for containers
- [ ] Test disaster recovery procedures

### Monitoring

- [ ] Set up custom Grafana dashboards
- [ ] Configure Slack/PagerDuty alerts
- [ ] Set up log aggregation (ELK/Loki)
- [ ] Enable distributed tracing (Jaeger/Tempo)
- [ ] Configure cost tracking dashboards

---

## Troubleshooting

### Router API Returns 503

**Symptom:** All inference requests fail with 503.

**Causes:**
- Rasa or Mistral classifier is down
- Database connection failed

**Fix:**
```bash
# Check classifier health
docker-compose logs rasa-pro
docker-compose logs llm-mistral

# Restart services
docker-compose restart rasa-pro llm-mistral router-api
```

### High Escalation Rate (> 50%)

**Symptom:** Too many requests escalating to DeepSeek, high costs.

**Causes:**
- Gating thresholds too strict
- Cheap classifiers performing poorly
- Data distribution shift

**Fix:**
```bash
# Check current policy
curl http://localhost:8000/config/gating

# Update to aggressive policy (lower escalation)
curl -X POST http://localhost:8000/config/gating \
  -H "Content-Type: application/json" \
  -d '{"default_threshold": 0.60, "high_risk_threshold": 0.75, "high_value_threshold": 0.70, "top2_margin_threshold": 0.05}'

# Monitor impact
curl http://localhost:8000/stats
```

### DeepSeek Timeout Errors

**Symptom:** Escalation requests timing out.

**Causes:**
- Model serving is slow (GPU memory issue)
- Network latency to API

**Fix:**
```bash
# Increase router timeout
# Edit router/.env:
DEEPSEEK_TIMEOUT=60.0

# Check GPU memory usage
docker exec llm-deepseek nvidia-smi

# Restart DeepSeek service
docker-compose restart llm-deepseek
```

---

## Cost Estimation

### Self-Hosted Setup (Recommended)

**Infrastructure:**
- GPU server (2x A100 40GB): $3,000/month
- Database server (16 cores, 64GB): $500/month
- BigQuery storage (1TB): $20/month
- BigQuery queries: $50/month
- **Total: ~$3,570/month**

**Pros:** Predictable costs, no API rate limits, full control
**Cons:** Higher upfront complexity

### Hybrid (Hosted LLMs)

**API Costs (1M inferences/month, 20% escalation):**
- Rasa Pro: $500/month (flat license)
- Mistral Small API: $200/month (800K inferences @ $0.25/1M tokens)
- DeepSeek API: $500/month (200K escalations @ $2.50/1M tokens)
- Infrastructure: $500/month
- BigQuery: $70/month
- **Total: ~$1,770/month**

**Pros:** Lower upfront cost, easier scaling
**Cons:** Variable costs, API dependencies

---

## Next Steps

1. **Week 1:** Deploy to staging environment, run load tests
2. **Week 2:** Fine-tune gating policy, optimize escalation rate
3. **Week 3:** Integrate with browser agent, test end-to-end
4. **Week 4:** Production deployment, monitor for 1 week
5. **Ongoing:** Weekly reviews of escalation rate, model performance, costs

---

## Support

- **Documentation:** See individual component READMEs
- **Issues:** https://github.com/your-org/NIMBUS/issues
- **Slack:** #intent-engine channel

---

**Last Updated:** 2026-01-08
