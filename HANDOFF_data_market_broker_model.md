# Data Performance Marketplace – Broker Model Clarification

**Status:** Ready for Opus implementation
**Date:** 2026-01-04
**Context:** Clarification of market maker role in data_performance_marketplace.md

---

## Executive Summary

The **market maker** role in the data performance marketplace is actually a **data broker** (you). This clarifies the pricing and liquidity model significantly.

---

## Corrected Model

### Participants & Flow
```
AI Browser (provides segments)
    ↓
YOU (Market Maker/Data Broker)
    ├─ Quote bid/ask prices (via proprietary algorithm)
    ├─ Manage access capacity (escrowed rights, not raw data)
    ├─ Earn spread (buy from providers, sell to consumers)
    └─ Control liquidity and phase progression
    ↓
Data Consumers (buy segments at ask price)
```

### Key Clarification
- **Market Maker ≠ Data Buyer** → Market Maker = Data Broker (middleman)
- You don't hold raw data (only access rights)
- You profit from the bid/ask spread
- You control when/if speculation layers (Phases 3-4) launch

---

## Phase Progression (Broker Perspective)

| Phase | Retail | Institutions | You (Broker) |
|-------|--------|--------------|------------|
| **1** | Utility only (buy data) | Utility only | Set prices, earn spread |
| **2** | Forward contracts (delivery required) | Forward contracts | Add time-based products |
| **3** | **Locked out** | Synthetic derivatives (cash settlement) | Offer derivatives to qualified traders |
| **4** | Options/calls/puts open | Options/calls/puts | Open speculation layer for all |

---

## Revenue Model

**Phase 1-2 (Foundation):**
- Spread-based: buy from providers at X, sell to consumers at X + margin
- Volume: utility-driven demand for intent signals

**Phase 3-4 (Speculation):**
- Spread + directional positioning (if you choose to be counterparty)
- Higher volumes from derivative traders
- Market-making fees from call/put issuance

---

## Why This Model is Sound

1. **Clear moat** – Your proprietary pricing algorithm IS your edge
2. **Aligned incentives** – You profit from accurate pricing
3. **Regulatory clarity** – Single broker/custodian (Wyoming DAO LLC) is cleaner
4. **Proven model** – Bloomberg, Refinitiv, etc. operate this way
5. **Controlled rollout** – You decide Phase 3-4 timing based on stability

---

## Implementation Next Steps for Opus

1. **Update data_performance_marketplace.md**
   - Clarify "market maker" terminology → use "broker" or "platform operator" instead
   - Explicitly name YOU as the broker in sections 6-7
   - Clarify that broker earns spread (revenue model)

2. **Define pricing algorithm spec**
   - Formula: `Price = BaseValue × FreshnessMultiplier × DemandPressure × ScarcityFactor`
   - Document how YOUR proprietary model feeds these components
   - Specify bid/ask spread calculation

3. **Design broker inventory system**
   - Escrowed access capacity (not raw data storage)
   - PAT collateral requirements per phase
   - Exposure limits per segment/window

4. **Smart contract architecture (zkSync Era)**
   - Broker settlement: receives PAT from consumers, pays providers
   - Access rights registration (who owns rights to which segments)
   - Phase-gated derivative enablement (Phase 3+ requires governance vote)

5. **Speculation layer (Phase 4 planning)**
   - Call/put contract specs
   - Cash settlement mechanics
   - Counterparty risk management (broker or AMM model?)

---

## Notes

- This clarification removes ambiguity from the original document
- You're not running a permissionless DEX; you're running a regulated data brokerage
- Wyoming DAO LLC provides legal clarity for this structure
- Phases provide a clear path to introducing speculation without regulatory risk

---

**Ready for Opus:** Yes. This handoff clarifies the business model, participants, and implementation priorities.
