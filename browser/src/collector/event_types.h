// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_COLLECTOR_EVENT_TYPES_H_
#define PAT_BROWSER_COLLECTOR_EVENT_TYPES_H_

#include <string>
#include "base/time/time.h"

namespace pat {

// Types of browsing events collected by the data collector
enum class BrowsingEventType {
  PAGE_LOAD,      // User navigates to a new page
  PAGE_UNLOAD,    // User leaves a page
  SCROLL,         // User scrolls the page
  CLICK,          // User clicks an element
  FORM_SUBMIT,    // User submits a form
  SEARCH_QUERY    // User performs a search
};

// Represents a single browsing event
struct BrowsingEvent {
  BrowsingEventType type;

  // URL hash (never store raw URLs)
  std::string url_hash;

  // When the event occurred
  base::Time timestamp;

  // Duration on page (for PAGE_UNLOAD events)
  base::TimeDelta duration;

  // Scroll depth as percentage 0.0-1.0 (for SCROLL events)
  double scroll_depth = 0.0;

  // Anonymized element type (for CLICK events)
  std::string element_type;

  // Search query text (for SEARCH_QUERY events only)
  std::string search_query;

  // Referrer URL hash
  std::string referrer_hash;

  // Constructor
  BrowsingEvent() = default;

  BrowsingEvent(BrowsingEventType t, const std::string& hash, base::Time ts)
      : type(t), url_hash(hash), timestamp(ts) {}
};

// Privacy-sensitive categories that are excluded by default
enum class ExcludedCategory {
  BANKING,      // Financial institutions
  HEALTHCARE,   // Medical and health sites
  GOVERNMENT,   // Government portals
  ADULT         // Adult content
};

}  // namespace pat

#endif  // PAT_BROWSER_COLLECTOR_EVENT_TYPES_H_
