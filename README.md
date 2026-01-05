# Project Overview

Welcome to the **PAT Project** repository.  This project revolves around three
complementary pillars designed to create a cohesive ecosystem for token economics,
intelligent web agents and high‑quality data exchange:

1. **PAT coin launch** – an ERC‑20 compatible token on **zkSync Era** that will
   power the ecosystem.  PAT has a total supply of **555,222,888 tokens** with
   the following allocation: 10% ICO, 10% Team (6‑12 month linear vesting),
   30% Ecosystem and 50% Treasury.  The token is classified as a **utility token**
   under **Wyoming (USA)** jurisdiction.

2. **AI browser for data ingestion** – an autonomous browser agent powered by
   **Qwen** that navigates websites, interacts with forms and extracts
   **web browsing intent signals**.  The agent creates data segments that feed
   into the marketplace.  Building such an agent involves defining its purpose,
   designing its architecture (decision logic, perception and action modules),
   choosing the right AI models, developing perception/action modules, training
   and testing, and deploying as a browser extension.

3. **Data performance marketplace** – a platform that allows data providers to
   monetize high‑quality datasets and data consumers to discover and purchase
   data.  Data is stored on **centralized cloud** infrastructure with on‑chain
   pricing and settlement via PAT tokens on zkSync Era.  The marketplace
   connects providers and consumers in a secure environment with quality metrics,
   governance and transparent pricing.

## Repository Structure

```
NIMBUS/
├── contracts/                 # Smart contracts (Solidity + Hardhat)
│   ├── contracts/
│   │   ├── PAT.sol           # ERC-20 token with vesting
│   │   └── DataMarketplace.sol  # UUPS upgradeable marketplace
│   └── test/                 # Contract test suite
├── browser/                  # AI browser agent (Python + Playwright)
│   └── src/
│       ├── agent.py          # Browser automation agent
│       ├── qwen_client.py    # Qwen LLM API client
│       └── marketplace_client.py  # Marketplace API client
├── pat_coin_launch.md        # Token launch plan and tokenomics
├── ai_browser_ingestion.md   # Browser architecture spec
├── data_performance_marketplace.md  # Marketplace design doc
└── whitepaper_outline.md     # Investor whitepaper outline
```

### Quick Start

**Smart Contracts:**
```bash
cd contracts
npm install
npx hardhat test
```

**Browser Agent:**
```bash
cd browser
pip install -r requirements.txt
python -m src.agent
```

## Contributing

These documents are intended to serve as a foundation for a software‑developer
agent.  Each file outlines tasks, requirements and milestones for its
corresponding pillar.  Contributions should be made via issues and pull
requests.  As the project evolves, feel free to expand these documents,
add diagrams or code samples and update tasks accordingly.
