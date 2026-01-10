# PAT Browser – Chromium Fork for Data Monetization

This document describes the design and implementation of **PAT Browser**, a
Chromium-based web browser that enables users to monetize their browsing data
through the PAT marketplace. The browser passively ingests browsing behavior,
uses a hybrid Rasa + Mistral + DeepSeek pipeline to identify intent signals,
and creates tradeable data segments.

## Technical Specifications

| Component | Technology |
|-----------|------------|
| **Base** | Ungoogled-Chromium (fork) |
| **AI Engine** | Rasa Open Source + Mistral-small + DeepSeek (hybrid) |
| **Data Collected** | URLs, time on page, scroll depth, clicks, search queries, form inputs |
| **Privacy** | Incognito mode excludes all data collection |
| **Output** | Intent signal data segments |
| **Settlement** | PAT tokens on zkSync Era |

## 1. Concept & Motivation

Users generate valuable browsing data every day but receive nothing in return.
Advertisers and data brokers profit from this data while users bear the privacy
costs. PAT Browser flips this model:

- **User owns their data** – All browsing data stays local until the user
  explicitly chooses to monetize it.
- **Transparent collection** – Users see exactly what data is collected and can
  opt out per-site or globally.
- **Fair compensation** – Users earn PAT tokens when their data segments are
  purchased on the marketplace.
- **Privacy by default** – Incognito mode disables all data collection.

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PAT Browser (Ungoogled-Chromium)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Chromium  │  │    Data     │  │   Intent    │  │    PAT Wallet &     │ │
│  │   Renderer  │──│  Collector  │──│   Router    │──│  Marketplace Client │ │
│  │             │  │             │  │ (FastAPI)   │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         │               │               │                     │             │
│         ▼               ▼               ▼                     ▼             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        Local Encrypted Storage                          ││
│  │  (Browsing data, intent signals, segments awaiting upload)              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │      PAT Marketplace API        │
                    │      (zkSync Era Settlement)    │
                    └─────────────────────────────────┘
```

### Core Components

1. **Chromium Renderer** – Ungoogled-Chromium rendering engine (no Google telemetry)
   with hooks for data collection events.

2. **Data Collector** – Native C++ component that captures browsing events:
   - Page navigation (URL, timestamp, referrer)
   - Time on page and engagement metrics
   - Scroll depth and viewport interactions
   - Click events (anonymized element selectors)
   - Search queries (from search engine URLs)
   - Form inputs (sanitized, no passwords/PII)

3. **Intent Router (FastAPI)** – Hybrid inference pipeline:
   - **Rasa Open Source** – Deterministic classifier for known intents
   - **Mistral-small** – Semantic scorer via vLLM
   - **DeepSeek** – Long-chain reasoning for ambiguous cases (gated)
   - Gating policy escalates when confidence < 0.70

4. **PAT Wallet & Marketplace Client** – Integrated wallet for:
   - Managing PAT token balance
   - Viewing pending/sold data segments
   - Configuring monetization preferences
   - Withdrawing earnings to external wallet

## 3. Data Collection Specification

### Collected Data Points

| Data Type | Description | Storage |
|-----------|-------------|---------|
| **URLs** | Full URL of visited pages | Local, hashed for segments |
| **Time on Page** | Duration in seconds | Local |
| **Scroll Depth** | Maximum scroll percentage | Local |
| **Clicks** | Anonymized element type + position | Local |
| **Search Queries** | Extracted from search engine URLs | Local |
| **Form Inputs** | Field types only, no values (except search) | Local |
| **Referrer Chain** | How user arrived at page | Local |
| **Timestamps** | UTC timestamps for all events | Local |

### Excluded Data (Never Collected)

- Passwords and authentication tokens
- Credit card numbers and financial data
- Personal identifiable information (names, emails, addresses)
- Private/Incognito browsing sessions
- Sites on user's exclusion list
- Healthcare and banking sites (default excluded)

### Privacy Controls

```
┌─────────────────────────────────────────────────────┐
│              PAT Browser Privacy Settings            │
├─────────────────────────────────────────────────────┤
│ ☑ Enable data collection (earn PAT tokens)          │
│ ☑ Exclude Incognito mode                            │
│ ☑ Exclude banking/financial sites                   │
│ ☑ Exclude healthcare sites                          │
│ ☐ Exclude social media                              │
│                                                      │
│ Site-specific exclusions:                           │
│   [example.com] [Remove]                            │
│   [private-site.org] [Remove]                       │
│   [+ Add site]                                       │
│                                                      │
│ [View My Data] [Export Data] [Delete All Data]      │
└─────────────────────────────────────────────────────┘
```

## 4. Intent Signal Detection

The hybrid Rasa + Mistral + DeepSeek pipeline processes raw browsing events:

### Signal Types

| Intent Type | Indicators | Confidence Factors |
|-------------|------------|-------------------|
| **PURCHASE_INTENT** | Product pages, cart, checkout, price comparisons | Time on page, return visits, click depth |
| **RESEARCH_INTENT** | Articles, guides, documentation, tutorials | Scroll depth, time reading, bookmarks |
| **COMPARISON_INTENT** | Review sites, "vs" searches, spec comparisons | Multiple product views, tab switches |
| **ENGAGEMENT_INTENT** | Comments, shares, likes, form submissions | Interaction frequency, session length |
| **NAVIGATION_INTENT** | Category browsing, search refinement | Click patterns, query modifications |

### Hybrid Classification Pipeline

```
Events → Rasa Open Source (deterministic) → Mistral (semantic scorer) → Gating Policy
                                                                      │
                                        ┌─────────────────────────────┴───┐
                                        │ If confidence < 0.70            │
                                        │ If high-risk + conf < 0.85      │
                                        │ If top-2 margin < 0.10          │
                                        └─────────────────────────────────┘
                                                      │
                                                      ▼
                                              DeepSeek (reasoning)
                                                      │
                                                      ▼
                                              Final Intent Decision
```

### Segment Format

```json
{
  "segment_id": "PURCHASE_INTENT|7D|0.75-0.90",
  "segment_type": "PURCHASE_INTENT",
  "time_window_days": 7,
  "confidence_range": { "min": 0.75, "max": 0.90 },
  "signal_count": 847,
  "categories": ["electronics", "laptops"],
  "created_at": "2024-01-15T10:30:00Z",
  "user_id_hash": "0x7f3a...",
  "price_pat": 150.00
}
```

## 5. Building from Source

### Prerequisites

- Linux (Ubuntu 20.04+ recommended) or macOS
- 100GB+ free disk space
- 16GB+ RAM (32GB recommended)
- Python 3.8+
- Git, curl, lsb_release

### Clone and Setup

```bash
# Install depot_tools
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH="$PATH:$(pwd)/depot_tools"

# Create working directory
mkdir pat-browser && cd pat-browser

# Fetch Ungoogled-Chromium source
fetch --nohooks chromium
cd src

# Checkout stable branch
git checkout tags/120.0.6099.109 -b pat-browser

# Apply PAT Browser patches
git apply ../patches/pat-data-collector.patch
git apply ../patches/pat-intent-router.patch
git apply ../patches/pat-wallet-ui.patch

# Install dependencies
gclient sync
./build/install-build-deps.sh

# Configure build
gn gen out/Release --args='
  is_official_build=true
  is_debug=false
  target_cpu="x64"
  proprietary_codecs=true
  ffmpeg_branding="Chrome"
  enable_pat_data_collection=true
  pat_inference_endpoint="http://localhost:8000/api/infer/intent"
'

# Build (takes 2-6 hours depending on hardware)
autoninja -C out/Release chrome
```

### Build Outputs

```
out/Release/
├── chrome                    # Main browser executable
├── chrome_sandbox            # Sandbox helper
├── libpat_collector.so       # Data collection library
├── libpat_inference.so       # Intent router client library
├── resources/
│   └── pat_wallet/           # Wallet UI resources
└── locales/                  # Localization files
```

## 6. Project Structure

```
browser/
├── patches/
│   ├── pat-data-collector.patch    # Chromium patches for data collection
│   ├── pat-intent-router.patch     # FastAPI inference integration
│   └── pat-wallet-ui.patch         # Wallet and settings UI
├── src/
│   ├── collector/
│   │   ├── browsing_data_collector.cc
│   │   ├── browsing_data_collector.h
│   │   ├── event_types.h
│   │   └── privacy_filter.cc
│   ├── inference/
│   │   ├── intent_analyzer.cc
│   │   ├── intent_analyzer.h
│   │   ├── mistral_client.cc
│   │   └── segment_builder.cc
│   ├── wallet/
│   │   ├── pat_wallet_controller.cc
│   │   ├── marketplace_client.cc
│   │   └── ui/
│   │       ├── wallet_page.html
│   │       ├── settings_page.html
│   │       └── data_viewer.html
│   └── storage/
│       ├── encrypted_store.cc
│       └── segment_cache.cc
├── tests/
│   ├── collector_test.cc
│   ├── intent_analyzer_test.cc
│   └── privacy_filter_test.cc
└── BUILD.gn
```

## 7. Native Components

### Data Collector (C++)

```cpp
// browsing_data_collector.h
namespace pat {

struct BrowsingEvent {
  enum Type {
    PAGE_LOAD,
    PAGE_UNLOAD,
    SCROLL,
    CLICK,
    FORM_SUBMIT,
    SEARCH_QUERY
  };

  Type type;
  std::string url_hash;
  base::Time timestamp;
  base::TimeDelta duration;
  double scroll_depth;
  std::string element_type;
  std::string search_query;  // Only for SEARCH_QUERY type
};

class BrowsingDataCollector {
 public:
  static BrowsingDataCollector* GetInstance();

  void OnPageLoad(const GURL& url, content::WebContents* contents);
  void OnPageUnload(const GURL& url, base::TimeDelta time_on_page);
  void OnScroll(double depth_percentage);
  void OnClick(const std::string& element_selector);
  void OnSearchQuery(const std::string& query);

  bool IsCollectionEnabled() const;
  bool IsIncognito(content::WebContents* contents) const;
  bool IsExcludedSite(const GURL& url) const;

 private:
  std::unique_ptr<PrivacyFilter> privacy_filter_;
  std::unique_ptr<EncryptedStore> local_store_;
};

}  // namespace pat
```

### Intent Analyzer (FastAPI Router Client)

```cpp
// intent_analyzer.h
namespace pat {

enum class IntentType {
  PURCHASE_INTENT,
  RESEARCH_INTENT,
  COMPARISON_INTENT,
  ENGAGEMENT_INTENT,
  NAVIGATION_INTENT
};

struct IntentSignal {
  IntentType type;
  double confidence;
  std::vector<std::string> categories;
  base::Time detected_at;
  std::string model_used;  // "mistral" or "deepseek"
};

class IntentAnalyzer {
 public:
  explicit IntentAnalyzer(const std::string& router_endpoint);

  // Analyze recent browsing events and detect intent signals
  std::vector<IntentSignal> AnalyzeEvents(
      const std::vector<BrowsingEvent>& events);

  // Build a data segment from detected signals
  DataSegment BuildSegment(
      const std::vector<IntentSignal>& signals,
      int time_window_days,
      double confidence_min,
      double confidence_max);

 private:
  std::string router_endpoint_;
  std::unique_ptr<HttpClient> http_client_;
};

}  // namespace pat
```

## 8. Security Considerations

### Data Protection

1. **Local Encryption** – All browsing data encrypted at rest using AES-256-GCM
   with a key derived from user's PAT wallet password.

2. **Minimal Data Transmission** – Only aggregated segments are uploaded to
   the marketplace, never raw browsing history.

3. **Hash-based Anonymization** – URLs and identifiers are hashed before
   segment creation; original values never leave the device.

4. **Secure Inference** – Intent router runs locally or via TLS 1.3 with
   certificate pinning.

### User Controls

1. **Granular Opt-out** – Per-site, per-category, or global data collection
   toggle.

2. **Data Viewer** – Built-in UI to see all collected data before any upload.

3. **Delete Anytime** – One-click deletion of all local data.

4. **Export** – Download all data in machine-readable format (JSON).

## 9. Development Roadmap

### Phase 1: Foundation
- [x] Set up Ungoogled-Chromium build environment
- [x] Implement basic data collector hooks
- [x] Create local encrypted storage
- [x] Build privacy filter and exclusion system

### Phase 2: AI Integration
- [x] Implement FastAPI intent router
- [x] Integrate Mistral + DeepSeek via vLLM
- [x] Implement gating policy for escalation
- [x] Build segment creation pipeline

### Phase 3: Marketplace Integration
- [ ] Implement PAT wallet UI
- [ ] Build marketplace API client
- [ ] Add segment upload and pricing
- [ ] Integrate zkSync Era for settlements

### Phase 4: Polish & Launch
- [ ] Security audit
- [ ] Performance optimization
- [ ] Cross-platform builds (Linux, macOS, Windows)
- [ ] Beta release

## 10. Next Steps

1. **Set up build environment** – Install depot_tools and fetch Ungoogled-Chromium
2. **Create initial patches** – Hook into Chromium's navigation and event system
3. **Implement data collector** – Start with URL and time-on-page tracking
4. **Build privacy filter** – Implement incognito detection and site exclusions
5. **Deploy intent router** – Run FastAPI with vLLM (Mistral + DeepSeek)

See `contracts/` for the PAT token smart contract implementation.
