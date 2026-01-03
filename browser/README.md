# PAT AI Browser Agent

A Qwen-powered browser agent for collecting web browsing intent signals.

## Overview

This agent autonomously browses the web to detect and extract browsing intent
signals that are packaged as data segments for the PAT marketplace.

## Features

- **Qwen-powered analysis**: Uses Alibaba's Qwen LLM for intelligent intent detection
- **Playwright automation**: Headless browser automation for reliable web scraping
- **Intent classification**: Detects purchase, research, comparison, and engagement intents
- **Segment creation**: Packages signals into marketplace-ready data segments
- **Marketplace integration**: Submits segments to the PAT marketplace API

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required environment variables:
- `QWEN_API_KEY`: Your Qwen API key from Alibaba Cloud
- `PAT_MARKETPLACE_KEY`: API key for the PAT marketplace

## Usage

### Basic Usage

```python
import asyncio
from src import BrowserAgent, QwenAPIClient, IntentType

async def main():
    # Initialize
    qwen = QwenAPIClient()
    agent = BrowserAgent(qwen)

    # Start browser
    await agent.start(headless=True)

    # Browse and collect signals
    urls = ["https://example.com/product/laptop"]
    signals = await agent.browse_urls(urls)

    # Create data segment
    segment = agent.create_segment(
        segment_type=IntentType.PURCHASE_INTENT,
        time_window_days=7,
        confidence_min=0.70,
        confidence_max=0.90
    )

    # Export for marketplace
    agent.export_segments([segment], "output.json")

    await agent.stop()

asyncio.run(main())
```

### Running the Demo

```bash
python -m src.agent
```

## Data Segments

Segments are identified by:
- **Type**: PURCHASE_INTENT, RESEARCH_INTENT, COMPARISON_INTENT, etc.
- **Time Window**: How recent the signals are (e.g., 7D = 7 days)
- **Confidence Range**: The confidence score range (e.g., 0.70-0.85)

Example segment ID: `PURCHASE_INTENT|7D|0.70-0.85`

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Browser Agent  │────▶│   Qwen Client   │────▶│   Marketplace   │
│  (Playwright)   │     │   (Analysis)    │     │   (zkSync Era)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                       │
        ▼                        ▼                       ▼
   Navigate &              Detect Intent           Submit Segment
   Extract DOM             Signals                 for Trading
```

## Testing

```bash
pytest tests/
```

## License

MIT
