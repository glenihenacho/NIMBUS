// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_COLLECTOR_PRIVACY_FILTER_H_
#define PAT_BROWSER_COLLECTOR_PRIVACY_FILTER_H_

#include <set>
#include <string>
#include <vector>

#include "url/gurl.h"

namespace pat {

// Filters browsing data to protect user privacy.
// This class maintains exclusion lists and sanitizes data before storage.
class PrivacyFilter {
 public:
  PrivacyFilter();
  ~PrivacyFilter();

  // Check if a URL should be excluded from data collection
  bool IsExcluded(const GURL& url) const;

  // Check if domain matches a category exclusion
  bool IsCategoryExcluded(const std::string& domain) const;

  // Check if domain is in user's exclusion list
  bool IsUserExcluded(const std::string& domain) const;

  // Add domain to user exclusion list
  void AddExcludedDomain(const std::string& domain);

  // Remove domain from user exclusion list
  void RemoveExcludedDomain(const std::string& domain);

  // Get all user-excluded domains
  std::vector<std::string> GetExcludedDomains() const;

  // Category exclusion toggles
  void SetBankingExcluded(bool excluded);
  void SetHealthcareExcluded(bool excluded);
  void SetSocialMediaExcluded(bool excluded);

  bool IsBankingExcluded() const { return exclude_banking_; }
  bool IsHealthcareExcluded() const { return exclude_healthcare_; }
  bool IsSocialMediaExcluded() const { return exclude_social_media_; }

  // Sanitize element selector to remove potential PII
  std::string SanitizeElementSelector(const std::string& selector) const;

  // Sanitize search query to remove potential PII
  std::string SanitizeSearchQuery(const std::string& query) const;

  // Load/save exclusion settings
  void LoadSettings();
  void SaveSettings();

 private:
  // Check domain against known category lists
  bool IsBankingSite(const std::string& domain) const;
  bool IsHealthcareSite(const std::string& domain) const;
  bool IsSocialMediaSite(const std::string& domain) const;

  // User-defined excluded domains
  std::set<std::string> user_excluded_domains_;

  // Category exclusion flags (default: on for banking/healthcare)
  bool exclude_banking_ = true;
  bool exclude_healthcare_ = true;
  bool exclude_social_media_ = false;

  // Known category domain patterns
  static const std::vector<std::string> kBankingDomains;
  static const std::vector<std::string> kHealthcareDomains;
  static const std::vector<std::string> kSocialMediaDomains;

  // PII patterns for sanitization
  static const std::vector<std::string> kPiiPatterns;
};

}  // namespace pat

#endif  // PAT_BROWSER_COLLECTOR_PRIVACY_FILTER_H_
