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

### 1. Custodial Embedded Wallet

**Browser owns private keys locally; you (Wyoming DAO LLC) are the custodian.**

**Onboarding (First Time):**
```
1. User launches browser
2. Create account:
   ├─ Set username
   ├─ Set password
   └─ Browser generates private key locally
3. Derive public address from private key
4. Set withdrawal wallet address (one-time, fixed)
   └─ Where PAT payouts are sent
5. Done - never asks again
```

**Local Storage (Encrypted):**
- `encrypted_private_key` = AES-256-GCM(privateKey, PBKDF2(password))
- `user_address` = public address derived from key
- `withdrawal_wallet` = fixed address for payouts (never changes)
- Only user's password can decrypt private key

**User Experience:**
- ✅ No MetaMask popups during normal use
- ✅ No signature requests while browsing
- ✅ Automatic nightly payouts (user doesn't do anything)
- ✅ Manual claim option anytime (user clicks "Claim Now")

**Password Recovery:**
- User forgets password → Click "Forgot password"
- Email verification → You generate new encrypted key
- User sets new password → Browser re-encrypts and stores locally
- Seamless recovery (no loss of address or earnings)

**Network:** zkSync Era mainnet

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

### 4. Automatic + Manual Payout Claims

**Earnings accumulation:**
```
Marketplace Smart Contract executes buySegment()
  ├─ Sends 70 PAT (BID) → usersPoolWallet
  ├─ Sends 30 PAT (spread) → brokerWallet
  └─ Emits PayoutEvent(segmentId, amount)

Smart contract tracks per-user earnings in mapping:
  mapping(address => uint256) userEarnings

Browser listens for PayoutEvent
  → Update UI: "Your data earned 15 PAT"
  → Add to balance: total earned = 15 PAT
```

**Nightly Auto-Claim (Automatic):**
```
Every night at 2 AM UTC:
  1. Browser checks accumulated earnings
  2. Calls withdrawEarnings(amount) automatically
  3. Private key decrypted (using stored password)
  4. Transaction signed + submitted to zkSync Era
  5. PAT transferred to withdrawal_wallet
  6. UI updates: "Claimed 45 PAT overnight"
```

**Manual Claim (On-Demand):**
```
User sees: "Earnings: 127.50 PAT"
User clicks: "Claim Now" button
  ├─ Browser decrypts private key
  ├─ Signs: withdrawEarnings(127.50) transaction
  ├─ Submits to zkSync Era
  └─ PAT arrives in withdrawal_wallet within seconds

UI updates: "Earnings: 0 PAT" (reset after claim)
```

**No gas fees:** Wyoming DAO LLC covers gas for auto-claims and manual claims (cost of user acquisition).

**Fixed withdrawal address:** All earnings go to same wallet address (set at signup, never changes).

---

## User Flow

### Setup (First Time)
```
1. Download PAT Browser
2. Launch → Welcome screen
3. Create account:
   - Enter username
   - Set password
   - Browser generates private key locally (encrypted)
4. Set withdrawal wallet address:
   - Paste your zkSync Era wallet address (e.g., 0x123...)
   - "PAT will be sent here automatically"
   - Confirm (cannot be changed)
5. Start browsing:
   - Browser begins tracking behavior
   - UI: "Your data is being collected and monetized"
   - No further setup needed
```

### Daily Usage
```
1. User opens browser and browses normally
   - No ads, no interruptions
   - No wallet popups
2. Browser collects behavior locally (encrypted)
3. AI analysis (nightly) detects intent signals
4. Data segments created and submitted to marketplace
   - User sees notification: "New segment created: PURCHASE_INTENT (7D, 0.75)"
5. Consumer purchases segment on marketplace
6. Smart contract settles atomically:
   - 70 PAT → usersPoolWallet
   - 30 PAT → brokerWallet (your spread)
7. Browser listens for PayoutEvent
   - Notification: "Your data earned 15 PAT"
   - Earnings balance increases: 15 PAT
8. Every night at 2 AM UTC:
   - Browser auto-claims accumulated earnings
   - PAT automatically sent to withdrawal_wallet
   - Notification: "Auto-claimed 45 PAT overnight"
```

### Manual Claim (On-Demand)
```
User sees in dashboard:
  Earnings: 127.50 PAT [Claim Now] button

User clicks "Claim Now":
  ├─ Browser decrypts private key (using password)
  ├─ Signs: withdrawEarnings(127.50) transaction
  ├─ Submits to zkSync Era
  └─ PAT arrives in withdrawal_wallet (~15 seconds)

Dashboard updates:
  Earnings: 0 PAT

History shows:
  "Claimed 127.50 PAT at 3:45 PM"
```

---

## Smart Contract Integration

### Smart Contract Functions

**Earnings tracking (on-chain):**
```solidity
mapping(address => uint256) public userEarnings;

function recordPayout(address user, uint256 amount) internal {
    userEarnings[user] += amount;
    emit PayoutRecorded(user, amount);
}

function withdrawEarnings(uint256 amount) external {
    require(userEarnings[msg.sender] >= amount, "Insufficient balance");
    userEarnings[msg.sender] -= amount;
    PAT.transfer(msg.sender, amount);
    emit Withdrawal(msg.sender, amount);
}
```

### Events Browser Listens For
```solidity
event PayoutRecorded(
  address indexed user,
  uint256 amount,
  bytes32 indexed segmentId,
  uint256 timestamp
);

event Withdrawal(
  address indexed user,
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

### Browser Claims (No Gas Fees)
Wyoming DAO LLC covers all gas fees for:
- **Auto-claim transactions** (every night)
- **Manual claim transactions** (on-demand)

This is a user acquisition cost—users should never pay gas.

**Implementation options:**
- Option A: Relayer/keeper service signs transactions for users
- Option B: Meta-transactions (EIP-2771) with sponsor
- Option C: Flashbots Relay (MEV-free, sponsored gas)

**Auto-claim mechanism:**
- Nightly job reads user's `userEarnings[address]` balance
- If balance > 0, calls `withdrawEarnings(balance)`
- Relayer/keeper signs and submits
- PAT arrives in withdrawal_wallet (user's fixed address)

---

## Implementation Priorities for Opus

### Phase 1: Browser Infrastructure + Custodial Wallet

1. **Browser engine: Ungoogled-Chromium fork (recommended)**
   - Fork of Chromium with all Google integration removed
   - Privacy-first (no telemetry, no tracking)
   - Full browser experience: tabs, bookmarks, history, extensions
   - Cross-platform (Windows/Mac/Linux)
   - Fast, reliable, familiar UX
   - Local data storage via SQLite (encrypted)

2. **Custodial wallet module**
   - Generate ed25519 keypair on signup
   - Encrypt private key: AES-256-GCM(key, PBKDF2(password, 100k iterations))
   - Store encrypted key locally (never leaves device)
   - Derive public address from private key
   - Sign transactions using decrypted key

3. **Account system**
   - Username + password authentication (local)
   - Password hashing: PBKDF2/bcrypt for stored credentials
   - Password recovery: Email verification → regenerate encrypted key
   - Withdrawal wallet address (immutable, set at signup)

4. **Local behavior tracking**
   - Track tab activity (URL, time spent, title)
   - Store in local SQLite database
   - No PII collection (filter sensitive domains: gmail.com, banking, etc.)
   - No form input logging (except button clicks)
   - Behavior data encrypted at rest

### Phase 2: AI Integration Bridge
1. **Data export pipeline**
   - Batch browser behavior data (every 6 hours)
   - Send to AI ingestion system via secure API
   - Receive segment creation notifications

2. **Segment creation listener**
   - Subscribe to marketplace API: "segments created from my data"
   - Display in browser UI

### Phase 3: Smart Contract Integration + Auto-Claims
1. **zkSync Era RPC connection**
   - Connect to zkSync Era mainnet
   - Listen for `PayoutRecorded` events
   - Filter events for user's address
   - Track off-chain balance (accumulate earnings)

2. **Real-time notifications**
   - Show payout alerts in browser
   - Update earnings balance UI
   - Trigger desktop notification (optional)

3. **Manual claim functionality**
   - User clicks "Claim Now" button
   - Browser decrypts private key (user enters password again)
   - Sign: `withdrawEarnings(amount)` transaction
   - Submit to zkSync Era
   - Update UI on confirmation
   - Show transaction hash/receipt

4. **Automatic nightly claims**
   - Nightly job (2 AM UTC) triggered by OS scheduler
   - Read accumulated balance
   - If balance > 0, sign and submit `withdrawEarnings(balance)`
   - Use relayer/keeper service (Wyoming DAO LLC sponsored)
   - Log transaction in UI history
   - Notification: "Auto-claimed X PAT overnight"

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

**Architecture & Trust Model:**
- Browser is **separate from marketplace** (different codebases)
- Marketplace broker controls segment pricing; browser users don't
- Users earn passive income from behavior; no ads or interruptions
- PAT token is earned (not purchased) through normal usage
- Phases 1-4 marketplace progression is transparent to browser users

**Custodial Wallet Model:**
- **You (Wyoming DAO LLC) are the custodian** – You control private key encryption/recovery
- **Private keys stay local** – Never transmitted to servers (only during password recovery)
- **No MetaMask dependency** – Seamless UX, automatic payouts
- **Email-based recovery** – Users can recover if password is forgotten
- **Fixed withdrawal address** – Same wallet receives all payouts (immutable)
- **No gas fees for users** – Wyoming DAO LLC covers all transaction costs (relayer/keeper service)

**Regulatory Approach:**
- Initially operate under **Wyoming DAO LLC exemption** (no VASP registration yet)
- As platform scales, evaluate whether formal custodian registration is needed
- Maintain clear privacy policy: what data is tracked, how it's monetized, user controls

---

**Ready for Opus:** Yes. This handoff clarifies:
- Browser is real user application (not autonomous agent)
- **Custodial embedded wallet** (private keys local, you are custodian)
- Zero friction UX (no MetaMask, automatic payouts)
- Email-based password recovery (seamless account recovery)
- Manual + automatic claims (nightly auto-claim + on-demand claims)
- Fixed withdrawal address (set at signup, never changes)
- No gas fees for users (Wyoming DAO LLC covers via relayer)
- Data flow: Browser (track) → AI Ingestion (analyze) → Marketplace (sell) → Smart Contract (pay)
- Implementation: Ungoogled-Chromium fork + ethers.js + SQLite for local storage + custodial wallet
- Smart contract functions: `recordPayout()`, `withdrawEarnings()`, event listening
- Privacy-first: No Google telemetry, local-only behavior data, encrypted storage
