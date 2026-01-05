// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_QWEN_INTENT_ANALYZER_H_
#define PAT_BROWSER_QWEN_INTENT_ANALYZER_H_

#include <memory>
#include <string>
#include <vector>

#include "browser/src/collector/event_types.h"

namespace pat {

// Types of detected user intent
enum class IntentType {
  PURCHASE_INTENT,     // User likely to buy something
  RESEARCH_INTENT,     // User researching a topic
  COMPARISON_INTENT,   // User comparing products/services
  ENGAGEMENT_INTENT,   // High engagement with content
  NAVIGATION_INTENT    // User navigating to specific destination
};

// Confidence level for intent detection
enum class ConfidenceLevel {
  LOW,      // 0.0 - 0.4
  MEDIUM,   // 0.4 - 0.7
  HIGH      // 0.7 - 1.0
};

// Represents a detected intent signal
struct IntentSignal {
  IntentType type;
  ConfidenceLevel confidence;
  double confidence_score;  // 0.0 - 1.0
  std::string category;     // e.g., "electronics", "travel", "finance"
  base::Time detected_at;

  // Time window for this intent
  base::TimeDelta time_window;

  // Number of supporting events
  int event_count = 0;
};

// Analyzes browsing events using Qwen LLM to detect intent signals.
// Runs locally on-device for privacy - no raw data leaves the device.
class IntentAnalyzer {
 public:
  IntentAnalyzer();
  ~IntentAnalyzer();

  // Initialize the Qwen model
  bool Initialize(const std::string& model_path);

  // Check if model is ready
  bool IsReady() const;

  // Analyze a batch of browsing events
  std::vector<IntentSignal> AnalyzeEvents(
      const std::vector<BrowsingEvent>& events);

  // Analyze events within a time window
  std::vector<IntentSignal> AnalyzeTimeWindow(
      const std::vector<BrowsingEvent>& events,
      base::TimeDelta window);

  // Get the latest detected intents
  std::vector<IntentSignal> GetLatestIntents() const;

  // Clear detected intents
  void ClearIntents();

  // Configuration
  void SetMinConfidence(double threshold);
  double GetMinConfidence() const { return min_confidence_; }

  void SetAnalysisInterval(base::TimeDelta interval);
  base::TimeDelta GetAnalysisInterval() const { return analysis_interval_; }

 private:
  // Run Qwen inference on event data
  std::string RunInference(const std::string& prompt);

  // Parse Qwen response into intent signals
  std::vector<IntentSignal> ParseResponse(const std::string& response);

  // Build prompt from events
  std::string BuildPrompt(const std::vector<BrowsingEvent>& events);

  // Qwen model handle
  void* model_handle_ = nullptr;

  // Model ready flag
  bool is_ready_ = false;

  // Cached intents
  std::vector<IntentSignal> cached_intents_;

  // Minimum confidence threshold
  double min_confidence_ = 0.5;

  // Analysis interval
  base::TimeDelta analysis_interval_ = base::Minutes(5);
};

}  // namespace pat

#endif  // PAT_BROWSER_QWEN_INTENT_ANALYZER_H_
