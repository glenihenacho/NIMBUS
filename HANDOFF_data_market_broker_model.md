# Data Performance Marketplace – Broker Model Clarification

**Status:** Ready for Opus implementation
**Date:** 2026-01-04
**Context:** Clarification of market maker role in data_performance_marketplace.md

---

## Executive Summary

The **market maker** role in the data performance marketplace is actually a **data broker** (you). This clarifies the pricing and liquidity model significantly.

---

## Corrected Model

### Participants & Atomic Flow
```
PAT Browser Users (data providers/sellers)
    ↓ sell at BID price
YOU (Broker/Data Marketplace Operator)
    ↓ sell at ASK price
Data Consumers (buyers/data users)

Revenue = (ASK - BID) × Volume
```

### Core Mechanism: Atomic Settlement

**Single transaction, no inventory holding:**

When a Data Consumer buys 1 segment at ASK (100 PAT):
```
Smart contract executes atomically:
├─ Browser Users receive BID (70 PAT) ✓
├─ YOU receive Spread (30 PAT) ✓
└─ Consumer receives data access rights ✓

All three parties settle simultaneously.
Zero inventory risk. Zero timing mismatch.
```

### Key Clarifications
- **No broker inventory** – You never hold access rights alone
- **Atomic smart contracts** – Single transaction splits payment to all three parties
- **Zero capital lockup** – Spread is earned instantly on each transaction
- **Blockchain-native** – Fits zkSync Era atomic transaction model better than traditional brokerage
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

**All Phases:**
- **Atomic spread model:** `Revenue = (ASK - BID) × Volume`
- No inventory holding, no capital requirements
- Earned instantly on each transaction settlement
- Smart contract automates the split; you can't deviate from pricing

**Phase 1-2 (Foundation):**
- Volume driven by utility-based demand for intent signals
- Spread optimized for market penetration vs. margin

**Phase 3-4 (Speculation):**
- Higher volumes from derivative traders
- Additional fees from call/put issuance (if you choose to offer them)
- Core atomic spread mechanism remains unchanged

---

## Why This Model is Sound

1. **Clear moat** – Your proprietary pricing algorithm IS your edge (BID/ASK determined by your formula)
2. **Atomic settlement** – Zero inventory risk, zero capital requirements, all parties settle simultaneously
3. **Aligned incentives** – You profit from accurate pricing (wider spreads on well-priced segments)
4. **Blockchain-native** – Atomic transactions fit zkSync Era better than traditional brokerage
5. **Regulatory clarity** – Single broker/custodian (Wyoming DAO LLC) is cleaner than decentralized market making
6. **Proven model** – DEXs and spot exchanges operate this atomic model at scale
7. **Controlled rollout** – You decide Phase 3-4 timing and feature expansion based on stability

---

## Atomic Settlement Mechanics (Critical)

**The single most important implementation detail:**

**Segment Storage (Minimal):**
```
Segment Registry:
  segmentId → {
    type: "AUTO_INTENT",
    window: "7D",
    confidence: 0.75,
    ASK: 100
  }

Global Config:
  brokerMargin: 0.30  // Percentage of ASK that broker keeps
```

**Atomic Settlement (Single Transaction):**
When a Data Consumer buys a segment at ASK (100 PAT):

```
buySegment(segmentId):
  ├─ Read segment metadata (type, window, confidence, ASK)
  ├─ Read globalBrokerMargin (0.30)
  ├─ Calculate brokerSpread = ASK × brokerMargin = 30
  ├─ Calculate userPayout = ASK - brokerSpread = 70
  ├─ transfer(userPayout) → Browser Users Pool
  ├─ transfer(brokerSpread) → Broker Wallet
  └─ grantAccess(consumer, segmentId)

  If ANY step fails → entire transaction reverts
  If ALL succeed → settlement is instant and irreversible
```

**Governance Function (Owner-only):**
```solidity
// UUPS Upgrade Pattern - Replace entire implementation
updateBrokerContract(address newBrokerContractAddress):
  // Atomically migrate to new broker contract implementation
  ├─ Verify new contract address is valid
  ├─ All state preserved via proxy pattern
  ├─ Emit BrokerContractUpdated(oldAddress, newAddress)
  └─ Only callable by Wyoming DAO LLC (owner)

// Individual Parameter Setters (no upgrade needed)
setBrokerMargin(uint256 newMarginBps):  // Adjust 30% → 25%
setBrokerWallet(address newWallet):     // Update broker recipient
advancePhase():                         // Progress 1→2→3→4
setPaused(bool paused):                 // Emergency pause
```

**Note:** Provider earnings are held in contract and withdrawn directly by users (no usersPoolWallet).

**Broker contract can be upgraded to:**
- Fix bugs or optimize gas
- Add new features (call/put issuance, etc.)
- Change core settlement logic if needed

**Why this matters:**
- **No waiting period** – Spread earned immediately on settlement
- **No counterparty risk** – All three parties settle or none do
- **No inventory liquidity drain** – Broker never holds access rights
- **Smart contract enforces pricing** – Segment ASK is stored; algorithm cannot be bypassed
- **Governance flexibility** – Update margin, wallets, phase progression without redeploying

**Contrast with traditional broker:**
```
❌ Traditional: Broker buys from provider → holds inventory → sells to consumer
   (Broker capital at risk, inventory decay, timing mismatch)

✅ Atomic: Smart contract splits one payment to provider + broker + access for consumer
   (Zero capital, zero inventory, instant settlement)
```

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

4. **Smart contract architecture (zkSync Era) – Atomic Settlement**
   - **Segment storage:** Minimal (type, window, confidence, ASK only)
   - **Global configuration:** Single `brokerMargin` percentage (e.g., 0.30)
   - **Core transaction:** `buySegment(segmentId)` atomically:
     - Reads segment ASK and global margin
     - Calculates brokerSpread = ASK × margin
     - Calculates userPayout = ASK - brokerSpread
     - Transfers both amounts simultaneously + grants access rights
   - **No intermediate states:** All settle together or transaction reverts
   - **Governance:** UUPS upgradeable proxy + individual parameter setters
     - `updateBrokerContract(newImpl)` - Full implementation upgrade via UUPS
     - `setBrokerMargin(bps)` - Update margin without upgrade
     - `setBrokerWallet(addr)` - Update broker recipient
     - `advancePhase()` - Progress 1→2→3→4
     - `setPaused(bool)` - Emergency pause
     - All owner-only callable (Wyoming DAO LLC)
   - Access rights registration (who owns rights to which segments, backed by smart contract)
   - Phase-gated derivative enablement (Phase 3+ requires governance call)

5. **Speculation layer (Phase 4 planning)**
   - Call/put contract specs
   - Cash settlement mechanics
   - Counterparty risk management (broker or AMM model?)

---

## Notes

- This clarification removes ambiguity from the original document
- You're running a **regulated data brokerage on blockchain**, not a permissionless DEX
- **Atomic settlement is the architectural centerpiece** – not a traditional "buy then sell" model
- Wyoming DAO LLC provides legal and operational clarity for this structure
- Phases provide a clear path to introducing speculation without regulatory risk
- **Smart contracts enforce pricing algorithm** – ensures BID/ASK spreads cannot be manipulated post-quote
- Zero capital requirements and zero inventory risk are massive operational advantages

---

**Ready for Opus:** Yes. This handoff clarifies:
- Business model (atomic brokerage, not traditional)
- Participants (PAT Browser Users → Broker → Data Consumers)
- Revenue (Spread × Volume, earned instantly)
- Implementation focus (Smart contract atomic settlement)
- Pricing control (Your algorithm determines BID/ASK per segment)
