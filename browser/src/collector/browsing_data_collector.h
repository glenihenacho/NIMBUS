// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_COLLECTOR_BROWSING_DATA_COLLECTOR_H_
#define PAT_BROWSER_COLLECTOR_BROWSING_DATA_COLLECTOR_H_

#include <memory>
#include <string>
#include <vector>

#include "base/memory/singleton.h"
#include "browser/src/collector/event_types.h"
#include "url/gurl.h"

namespace content {
class WebContents;
}  // namespace content

namespace pat {

class PrivacyFilter;
class EncryptedStore;

// Singleton class that collects browsing data from Chromium's rendering engine.
// This component hooks into navigation and DOM events to capture user behavior
// for intent signal detection.
//
// Privacy is enforced at collection time:
// - Incognito mode sessions are never tracked
// - User-excluded sites are skipped
// - Sensitive categories (banking, healthcare) are excluded by default
// - Raw URLs are hashed before storage
class BrowsingDataCollector {
 public:
  // Returns the singleton instance
  static BrowsingDataCollector* GetInstance();

  // Delete copy/move constructors
  BrowsingDataCollector(const BrowsingDataCollector&) = delete;
  BrowsingDataCollector& operator=(const BrowsingDataCollector&) = delete;

  // Event handlers called from Chromium hooks

  // Called when a page finishes loading
  void OnPageLoad(const GURL& url, content::WebContents* contents);

  // Called when user leaves a page
  void OnPageUnload(const GURL& url, base::TimeDelta time_on_page);

  // Called on scroll events (debounced)
  void OnScroll(double depth_percentage);

  // Called on click events
  void OnClick(const std::string& element_selector);

  // Called when a search query is detected
  void OnSearchQuery(const std::string& query);

  // Called on form submission (field types only, no values)
  void OnFormSubmit(const std::vector<std::string>& field_types);

  // Configuration methods

  // Check if data collection is globally enabled
  bool IsCollectionEnabled() const;

  // Enable or disable data collection
  void SetCollectionEnabled(bool enabled);

  // Check if current context is incognito
  bool IsIncognito(content::WebContents* contents) const;

  // Check if URL is in exclusion list
  bool IsExcludedSite(const GURL& url) const;

  // Add site to exclusion list
  void AddExcludedSite(const std::string& domain);

  // Remove site from exclusion list
  void RemoveExcludedSite(const std::string& domain);

  // Get all collected events (for local viewing)
  std::vector<BrowsingEvent> GetCollectedEvents() const;

  // Clear all collected data
  void ClearAllData();

  // Export data as JSON
  std::string ExportDataAsJson() const;

 private:
  friend struct base::DefaultSingletonTraits<BrowsingDataCollector>;

  BrowsingDataCollector();
  ~BrowsingDataCollector();

  // Hash a URL for privacy
  std::string HashUrl(const GURL& url) const;

  // Privacy filter for checking exclusions
  std::unique_ptr<PrivacyFilter> privacy_filter_;

  // Encrypted local storage
  std::unique_ptr<EncryptedStore> local_store_;

  // Current scroll depth (for debouncing)
  double current_scroll_depth_ = 0.0;

  // Global collection enabled flag
  bool collection_enabled_ = true;
};

}  // namespace pat

#endif  // PAT_BROWSER_COLLECTOR_BROWSING_DATA_COLLECTOR_H_
