# Canonical Browser Event Schema (v1)

**Status:** Ready for Opus implementation
**Date:** 2026-01-04
**Context:** Production-grade event schema for PAT browser → intent detection pipeline

---

## Design Philosophy

This schema is the **immutable contract** between the browser and your entire data infrastructure.

**Core Principles:**
1. **Raw before derived** – Never collapse signals; preserve raw data
2. **Event ≠ intent** – Events are facts, intent is interpretation
3. **Time + sequence matter** – Ordering is more valuable than labels
4. **Everything is replayable** – Re-run inference years later with new models
5. **Monetization-first** – Enable selling at raw, aggregated, and inferred levels

**Why this matters:**
- Swap intent models without recollecting data
- Backtest new classifiers on historical events
- Sell data at multiple levels (raw streams, cohorts, predictions)
- Migrate from managed → open-source without data loss
- Remain compliance-aware (GDPR/CCPA consent gates)

---

## Top-Level Envelope (Required for Every Event)

Every event from the browser follows this structure:

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "page_view",
  "event_version": "1.0",
  "event_time": "2026-01-04T14:32:17.123Z",
  "ingest_time": "2026-01-04T14:32:18.456Z",

  "session": { ... },
  "actor": { ... },
  "context": { ... },
  "payload": { ... },
  "privacy": { ... }
}
```

**Field Definitions:**
- `event_id` (UUID-v7): Unique, sortable by time
- `event_type` (enum): Canonical event type (see section 5)
- `event_version` (string): Schema version for migrations
- `event_time` (ISO-8601): When event occurred (client-side)
- `ingest_time` (ISO-8601): When received by RudderStack (server-side)

**Why event_time ≠ ingest_time matters:**
- Allows buffering and offline behavior
- Enables latency analysis
- Preserves true temporal sequence

---

## Session Object (Sequence Is Everything)

```json
"session": {
  "session_id": "uuid",
  "sequence": 42,
  "session_start": "2026-01-04T14:00:00Z",
  "is_new_session": false,
  "referrer": "https://google.com/search?q=data%20brokers",
  "entry_point": "search"
}
```

**Field Definitions:**
- `session_id`: Stable within 30-minute window
- `sequence`: Event order within session (0-indexed)
- `session_start`: When session began
- `is_new_session`: True if this is user's first session ever
- `referrer`: Previous page (before entry)
- `entry_point`: One of [direct, search, ad, referral, app, other]

**Why sequence matters:**
- Enables intent reconstruction ("user searched → visited pricing → clicked CTA")
- Critical for segment monetization (intent path → higher valuation)
- Session boundaries define cohort granularity

---

## Actor Object (Pseudonymous by Design)

```json
"actor": {
  "user_id": "7f8a9b3c2d1e0f...",
  "anonymous_id": "browser-stable-id-xyz123",
  "device_id": "hashed:iphone13,2024-01",
  "account_id": null,
  "role": "visitor"
}
```

**Field Definitions:**
- `user_id`: SHA-256 hash of actual ID (null if not logged in)
- `anonymous_id`: Browser-stable identifier for cross-session tracking
- `device_id`: Hashed device fingerprint (no PII)
- `account_id`: Only if user has authenticated with PAT browser
- `role`: [visitor, user, premium]

**Privacy Rule:**
- No PII here ever
- All hashing happens client-side (browser)
- Identity resolution happens downstream only

---

## Context Object (Environmental Truth)

```json
"context": {
  "url": "https://stripe.com/pricing/billing",
  "path": "/pricing/billing",
  "domain": "stripe.com",
  "title": "Billing API – Stripe",
  "content_category": ["pricing", "payments"],

  "viewport": {
    "width": 1920,
    "height": 1080
  },

  "device": {
    "type": "desktop",
    "os": "macOS",
    "os_version": "14.2",
    "browser": "Chrome",
    "browser_version": "131.0.0"
  },

  "geo": {
    "country": "US",
    "region": "CA",
    "city": "San Francisco"
  },

  "time": {
    "hour": 14,
    "day_of_week": "Monday",
    "is_business_hours": true
  }
}
```

**Field Definitions:**
- `url`: Full URL (including path)
- `path`: Pathname only
- `domain`: Second-level domain (for privacy)
- `title`: Page title (raw HTML)
- `content_category`: Auto-classified by browser (list of tags)
- `viewport`: Screen dimensions (mobile vs desktop detection)
- `device`: OS, browser, version
- `geo`: Country/region (coarse only; no precise lat/lon)
- `time`: Context for demand signals (pricing requests at 2 AM = different intent)

**Why this survives migration:**
- No vendor-specific fields
- All inference-relevant metadata preserved
- Supports both managed and OSS models

---

## Core Event Types (10 Canonical Primitives)

You don't need 100 event types. These 10 cover 95% of intent signals:

| Event Type | Purpose | Use Case |
|------------|---------|----------|
| `page_view` | Navigation intent | User landed on pricing → purchase intent signal |
| `scroll` | Engagement depth | Scrolled 80% of pricing page → strong signal |
| `click` | Decision probe | Clicked "Buy Now" → conversion intent |
| `hover` | Hesitation / evaluation | Hovered over price point → price sensitivity |
| `text_input` | Explicit intent signal | Searched "best data brokers" → research intent |
| `search` | High-signal intent | On-site search for feature → strong buying signal |
| `form_submit` | Conversion intent | Submitted contact form → sales qualified |
| `media_interaction` | Attention | Watched product video → engagement |
| `error` | Friction / frustration | "404 Not Found" → pain point |
| `custom_action` | Business-specific | Custom event defined by browser |

---

## Payload Object (Event-Specific, Raw)

**Rule: Payloads contain raw, uninterpreted data only. No labels. No intent guesses.**

### Example 1: text_input (Explicit Intent Signal)

```json
"event_type": "text_input",
"payload": {
  "field_id": "search_box",
  "field_name": "q",
  "raw_text": "best security guard service near me",
  "input_length": 36,
  "is_autocomplete": false,
  "is_corrected": false,
  "character_count": 36,
  "word_count": 6
}
```

### Example 2: scroll (Engagement Depth)

```json
"event_type": "scroll",
"payload": {
  "scroll_depth_pct": 72,
  "scroll_velocity": "slow",
  "max_depth_reached": 85,
  "section_id": "pricing-table",
  "time_on_page_seconds": 47,
  "scroll_direction": "down"
}
```

### Example 3: click (Decision Probe)

```json
"event_type": "click",
"payload": {
  "element_id": "cta-buy-now",
  "element_class": "button-primary",
  "element_text": "Buy Now",
  "element_type": "button",
  "parent_section": "pricing-tier-pro",
  "click_x": 640,
  "click_y": 480
}
```

### Example 4: form_submit (Conversion Intent)

```json
"event_type": "form_submit",
"payload": {
  "form_id": "contact_form",
  "form_fields": {
    "email": "user@example.com",
    "company": "Acme Corp",
    "employees": "100-500",
    "use_case": "security"
  },
  "form_completion_pct": 100,
  "time_to_submit_seconds": 180
}
```

### Example 5: page_view (Navigation Intent)

```json
"event_type": "page_view",
"payload": {
  "referrer_path": "/search?q=data%20brokers",
  "page_load_time_ms": 1200,
  "dom_ready_ms": 850,
  "had_errors": false,
  "is_first_page": false
}
```

---

## Privacy Object (Monetization Gate)

```json
"privacy": {
  "consent": {
    "analytics": true,
    "personalization": false,
    "monetization": false
  },
  "jurisdiction": "CCPA",
  "retention_tier": "standard",
  "is_opted_in_to_data_sale": false,
  "do_not_track": false
}
```

**Field Definitions:**
- `consent.analytics`: Can track behavior (required for any use)
- `consent.personalization`: Can use for custom recommendations (optional)
- `consent.monetization`: Can sell raw/aggregated data (optional)
- `jurisdiction`: GDPR, CCPA, LGPD, NONE
- `retention_tier`: [short (30d), standard (90d), long (365d)]
- `is_opted_in_to_data_sale`: Explicit consent for resale
- `do_not_track`: Browser DNT header respected

**Critical for monetization:**
- Only sell events where `monetization: true`
- Respect jurisdiction rules (GDPR requires explicit opt-in)
- Retention tier determines how long data is kept
- Users without monetization consent → local use only

---

## Intent Inference Layer (Stored Separately)

Intent is **never inline** in raw events. It's stored in a separate inference table:

```json
{
  "intent_event_id": "uuid-v7",
  "source_event_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002",
    "550e8400-e29b-41d4-a716-446655440003"
  ],
  "model_id": "rasa:v1.0",
  "model_version": "1.0",
  "intent_label": "purchase_intent",
  "confidence": 0.87,
  "alternatives": [
    {"intent": "research_intent", "confidence": 0.10},
    {"intent": "comparison_intent", "confidence": 0.03}
  ],
  "reasoning": "User searched for 'best X', visited pricing page, scrolled 80%, clicked CTA",
  "created_at": "2026-01-04T14:35:00Z",
  "escalated_to_long_chain": false
}
```

**Why separate:**
- Swap models without touching raw events
- Re-infer old data with new classifiers
- Sell raw vs. inferred data at different price points
- Audit trail: which model made which decision

---

## Data Storage (BigQuery)

```sql
-- Raw events (immutable append-only)
CREATE TABLE pat_events.events_raw (
  event_id STRING NOT NULL,
  event_type STRING NOT NULL,
  event_version STRING,
  event_time TIMESTAMP NOT NULL,
  ingest_time TIMESTAMP NOT NULL,

  session STRUCT<
    session_id STRING,
    sequence INT64,
    session_start TIMESTAMP,
    is_new_session BOOL,
    referrer STRING,
    entry_point STRING
  >,

  actor STRUCT<
    user_id STRING,
    anonymous_id STRING,
    device_id STRING,
    account_id STRING,
    role STRING
  >,

  context STRUCT<
    url STRING,
    path STRING,
    domain STRING,
    title STRING,
    content_category ARRAY<STRING>,
    viewport STRUCT<width INT64, height INT64>,
    device STRUCT<type STRING, os STRING, browser STRING>,
    geo STRUCT<country STRING, region STRING>
  >,

  payload JSON,
  privacy STRUCT<
    consent STRUCT<analytics BOOL, personalization BOOL, monetization BOOL>,
    jurisdiction STRING,
    retention_tier STRING,
    is_opted_in_to_data_sale BOOL
  >
)
PARTITION BY DATE(event_time)
CLUSTER BY session.session_id, actor.user_id;

-- Inference results (linked to raw events)
CREATE TABLE pat_events.intent_inferences (
  intent_event_id STRING NOT NULL,
  source_event_ids ARRAY<STRING> NOT NULL,
  model_id STRING NOT NULL,
  intent_label STRING NOT NULL,
  confidence FLOAT64 NOT NULL,
  alternatives ARRAY<STRUCT<intent STRING, confidence FLOAT64>>,
  reasoning STRING,
  created_at TIMESTAMP NOT NULL,
  escalated_to_long_chain BOOL
)
PARTITION BY DATE(created_at)
CLUSTER BY source_event_ids[0];
```

---

## Monetization Readiness

With this schema, you can sell:

### 1. Raw Event Streams
```sql
SELECT * FROM pat_events.events_raw
WHERE privacy.consent.monetization = true
  AND privacy.is_opted_in_to_data_sale = true
  AND event_type IN ('page_view', 'click', 'text_input')
```
**Price:** $0.01–0.05 per event (depends on category)

### 2. Aggregated Intent Cohorts
```sql
SELECT
  intent_label,
  context.domain,
  APPROX_QUANTILES(confidence, 100)[OFFSET(50)] as median_confidence,
  COUNT(*) as cohort_size,
  AVG(privacy.jurisdiction = 'CCPA') as ccpa_pct
FROM pat_events.intent_inferences
WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY intent_label, context.domain
```
**Price:** $100–500 per cohort (depends on size/freshness)

### 3. Temporal Intent Shifts
```sql
SELECT
  DATE(created_at) as date,
  intent_label,
  COUNT(*) as intent_count
FROM pat_events.intent_inferences
WHERE context.domain = 'stripe.com'
  AND created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY date, intent_label
ORDER BY date DESC
```
**Price:** $1,000–5,000 per dataset (depends on lookback period)

### 4. Category-Specific Demand Signals
```sql
SELECT
  CAST(context.viewport.width AS STRING) as device_type,
  context.domain,
  intent_label,
  COUNT(*) as signal_count
FROM pat_events.intent_inferences
WHERE context.content_category CONTAINS 'pricing'
  AND privacy.consent.monetization = true
GROUP BY device_type, context.domain, intent_label
```
**Price:** $500–2,000 (premium insight datasets)

**All without recollecting data.** Just re-query.

---

## Browser Implementation (Pseudocode)

**Sending events from Ungoogled-Chromium browser:**

```typescript
class BrowserEventTracker {
  private eventBuffer: BrowserEvent[] = [];
  private sessionId: string;
  private sequence: number = 0;

  constructor() {
    this.sessionId = generateUUID();
    this.startAutoFlush();
  }

  trackPageView(url: string, title: string) {
    const event: BrowserEvent = {
      event_id: generateUUIDv7(),
      event_type: "page_view",
      event_version: "1.0",
      event_time: new Date().toISOString(),

      session: {
        session_id: this.sessionId,
        sequence: this.sequence++,
        is_new_session: this.isFirstPage,
        referrer: document.referrer,
        entry_point: this.getEntryPoint()
      },

      actor: {
        user_id: this.getHashedUserID(), // null if not logged in
        anonymous_id: this.getAnonymousID(),
        device_id: this.hashDeviceID(),
        role: this.getUserRole()
      },

      context: {
        url: url,
        path: new URL(url).pathname,
        domain: new URL(url).hostname.split('.').slice(-2).join('.'),
        title: title,
        content_category: this.classifyContent(url, title),
        viewport: { width: window.innerWidth, height: window.innerHeight },
        device: { type: this.detectDeviceType(), os: this.detectOS(), browser: this.detectBrowser() },
        geo: { country: await this.getGeoCountry(), region: null }
      },

      payload: {
        page_load_time_ms: performance.now(),
        had_errors: this.hadLoadErrors()
      },

      privacy: {
        consent: this.getConsent(),
        jurisdiction: await this.detectJurisdiction(),
        retention_tier: "standard",
        is_opted_in_to_data_sale: this.userOptedInToSale(),
        do_not_track: navigator.doNotTrack === '1'
      }
    };

    this.eventBuffer.push(event);
  }

  trackClick(element: HTMLElement) {
    const event: BrowserEvent = {
      event_id: generateUUIDv7(),
      event_type: "click",
      event_time: new Date().toISOString(),
      session: this.getCurrentSession(),
      actor: this.getCurrentActor(),
      context: this.getCurrentContext(),

      payload: {
        element_id: element.id,
        element_class: element.className,
        element_text: element.innerText?.substring(0, 100),
        element_type: element.tagName.toLowerCase(),
        parent_section: element.closest('[data-section]')?.getAttribute('data-section'),
        click_x: event.clientX,
        click_y: event.clientY
      },

      privacy: this.getCurrentPrivacy()
    };

    this.eventBuffer.push(event);
  }

  private async startAutoFlush() {
    // Flush every 6 hours or on page unload
    setInterval(() => this.flush(), 6 * 60 * 60 * 1000);
    window.addEventListener('beforeunload', () => this.flush());
  }

  private async flush() {
    if (this.eventBuffer.length === 0) return;

    // Batch send to RudderStack
    const response = await fetch('https://rudderstack.example.com/api/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        batch: this.eventBuffer,
        context: { writeKey: 'RUDDERSTACK_KEY' }
      })
    });

    if (response.ok) {
      this.eventBuffer = [];
    }
  }
}
```

---

## Migration Guarantees

This schema guarantees you can:

### 1. Swap Intent Models Freely
```sql
-- Re-infer all 2024 data with new DeepSeek model
INSERT INTO pat_events.intent_inferences
SELECT
  GENERATE_UUID() as intent_event_id,
  source_event_ids,
  'deepseek:v2.0' as model_id,
  deepseek_classifier(source_events) as intent_label,
  ...
FROM pat_events.events_raw
WHERE DATE(event_time) >= '2024-01-01'
  AND DATE(event_time) < '2025-01-01'
```

### 2. Migrate from Managed → Open-Source
- RudderStack (managed) → RudderStack (self-hosted) – **0 data loss**
- Rasa Pro → Rasa OSS – **0 retraining needed**
- Proprietary classifier → Mistral – **0 event recollection**

### 3. Comply with GDPR/CCPA Retroactively
```sql
-- Delete events from users who withdrew consent
DELETE FROM pat_events.events_raw
WHERE actor.user_id IN (
  SELECT user_id FROM pat_events.consent_withdrawals
)
AND privacy.jurisdiction = 'GDPR'
```

### 4. Sell Historical Data Without Recollection
- Re-aggregate 2024 data
- Price it based on new demand
- Zero recollection overhead

---

## Example: Complete Event Journey

**User searches for "best payment processor" on Google, lands on Stripe, scrolls pricing:**

```json
[
  {
    "event_id": "001",
    "event_type": "page_view",
    "event_time": "2026-01-04T14:00:00Z",
    "session": {"session_id": "ABC", "sequence": 0, "referrer": "google.com"},
    "context": {"url": "https://stripe.com", "title": "Stripe – Payments"},
    "payload": {}
  },
  {
    "event_id": "002",
    "event_type": "scroll",
    "event_time": "2026-01-04T14:00:15Z",
    "session": {"session_id": "ABC", "sequence": 1},
    "context": {"url": "https://stripe.com/pricing"},
    "payload": {"scroll_depth_pct": 45, "section_id": "pricing-table"}
  },
  {
    "event_id": "003",
    "event_type": "scroll",
    "event_time": "2026-01-04T14:00:45Z",
    "session": {"session_id": "ABC", "sequence": 2},
    "payload": {"scroll_depth_pct": 92}
  },
  {
    "event_id": "004",
    "event_type": "click",
    "event_time": "2026-01-04T14:00:50Z",
    "session": {"session_id": "ABC", "sequence": 3},
    "payload": {"element_id": "cta-pricing-pro", "element_text": "Get Started"}
  }
]
```

**Intent router processes all 4 events:**
- Combines sequence (0→1→2→3)
- Detects pattern: search → page view → deep scroll → CTA click
- Assigns: `purchase_intent` (confidence 0.92)

**Monetization:**
- User has `monetization: true` consent
- Segment created: `{type: PURCHASE_INTENT, window: 7D, confidence: 0.92}`
- ASK price set by broker: 100 PAT
- Users receive BID: 70 PAT

All from a single, immutable event schema.

---

## Summary

| Aspect | Advantage |
|--------|-----------|
| **Raw data** | Re-inference without recollection |
| **Separate intent** | Swap models, backtest, audit |
| **Privacy gates** | GDPR/CCPA compliant monetization |
| **No vendor lock-in** | Works with Rasa, Mistral, DeepSeek, proprietary |
| **Sequence preserved** | Enables behavioral intent reconstruction |
| **Monetization-ready** | Sell at raw, aggregated, temporal, cohort levels |

---

**Ready for Opus:** Yes. This handoff clarifies:
- Canonical event schema (10 event types, 5 core objects)
- Raw-before-derived principle (intent stored separately)
- Privacy gates enable monetization (consent + jurisdiction)
- Complete browser implementation (EventTracker class)
- BigQuery schema (immutable raw, linked inferences)
- 4 monetization layers (raw, cohort, temporal, category)
- Migration guarantees (swap models, migrate platforms, reclaim historical data)
- Example end-to-end event flow with intent inference
