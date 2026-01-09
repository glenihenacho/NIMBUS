# Intent Detection Pipeline – Architecture & Implementation Guide

This document describes the design and implementation of the **intent detection pipeline** for PAT.

**IMPORTANT:** See `HANDOFF_intent_detection_engine.md` for the complete, production-ready specification.

The pipeline:
1. Collects canonical browser events (from Ungoogled-Chromium browser)
2. Routes through intent classifiers (Rasa + Mistral-small)
3. Escalates uncertain cases to DeepSeek (reasoning model)
4. Aggregates intents into monetizable data segments
5. Submits segments to PAT marketplace

## Technical Specifications

| Component | Technology |
|-----------|------------|
| **Ingestion** | RudderStack (self-hosted) |
| **Storage** | BigQuery (raw) + Postgres (ops) |
| **Cheap Classifier** | Rasa Pro + Mistral-small (vLLM) |
| **Escalation** | DeepSeek reasoning (vLLM, gated) |
| **Serving** | FastAPI router |
| **Data Type** | Web browsing intent signals (canonical schema) |
| **Output** | Data segments for PAT marketplace |
| **Monitoring** | Prometheus + Grafana + OpenSearch |

## 1. Concept & Motivation

Traditional web browsers act as passive windows into the internet.  AI browser
agents transform them into proactive, goal‑driven assistants.  According to
LayerX, these agents integrate large language models (LLMs) directly into the
browser so that user commands expressed in natural language are interpreted
and broken down into sequences of web tasks.  The
agent then autonomously navigates websites, interacts with forms and extracts
data, mimicking human‑like browsing behaviour.
This capability makes AI browser agents powerful tools for automating data
collection, research and workflows.

## 2. Architecture Overview

The PAT intent detection pipeline consists of:

1. **Event Collection (Ungoogled-Chromium)** – Browser collects raw browsing events
   following canonical schema (page_view, scroll, click, text_input, etc.)

2. **Event Transport (RudderStack)** – Self-hosted data plane validates tracking plan,
   enforces schema, routes events to BigQuery + Postgres

3. **Storage Layer** –
   - **BigQuery**: Immutable append-only raw events (replayable)
   - **Postgres**: Operational state (sessions, routing decisions)

4. **Intent Inference (FastAPI Router)** –
   - **Cheap path**: Rasa Pro (deterministic) + Mistral-small (vLLM, semantic)
   - **Gating policy**: Escalate if confidence < 0.70 (or high-risk/ambiguous)
   - **Expensive path**: DeepSeek reasoning (vLLM, long-chain)

5. **Output Generation** – Structured intent decisions (JSON) linked to source events

6. **Segment Creation** – Aggregate intent decisions into monetizable segments
   (type, window, confidence, ASK price)

### Classifier Hybrid

The intent detection uses a **hybrid classifier approach**:

- **Rasa Pro** – Deterministic NLU for known intents (fast, stable, rule-based)
- **Mistral-small** – Semantic classifier via vLLM (flexible, learns from context)
- **DeepSeek** – Long-chain reasoning (expensive, gated, used for ambiguous cases)

**Why hybrid:**
- Rasa handles 90% of cases fast and cheap
- Mistral adds semantic flexibility when Rasa confidence is borderline
- DeepSeek provides reasoning for high-stakes decisions (high-value sessions, new intents)
- Gating policy ensures cost-efficient escalation (only ~10% → DeepSeek)

## 3. Practical Development Steps

LayerX suggests the following process for building an AI browser agent:

1. **Define the agent's purpose and scope** – The PAT agent collects **web
   browsing intent signals** — user behavior patterns that indicate purchase
   intent, research interests or engagement signals.
2. **Design the agent's architecture** – Use a goal‑based agent with Qwen as
   the reasoning engine and Playwright for browser automation.
3. **Choose the right models and tools** – PAT uses **Qwen** (Alibaba's LLM)
   for reasoning and **Playwright** for headless browser automation.  Qwen
   provides strong multilingual capabilities and efficient inference.
4. **Develop the perception and action modules** – Write code to parse web
   pages (e.g. using BeautifulSoup or DOM APIs) and interact with them
   programmatically.  In the PAT ecosystem, you could leverage the `browser`
   and `computer` tools to perform these actions.
5. **Train and test the agent** – Provide examples of tasks and validate that
   the agent correctly executes them.  Use unit tests and simulated
   environments to catch errors early.
6. **Deployment and iteration** – Package the agent as a browser extension
   or integrate it into the existing AI browser framework.  Collect feedback
   from users, monitor performance and iterate.

## 4. Security Considerations

AI browser agents can access sensitive information and perform actions on a
user’s behalf.  LayerX warns that compromised agents could exfiltrate data
or execute malicious actions.  To mitigate these
risks:

1. **Sandboxing** – Run the agent in an isolated context with minimal
   privileges and restrict access to sensitive data.
2. **Prompt injection protection** – Implement filtering to detect and ignore
   malicious instructions embedded in web pages or prompts.
3. **Monitoring & logging** – Log all actions taken by the agent and monitor
   for anomalies.  Provide users with transparency about what the agent is
   doing.
4. **Access control** – Require explicit user consent for actions that may
   have side effects (e.g. purchases, sign‑ins) and implement multi‑factor
   authentication where possible.
5. **Continuous updates** – Regularly update the agent to address newly
   discovered vulnerabilities and integrate security patches.

## 5. Next Steps for Developers

**See HANDOFF_intent_detection_engine.md for complete implementation spec.**

### Implementation Roadmap

1. **Deploy event pipeline**
   - RudderStack (self-hosted data plane)
   - BigQuery + Postgres
   - Canonical event schema validation

2. **Deploy intent classifiers**
   - Rasa Pro + Mistral-small (vLLM)
   - DeepSeek (vLLM)
   - Gating policy (escalation thresholds)

3. **Implement FastAPI router**
   - Cheap classification endpoint
   - Gating logic
   - Async writes to BigQuery + Postgres

4. **Segment creation pipeline**
   - Aggregate intents from decisions
   - Filter for eligibility (5+ signals, conf ≥ 0.70)
   - Submit to marketplace API

5. **Monitoring & observability**
   - Prometheus + Grafana dashboards
   - OpenSearch audit trail
   - Cost tracking per intent

### Architecture References

- **Event schema**: See `HANDOFF_canonical_event_schema.md`
- **Intent pipeline**: See `HANDOFF_intent_detection_engine.md`
- **Broker model**: See `HANDOFF_data_market_broker_model.md`
- **Smart contracts**: `contracts/` for PAT settlement on zkSync Era
- **User browser**: See `HANDOFF_user_browser_architecture.md`
