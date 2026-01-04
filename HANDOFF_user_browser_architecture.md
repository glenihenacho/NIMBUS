# User-Facing Browser – Architecture & Web3 Integration

**Status:** Ready for Opus implementation
**Date:** 2026-01-04
**Context:** User-facing browser architecture for PAT ecosystem (separate from AI data ingestion)

---

## Executive Summary

The **user-facing browser** is a Chrome/Firefox-like application that enables users to:
- Browse the web normally
- Connect a Web3 wallet (for receiving PAT payouts)
- Have their browsing behavior tracked and monetized
- Receive real-time payout notifications when segments are sold

**Separate component:** The **AI data ingestion system** analyzes browser behavior, detects intent signals, and creates marketplace segments.

---

## Architecture Overview

### Component Stack

```
┌──────────────────────────────────────┐
│    User-Facing Browser               │
├──────────────────────────────────────┤
│  ✓ Chromium/Firefox engine           │
│  ✓ Web3 wallet integration           │
│  ✓ Behavior tracking                 │
│  ✓ PAT payout notifications          │
└──────────────────────────────────────┘
            ↓
┌──────────────────────────────────────┐
│    Local Data Collection             │
├──────────────────────────────────────┤
│  ✓ Track browsing history            │
│  ✓ Capture page metadata             │
│  ✓ Record user interactions          │
└──────────────────────────────────────┘
            ↓
┌──────────────────────────────────────┐
│    AI Data Ingestion Pipeline        │
├──────────────────────────────────────┤
│  ✓ Detect intent signals             │
│  ✓ Create data segments              │
│  ✓ Submit to marketplace API         │
└──────────────────────────────────────┘
            ↓
┌──────────────────────────────────────┐
│    PAT Marketplace Smart Contracts   │
├──────────────────────────────────────┤
│  ✓ Settle segment sales              │
│  ✓ Split payments (users + broker)   │
│  ✓ Track ownership/payouts           │
└──────────────────────────────────────┘
```

---

## Core Features

### 1. Wallet Integration
- **Supported wallets:** MetaMask, WalletConnect, Coinbase Wallet
- **Network:** zkSync Era mainnet
- **User flow:**
  ```
  Launch browser
    → Connect wallet (one-time setup)
    → Approve payout wallet address
    → Wallet connected ✓
  ```
- **Persistent connection:** Wallet address stored locally (encrypted)
- **Signature requests:** Only for payout authorization, not for browsing

### 2. Browsing Behavior Tracking
- **What's tracked:**
  - URL visited (domain + path, no query parameters for privacy)
  - Time spent per page
  - Page title and metadata
  - User interactions (clicks, scrolls, form submissions)
  - Referral source (previous page)

- **What's NOT tracked:**
  - Personal passwords or credentials
  - Form input values (except button clicks)
  - Sensitive data (emails from gmail.com, banking sites, etc.)
  - HTTPS-only encrypted content

- **Storage:** Local to device (IndexedDB or SQLite), never sent raw

### 3. Segment Creation Eligibility
Browser generates segment **candidates** when:
- User has visited 5+ pages in a 7-day window
- Pages contain intent signals (product pages, comparison sites, research, etc.)
- Confidence score ≥ 0.70

Segments are created by AI analysis, not automatically.

### 4. Real-Time Payout Notifications
When a data segment (derived from user's behavior) is purchased:

```
Marketplace Smart Contract executes buySegment()
  ├─ Sends BID payout to usersPoolWallet
  ├─ Sends ASK spread to brokerWallet
  └─ Emits PayoutEvent(segmentId, users, amount)

Browser listens for PayoutEvent on zkSync Era
  → Notification: "Your browsing data earned 25 PAT"
  → Display in browser UI
  → Update total earned balance
```

**Payout flow:**
```
Individual User A: 15 PAT ← From segment (pooled with other users)
Individual User B: 10 PAT ← From same segment
...
usersPoolWallet receives: 70 PAT (BID from 100 PAT sale)
  → Smart contract tracks per-user contribution
  → Users claim earnings from pool
```

---

## User Flow

### Setup (First Time)
```
1. Download PAT Browser
2. Launch → Welcome screen
3. Connect Web3 wallet
   - Choose wallet provider
   - Approve wallet connection
   - Sign message (prove ownership)
4. Approve payout address
   - Confirm wallet address
   - Understand privacy policy
5. Start browsing
   - Browser begins tracking behavior
   - Notify user: "Your browsing data is being collected"
```

### Daily Usage
```
1. User browses normally (no ads, no popups interrupting)
2. Browser collects behavior locally
3. AI analysis periodically (nightly) detects intent signals
4. Segments created and submitted to marketplace
   - User sees notification: "New data segment created: PURCHASE_INTENT (7D, 0.75)"
5. Consumer purchases segment at ASK price
6. User receives notification: "Earned 15 PAT from browsing data sale"
7. Payout accumulates in usersPoolWallet (smart contract)
8. User can claim payouts anytime (withdrawal to wallet)
```

### Claim Earnings
```
Browser UI: "Earnings: 127.5 PAT"
User clicks "Claim" button
  ↓
Sign transaction (wallet approval required)
  ↓
User receives PAT in wallet
  ↓
Balance resets to 0
```

---

## Smart Contract Integration

### Events Browser Listens For
```solidity
event PayoutEvent(
  bytes32 indexed segmentId,
  address indexed usersPoolWallet,
  uint256 amount,
  uint256 timestamp
);

event SegmentCreated(
  bytes32 indexed segmentId,
  string segmentType,
  string timeWindow,
  uint256 confidence,
  uint256 askPrice
);
```

### Wallet Requirements
- **Payout wallet address:** Where user receives PAT (can be different from connected wallet)
- **Signing permissions:**
  - Sign message (prove ownership, one-time)
  - Approve withdrawal transactions (requires signature per claim)
- **No gas fees for tracking:** Browser behavior tracking is off-chain, no transactions

### On-Chain Claims
When user clicks "Claim," browser:
1. Reads usersPoolWallet balance for user
2. Prepares transaction: `withdrawEarnings(amount)`
3. User signs transaction
4. Transaction submitted to zkSync Era
5. Earnings transferred to user's wallet
6. Browser updates UI: balance = 0

---

## Implementation Priorities for Opus

### Phase 1: Browser Infrastructure
1. **Fork Chromium or use Tauri + Web technologies**
   - Tauri (Rust + web) recommended for cross-platform (Windows/Mac/Linux)
   - Lighter weight than Electron
   - Better privacy (local data storage)

2. **Wallet connection module**
   - Integrate ethers.js or web3.js
   - Support MetaMask + WalletConnect injected provider
   - Persist wallet address securely (encrypted local storage)

3. **Local behavior tracking**
   - Track tab activity (URL, time, title)
   - Store in IndexedDB or local SQLite
   - No PII collection (filter sensitive domains)
   - No form input logging

### Phase 2: AI Integration Bridge
1. **Data export pipeline**
   - Batch browser behavior data (every 6 hours)
   - Send to AI ingestion system via secure API
   - Receive segment creation notifications

2. **Segment creation listener**
   - Subscribe to marketplace API: "segments created from my data"
   - Display in browser UI

### Phase 3: Smart Contract Integration
1. **zkSync Era RPC connection**
   - Connect to zkSync Era mainnet
   - Listen for PayoutEvent emissions
   - Filter events for connected wallet address

2. **Real-time notifications**
   - Show payout alerts in browser
   - Update earnings balance UI
   - Trigger sound/desktop notification (optional)

3. **Claim functionality**
   - Read usersPoolWallet balance
   - Sign withdrawal transaction
   - Submit to smart contract
   - Update UI on confirmation

### Phase 4: UI/UX
1. **Dashboard**
   - Total earnings (PAT)
   - Segments created this month
   - Recent payouts (last 10)
   - Wallet connection status

2. **Settings**
   - Change payout wallet address
   - Privacy settings (pause tracking, exclude domains)
   - Notification preferences

3. **Privacy transparency**
   - Show what data is being tracked
   - Allow users to delete local data
   - Export data (GDPR compliance)

---

## Data Flow Summary

```
User Browser
  ↓ (continuous tracking)
Local behavior data
  ↓ (batch export, 6 hours)
AI Ingestion API
  ↓ (detect intent signals)
Data Segments
  ↓ (submit to marketplace)
Marketplace Smart Contract
  ↓ (consumer buys segment)
PayoutEvent emitted
  ↓ (browser listens)
Browser UI updated
  ↓ (notification)
User sees: "Earned 15 PAT"
```

---

## Key Differences: Browser vs. Ingestion

| Aspect | User Browser | AI Ingestion |
|--------|--------------|--------------|
| **Component** | User application | Backend service |
| **Purpose** | Browse normally + collect behavior | Analyze behavior → create segments |
| **Web3** | ✅ Wallet connected | ❌ No wallet (uses API key) |
| **Payouts** | ✅ Receives earnings | ❌ N/A |
| **Realtime** | ✅ Live notifications | ❌ Batch processing |
| **Storage** | Local (IndexedDB) | Cloud (centralized) |

---

## Security & Privacy Considerations

1. **Local-first approach** – Behavior data stays on user device until batch export
2. **No personal data** – Filter credit cards, passwords, emails
3. **Encrypted storage** – Wallet keys stored encrypted locally
4. **User consent** – Clear privacy policy before tracking starts
5. **Transparent tracking** – UI shows what domains are tracked/excluded
6. **Graceful degradation** – Browser works without wallet (no payouts, but still useful)

---

## Notes

- Browser is **separate from marketplace** (different codebases)
- Marketplace broker controls segment pricing; browser users don't
- Users earn passive income from behavior; no ads or interruptions
- PAT token is earned (not purchased) through normal usage
- Phases 1-4 marketplace progression is transparent to browser users

---

**Ready for Opus:** Yes. This handoff clarifies:
- Browser is real user application (not autonomous agent)
- Web3 wallet integration for payout notifications
- Smart contract event listening for earnings
- Data flow from browser → AI ingestion → marketplace
- Implementation priorities for Tauri/Chromium + ethers.js
