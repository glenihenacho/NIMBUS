# PAT Ecosystem

A Web3 data monetization platform on **zkSync Era** enabling users to earn PAT tokens from their browsing behavior.

## Architecture

| Component | Description |
|-----------|-------------|
| **PAT Token** | ERC-20 utility token (555,222,888 supply) with team vesting |
| **Data Marketplace** | UUPS upgradeable atomic settlement for intent signal segments |
| **Intent Detection** | Hybrid classifier: Rasa Open Source + Mistral-small + DeepSeek (gated) |
| **User Browser** | Ungoogled-Chromium with custodial embedded wallet |

**Jurisdiction:** Wyoming DAO LLC

## Repository

```
contracts/
  contracts/PAT.sol              # ERC-20 token with allocation + vesting
  contracts/DataMarketplace.sol  # Atomic settlement marketplace (UUPS)
  deploy/deploy.ts               # zkSync Era deployment script
  test/                          # Hardhat test suite

browser/
  src/router.py                  # FastAPI inference router
  src/llm_clients.py             # vLLM clients (Mistral + DeepSeek)
  src/schema.py                  # Canonical event schema (v1)
  src/agent.py                   # Browser automation + segment creation
```

## Intent Detection Stack

```
┌─────────────────────┐
│  User Browser       │  Ungoogled-Chromium + Canonical Events
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  RudderStack        │  Event transport + schema validation
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  FastAPI Router     │  Single inference entry point
├─────────────────────┤
│  Rasa + Mistral     │  Cheap classifier (hybrid)
│  Gating Policy      │  Escalate if confidence < 0.70
│  DeepSeek           │  Long-chain reasoning (gated)
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  Data Segments      │  Aggregate intents → marketplace
└─────────┬───────────┘
          ↓
┌─────────────────────┐
│  PAT Marketplace    │  Atomic settlement (zkSync Era)
└─────────────────────┘
```

## Quick Start

**Contracts:**
```bash
cd contracts && npm install && npx hardhat test
```

**Intent Router:**
```bash
cd browser && pip install -r requirements.txt && python -m src.router
```

## Token Allocation

| Category | % | Tokens | Vesting |
|----------|---|--------|---------|
| Treasury | 50% | 277,611,444 | None |
| Ecosystem | 30% | 166,566,866 | None |
| ICO | 10% | 55,522,289 | None |
| Team | 10% | 55,522,289 | 6-12 months |

## Documentation

- [pat_coin_launch.md](pat_coin_launch.md) - Token launch plan
- [ai_browser_ingestion.md](ai_browser_ingestion.md) - Browser architecture
- [data_performance_marketplace.md](data_performance_marketplace.md) - Marketplace design
- [whitepaper_outline.md](whitepaper_outline.md) - Investor whitepaper
