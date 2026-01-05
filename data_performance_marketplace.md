# Data Performance Marketplace – Design & Governance Guide

This document outlines the concept and design requirements for a **data
performance marketplace** within the PAT ecosystem.  The marketplace enables
data providers to monetize high‑quality datasets and data consumers to
discover, evaluate and purchase data using PAT tokens on **zkSync Era**.

## Technical Specifications

| Component | Technology |
|-----------|------------|
| **Settlement** | zkSync Era (PAT token) |
| **Data Storage** | Centralized cloud |
| **Data Type** | Web browsing intent signals |
| **Data Source** | Qwen‑powered AI browser agent |
| **Jurisdiction** | Wyoming DAO LLC |

## 1. Overview

Databricks describes a data marketplace as an online store that connects
data providers and consumers, offering participants the ability to buy and
sell data and related services in a secure environment with high‑quality,
consistent assets.  These platforms provide
infrastructure for data exchange while protecting privacy and security,
allowing users to research, sample, compare and purchase datasets.

### Marketplace vs. Data Exchange

A **public data marketplace** is open to many providers and consumers, whereas a
**data exchange** supports private sharing between a single provider and a few
recipients.  The PAT marketplace will operate as a
public platform with proper access control and reputation systems.

## 2. Participants & Roles

The PAT marketplace operates as a **data brokerage** with three distinct roles:

```
PAT Browser Users (Data Providers)
        ↓ sell segments at bid price
PAT Platform (Broker/Market Maker)
        ↓ sell segments at ask price
Data Consumers (Buyers)
```

### Data Providers (PAT Browser Users)
Individuals who browse the web using the PAT Browser.  Their browsing
behavior generates intent signal segments which they sell to the broker
at the **bid price**.  Providers earn PAT tokens for their data.

### Data Broker (PAT Platform Operator)
The PAT platform operates as a **regulated data broker** under Wyoming DAO LLC.
The broker:
- Quotes continuous bid/ask prices via proprietary pricing algorithm
- Buys segments from providers at bid, sells to consumers at ask
- Manages escrowed access capacity (not raw data)
- Earns the spread as revenue
- Controls phase progression and liquidity

### Data Consumers (Buyers)
Organizations or individuals who purchase intent signal segments at the
**ask price** to extract insights, target advertising, or enhance products.
Examples include ad networks, market researchers, and AI training pipelines.

## 3. Design Principles & Features

To build a successful marketplace, consider these core features:

1. **Secure environment** – Protect data privacy through encryption, secure
   storage and access controls.  Ensure that only authorized parties can
   purchase or download data.  Use PAT tokens for payments and integrate
   smart contracts to automate purchases.
2. **Data discovery & preview** – Provide search, filtering and preview
   capabilities so consumers can explore dataset schemas and sample data
   without downloading the entire dataset.
3. **Transparent pricing & licensing** – Allow providers to set prices and
   specify licensing terms (e.g. one‑time purchase, subscription, usage‑based).
4. **Quality metrics & rating system** – Display metrics such as accuracy,
   completeness, timeliness and reliability.  Allow consumers to rate and
   review datasets, which encourages providers to maintain high standards.  Atlan
   notes that many marketplaces include mechanisms for rating data products to
   provide additional information to buyers.
5. **Transaction management** – Implement smart contracts or backend systems
   to handle purchases, refunds and royalty distributions.  Maintain an audit
   trail for compliance.
6. **Integration & APIs** – Offer APIs so that the AI browser can ingest
   marketplace data automatically and allow external systems to query listings.
7. **Analytics & performance dashboard** – Provide dashboards for providers
   to see sales, downloads and ratings, and for consumers to track their
   purchases and usage statistics.
8. **Governance & compliance** – Apply data governance policies,
   including data provenance, legal compliance and privacy protection.

## 4. Data Quality & Governance

Ensuring data quality and governance is critical.  Atlan proposes a
step‑by‑step process for evaluating data before purchase:

1. **Understand your data needs** – Define the problem you want to solve
   and what type of data is required.
2. **Choose reputable marketplaces** – Research the platform’s vetting process
   and dispute mechanisms.
3. **Evaluate the data provider** – Check the provider's history and ratings.
4. **Check provenance & compliance** – Verify that data was collected
   ethically and complies with regulations (e.g. GDPR).
5. **Assess data quality** – Examine accuracy, completeness, consistency
   and timeliness.
6. **Implement governance** – Once acquired, define processes to maintain
   quality, security and privacy.
7. **Verify & validate** – Cross‑check the data against reliable sources.
8. **Monitor & update** – Continuously monitor performance and update data if
   it becomes outdated.

The PAT marketplace should embed these steps into its workflow.  For example,
the platform can require providers to submit provenance details and automate
quality checks (e.g. validate schema and timestamp freshness).  Consumers can
be guided through verification steps before finalizing a purchase.

## 5. Performance Metrics

In a “data performance” marketplace, datasets should be measured not only by
quality but also by **performance metrics** that indicate how useful they are
for downstream tasks.  Consider including:

- **Accuracy** – Statistical accuracy of the data (e.g. error rates, match
  rates to authoritative sources).
- **Completeness** – Proportion of missing or null values.
- **Timeliness / freshness** – How up‑to‑date the data is.
- **Consistency** – Consistent formatting across records and datasets.
- **Reliability** – Frequency of updates and provider uptime.
- **User ratings & reviews** – Feedback from consumers on dataset usefulness.

These metrics can be computed automatically during ingestion and displayed on
dataset listing pages.  Providers should be encouraged to upload metadata
supporting these metrics.  Consumers can filter datasets based on minimum
performance thresholds.

## 6. Platform Architecture

The PAT marketplace architecture:

1. **Frontend** – Web interface for browsing, searching and purchasing
   data segments.  Dashboards for providers and consumers.
2. **Backend & API** – Microservices handling authentication, listing
   management, PAT payments via zkSync Era, rating and quality evaluation.
   REST APIs for external integrations.
3. **Metadata & catalog store** – PostgreSQL database storing segment metadata,
   quality metrics, provenance and user reviews.
4. **Storage layer** – **Centralized cloud storage** (AWS S3 / GCP Cloud Storage)
   with encryption at rest.  Segments are stored off‑chain; only pricing and
   settlement occur on zkSync Era.
5. **Smart contracts (zkSync Era)** – PAT token contract, segment registry,
   payment escrow and market maker collateral management.
6. **AI browser integration** – The Qwen‑powered browser agent pushes new
   intent signal segments via API.  Segments are validated, scored and listed
   automatically.

## 7. Broker Model for Data Segments

The PAT platform operates as the **sole broker** for intent signal segments.
This is not a permissionless DEX—it is a regulated data brokerage where the
platform operator (YOU) serves as the middleman between providers and consumers.

### Segment Contracts

Each traded unit is a **segment** identified by its type, time window and
confidence score:

``Segment | Window | Confidence``
`PURCHASE_INTENT | 7D | 0.70–0.85`

Supply and demand for each market are finite and time‑sensitive.

### Broker Role & Revenue

The broker operates via **atomic settlement**—a single smart contract transaction
that splits payment to all three parties simultaneously:

```
buySegment(segmentId):
  ├─ Consumer pays ASK (100 PAT)
  ├─ Browser Users receive BID (70 PAT) ✓
  ├─ Broker receives Spread (30 PAT) ✓
  └─ Consumer receives data access rights ✓

All three parties settle atomically. Zero inventory risk.
```

**Key advantages over traditional brokerage:**
- **No inventory holding** – Broker never holds access rights alone
- **Zero capital requirements** – No need to pre-buy from providers
- **Instant settlement** – Spread earned immediately on each transaction
- **No counterparty risk** – All parties settle or transaction reverts
- **Blockchain-native** – Fits zkSync Era atomic transaction model

Revenue formula: `Revenue = (ASK - BID) × Volume`

### Pricing Algorithm

The broker's proprietary pricing function:

``Price = BaseValue × FreshnessMultiplier × DemandPressure × ScarcityFactor``

| Variable | Description |
|----------|-------------|
| **BaseValue** | Floor price per segment type (set by broker) |
| **FreshnessMultiplier** | 1.0→0.1 decay curve over window lifetime |
| **DemandPressure** | Consumption velocity ÷ supply rate |
| **ScarcityFactor** | Mint rate vs burn rate, substitute availability |

The **bid/ask spread** is calculated as:
- Bid = Price × (1 - SpreadBps/10000)
- Ask = Price × (1 + SpreadBps/10000)

Spread widens under high volatility or thin liquidity.

### Smart Contract Architecture

**Segment Registry (minimal storage):**
```
segmentId → {
  type: "PURCHASE_INTENT",
  window: "7D",
  confidence: 0.75,
  ASK: 100
}
```

**Global Configuration:**
```
brokerMargin: 0.30        // Percentage of ASK kept by broker
brokerWallet: 0x...       // Broker revenue recipient
usersPoolWallet: 0x...    // Provider payout pool
phase: 1                  // Current market phase (1-4)
```

**Governance Functions (owner-only):**
```
updateBrokerContract(address newImplementation)  // UUPS upgrade
setBrokerMargin(uint256 newMarginBps)            // Adjust margin (max 50%)
setBrokerWallet(address newWallet)               // Update revenue recipient
setUsersPoolWallet(address newWallet)            // Update provider pool
advancePhase()                                   // Progress 1→2→3→4
setPaused(bool paused)                           // Emergency pause
```

See `contracts/contracts/DataMarketplace.sol` for implementation.

### Risk Controls

Risk is managed by:
1. Limiting exposure per window and segment type
2. Widening spreads during volatility
3. Requiring higher PAT margins for illiquid segments
4. Automatic position unwinding at window expiry

## 8. Liquidity Phases & Speculation

The broker introduces speculative activity gradually to ensure price
discovery is rooted in real utility.  **The broker controls phase progression.**

### Phase Access by Participant Type

| Phase | Retail Users | Institutions | Broker Revenue |
|-------|--------------|--------------|----------------|
| **1** | Utility only (buy/sell data) | Utility only | Spread on spot trades |
| **2** | Forward contracts (delivery required) | Forward contracts | Spread + time premiums |
| **3** | **Locked out** | Synthetic derivatives (cash settlement) | Spread + derivative fees |
| **4** | Options/calls/puts open | Options/calls/puts | Full derivative suite |

### Phase Descriptions

**Phase 1 – Utility‑anchored spot market.**  Contracts must be exercised to
settle; there is no cash settlement or secondary trading.  This yields real
price discovery and trusted performance metrics.  The broker earns spread
on all transactions.

**Phase 2 – Forward access guarantees.**  The broker introduces contracts
for future window access, freshness locks and supply assurance.  Settlement
still requires delivery of data; no purely synthetic outcomes are allowed.
These instruments create hedging demand rather than speculation.

**Phase 3 – Restricted synthetic exposure.**  Only after deep liquidity,
stable pricing and audited performance history does the broker allow
PAT-collateralized contracts with cash settlement **for qualified institutions
only**.  Retail participants remain utility-bound (Phases 1-2 only).
The broker may act as counterparty or use an AMM model.

**Phase 4 – Optional open speculative layer.**  Once the underlying market
stands on its own, speculation may amplify liquidity.  PAT becomes a universal
clearing asset across spot and derivative markets.  The broker opens
options/calls/puts to all participants.  Phase 4 launch requires governance vote.

### Why This Model Works

1. **Clear moat** – The broker's proprietary pricing algorithm is the competitive edge
2. **Aligned incentives** – Broker profits from accurate pricing and transaction volume
3. **Regulatory clarity** – Single regulated broker (Wyoming DAO LLC) is cleaner than DEX
4. **Proven model** – Bloomberg, Refinitiv, and major data vendors operate similarly
5. **Controlled rollout** – Broker decides Phase 3-4 timing based on market stability

## 9. Implementation Status

**Completed:**
- ✅ Smart contracts: `contracts/contracts/DataMarketplace.sol` (UUPS upgradeable)
- ✅ PAT token: `contracts/contracts/PAT.sol`
- ✅ Atomic settlement with earnings tracking
- ✅ Phase progression system (1-4)
- ✅ Test suite: `contracts/test/DataMarketplace.test.ts`

**In Progress:**
- Browser integration with smart contract events
- Marketplace API for segment submission

**Planned:**
- Frontend UI for browsing and purchasing segments
- Analytics dashboard for providers
- Quality evaluation automation

See `contracts/` directory for smart contract implementation.
