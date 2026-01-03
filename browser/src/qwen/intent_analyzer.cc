// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#include "browser/src/qwen/intent_analyzer.h"

#include "base/json/json_reader.h"
#include "base/logging.h"
#include "base/strings/stringprintf.h"
#include "browser/src/qwen/qwen_client.h"

namespace pat {

IntentAnalyzer::IntentAnalyzer() = default;

IntentAnalyzer::~IntentAnalyzer() {
  if (model_handle_) {
    QwenClient::UnloadModel(model_handle_);
    model_handle_ = nullptr;
  }
}

bool IntentAnalyzer::Initialize(const std::string& model_path) {
  LOG(INFO) << "PAT: Initializing Qwen intent analyzer...";

  model_handle_ = QwenClient::LoadModel(model_path);
  if (!model_handle_) {
    LOG(ERROR) << "PAT: Failed to load Qwen model from: " << model_path;
    return false;
  }

  is_ready_ = true;
  LOG(INFO) << "PAT: Qwen intent analyzer ready";
  return true;
}

bool IntentAnalyzer::IsReady() const {
  return is_ready_ && model_handle_ != nullptr;
}

std::vector<IntentSignal> IntentAnalyzer::AnalyzeEvents(
    const std::vector<BrowsingEvent>& events) {
  if (!IsReady()) {
    LOG(WARNING) << "PAT: Intent analyzer not ready";
    return {};
  }

  if (events.empty()) {
    return {};
  }

  // Build prompt from events
  std::string prompt = BuildPrompt(events);

  // Run inference
  std::string response = RunInference(prompt);

  // Parse response
  std::vector<IntentSignal> signals = ParseResponse(response);

  // Filter by confidence
  std::vector<IntentSignal> filtered;
  for (const auto& signal : signals) {
    if (signal.confidence_score >= min_confidence_) {
      filtered.push_back(signal);
    }
  }

  // Cache results
  cached_intents_ = filtered;

  return filtered;
}

std::vector<IntentSignal> IntentAnalyzer::AnalyzeTimeWindow(
    const std::vector<BrowsingEvent>& events,
    base::TimeDelta window) {
  // Filter events to time window
  base::Time cutoff = base::Time::Now() - window;

  std::vector<BrowsingEvent> windowed;
  for (const auto& event : events) {
    if (event.timestamp >= cutoff) {
      windowed.push_back(event);
    }
  }

  return AnalyzeEvents(windowed);
}

std::vector<IntentSignal> IntentAnalyzer::GetLatestIntents() const {
  return cached_intents_;
}

void IntentAnalyzer::ClearIntents() {
  cached_intents_.clear();
}

void IntentAnalyzer::SetMinConfidence(double threshold) {
  min_confidence_ = std::clamp(threshold, 0.0, 1.0);
}

void IntentAnalyzer::SetAnalysisInterval(base::TimeDelta interval) {
  analysis_interval_ = interval;
}

std::string IntentAnalyzer::BuildPrompt(
    const std::vector<BrowsingEvent>& events) {
  std::string prompt = R"(Analyze the following anonymized browsing events and detect user intent signals.

Events (hashed URLs, timestamps, and behaviors):
)";

  for (const auto& event : events) {
    std::string event_type;
    switch (event.type) {
      case BrowsingEventType::PAGE_LOAD:
        event_type = "PAGE_LOAD";
        break;
      case BrowsingEventType::PAGE_UNLOAD:
        event_type = "PAGE_UNLOAD";
        break;
      case BrowsingEventType::SCROLL:
        event_type = "SCROLL";
        break;
      case BrowsingEventType::CLICK:
        event_type = "CLICK";
        break;
      case BrowsingEventType::SEARCH_QUERY:
        event_type = "SEARCH";
        break;
      case BrowsingEventType::FORM_SUBMIT:
        event_type = "FORM";
        break;
    }

    prompt += base::StringPrintf(
        "- %s | scroll:%.0f%% | duration:%llds | element:%s | query:%s\n",
        event_type.c_str(),
        event.scroll_depth * 100,
        event.duration.InSeconds(),
        event.element_type.c_str(),
        event.search_query.c_str());
  }

  prompt += R"(

Respond with JSON array of detected intents:
[{"type": "PURCHASE_INTENT|RESEARCH_INTENT|COMPARISON_INTENT|ENGAGEMENT_INTENT|NAVIGATION_INTENT",
  "confidence": 0.0-1.0,
  "category": "category_name"}]
)";

  return prompt;
}

std::string IntentAnalyzer::RunInference(const std::string& prompt) {
  if (!model_handle_) {
    return "[]";
  }

  return QwenClient::Infer(model_handle_, prompt);
}

std::vector<IntentSignal> IntentAnalyzer::ParseResponse(
    const std::string& response) {
  std::vector<IntentSignal> signals;

  auto parsed = base::JSONReader::Read(response);
  if (!parsed || !parsed->is_list()) {
    LOG(WARNING) << "PAT: Failed to parse Qwen response";
    return signals;
  }

  for (const auto& item : parsed->GetList()) {
    if (!item.is_dict()) continue;

    const auto& dict = item.GetDict();

    IntentSignal signal;
    signal.detected_at = base::Time::Now();

    // Parse type
    const std::string* type = dict.FindString("type");
    if (type) {
      if (*type == "PURCHASE_INTENT") {
        signal.type = IntentType::PURCHASE_INTENT;
      } else if (*type == "RESEARCH_INTENT") {
        signal.type = IntentType::RESEARCH_INTENT;
      } else if (*type == "COMPARISON_INTENT") {
        signal.type = IntentType::COMPARISON_INTENT;
      } else if (*type == "ENGAGEMENT_INTENT") {
        signal.type = IntentType::ENGAGEMENT_INTENT;
      } else {
        signal.type = IntentType::NAVIGATION_INTENT;
      }
    }

    // Parse confidence
    auto confidence = dict.FindDouble("confidence");
    if (confidence) {
      signal.confidence_score = *confidence;
      if (*confidence < 0.4) {
        signal.confidence = ConfidenceLevel::LOW;
      } else if (*confidence < 0.7) {
        signal.confidence = ConfidenceLevel::MEDIUM;
      } else {
        signal.confidence = ConfidenceLevel::HIGH;
      }
    }

    // Parse category
    const std::string* category = dict.FindString("category");
    if (category) {
      signal.category = *category;
    }

    signals.push_back(signal);
  }

  return signals;
}

}  // namespace pat
