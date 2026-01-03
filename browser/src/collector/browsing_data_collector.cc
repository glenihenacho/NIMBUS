// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#include "browser/src/collector/browsing_data_collector.h"

#include <algorithm>

#include "base/hash/sha1.h"
#include "base/json/json_writer.h"
#include "base/logging.h"
#include "base/strings/string_util.h"
#include "base/values.h"
#include "browser/src/collector/privacy_filter.h"
#include "browser/src/storage/encrypted_store.h"
#include "content/public/browser/web_contents.h"

namespace pat {

// static
BrowsingDataCollector* BrowsingDataCollector::GetInstance() {
  return base::Singleton<BrowsingDataCollector>::get();
}

BrowsingDataCollector::BrowsingDataCollector()
    : privacy_filter_(std::make_unique<PrivacyFilter>()),
      local_store_(std::make_unique<EncryptedStore>()) {
  VLOG(1) << "PAT BrowsingDataCollector initialized";
}

BrowsingDataCollector::~BrowsingDataCollector() = default;

void BrowsingDataCollector::OnPageLoad(const GURL& url,
                                        content::WebContents* contents) {
  // Never collect in incognito mode
  if (IsIncognito(contents)) {
    VLOG(2) << "Skipping page load - incognito mode";
    return;
  }

  // Check if collection is enabled
  if (!IsCollectionEnabled()) {
    return;
  }

  // Check privacy filter
  if (IsExcludedSite(url)) {
    VLOG(2) << "Skipping page load - excluded site";
    return;
  }

  // Create and store event
  BrowsingEvent event(BrowsingEventType::PAGE_LOAD,
                      HashUrl(url),
                      base::Time::Now());

  local_store_->StoreEvent(event);

  // Reset scroll tracking for new page
  current_scroll_depth_ = 0.0;
}

void BrowsingDataCollector::OnPageUnload(const GURL& url,
                                          base::TimeDelta time_on_page) {
  if (!IsCollectionEnabled()) {
    return;
  }

  BrowsingEvent event(BrowsingEventType::PAGE_UNLOAD,
                      HashUrl(url),
                      base::Time::Now());
  event.duration = time_on_page;
  event.scroll_depth = current_scroll_depth_;

  local_store_->StoreEvent(event);
}

void BrowsingDataCollector::OnScroll(double depth_percentage) {
  if (!IsCollectionEnabled()) {
    return;
  }

  // Only update if we scrolled deeper (track max scroll depth)
  if (depth_percentage > current_scroll_depth_) {
    current_scroll_depth_ = depth_percentage;
  }
}

void BrowsingDataCollector::OnClick(const std::string& element_selector) {
  if (!IsCollectionEnabled()) {
    return;
  }

  BrowsingEvent event;
  event.type = BrowsingEventType::CLICK;
  event.timestamp = base::Time::Now();

  // Extract element type only (no IDs or classes that might contain PII)
  // e.g., "button", "a", "input[type=submit]"
  event.element_type = privacy_filter_->SanitizeElementSelector(element_selector);

  local_store_->StoreEvent(event);
}

void BrowsingDataCollector::OnSearchQuery(const std::string& query) {
  if (!IsCollectionEnabled()) {
    return;
  }

  // Sanitize query to remove potential PII
  std::string sanitized = privacy_filter_->SanitizeSearchQuery(query);
  if (sanitized.empty()) {
    return;
  }

  BrowsingEvent event;
  event.type = BrowsingEventType::SEARCH_QUERY;
  event.timestamp = base::Time::Now();
  event.search_query = sanitized;

  local_store_->StoreEvent(event);
}

void BrowsingDataCollector::OnFormSubmit(
    const std::vector<std::string>& field_types) {
  if (!IsCollectionEnabled()) {
    return;
  }

  // Only store field types, never values
  // Skip if form contains password fields
  for (const auto& type : field_types) {
    if (type == "password" || type == "credit-card") {
      VLOG(2) << "Skipping form submit - contains sensitive fields";
      return;
    }
  }

  BrowsingEvent event;
  event.type = BrowsingEventType::FORM_SUBMIT;
  event.timestamp = base::Time::Now();

  local_store_->StoreEvent(event);
}

bool BrowsingDataCollector::IsCollectionEnabled() const {
  return collection_enabled_;
}

void BrowsingDataCollector::SetCollectionEnabled(bool enabled) {
  collection_enabled_ = enabled;
  VLOG(1) << "PAT data collection " << (enabled ? "enabled" : "disabled");
}

bool BrowsingDataCollector::IsIncognito(content::WebContents* contents) const {
  if (!contents) {
    return false;
  }
  return contents->GetBrowserContext()->IsOffTheRecord();
}

bool BrowsingDataCollector::IsExcludedSite(const GURL& url) const {
  return privacy_filter_->IsExcluded(url);
}

void BrowsingDataCollector::AddExcludedSite(const std::string& domain) {
  privacy_filter_->AddExcludedDomain(domain);
}

void BrowsingDataCollector::RemoveExcludedSite(const std::string& domain) {
  privacy_filter_->RemoveExcludedDomain(domain);
}

std::vector<BrowsingEvent> BrowsingDataCollector::GetCollectedEvents() const {
  return local_store_->GetAllEvents();
}

void BrowsingDataCollector::ClearAllData() {
  local_store_->ClearAll();
  current_scroll_depth_ = 0.0;
  VLOG(1) << "PAT: All collected data cleared";
}

std::string BrowsingDataCollector::ExportDataAsJson() const {
  base::Value::List events_list;

  for (const auto& event : GetCollectedEvents()) {
    base::Value::Dict event_dict;
    event_dict.Set("type", static_cast<int>(event.type));
    event_dict.Set("url_hash", event.url_hash);
    event_dict.Set("timestamp",
                   event.timestamp.InMillisecondsFSinceUnixEpoch());
    event_dict.Set("scroll_depth", event.scroll_depth);
    event_dict.Set("element_type", event.element_type);
    event_dict.Set("search_query", event.search_query);
    events_list.Append(std::move(event_dict));
  }

  std::string json;
  base::JSONWriter::WriteWithOptions(
      events_list,
      base::JSONWriter::OPTIONS_PRETTY_PRINT,
      &json);
  return json;
}

std::string BrowsingDataCollector::HashUrl(const GURL& url) const {
  // Use SHA-1 hash of URL for privacy
  std::string url_str = url.spec();
  std::string hash = base::SHA1HashString(url_str);

  // Convert to hex string
  std::string hex_hash;
  for (unsigned char c : hash) {
    char buf[3];
    snprintf(buf, sizeof(buf), "%02x", c);
    hex_hash += buf;
  }

  return hex_hash;
}

}  // namespace pat
