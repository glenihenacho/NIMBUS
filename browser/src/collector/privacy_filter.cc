// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#include "browser/src/collector/privacy_filter.h"

#include <algorithm>
#include <regex>

#include "base/logging.h"
#include "base/strings/string_util.h"

namespace pat {

// Known banking domain patterns
const std::vector<std::string> PrivacyFilter::kBankingDomains = {
    "bank", "chase", "wellsfargo", "bankofamerica", "citi", "capitalone",
    "usbank", "pnc", "ally", "schwab", "fidelity", "vanguard", "etrade",
    "tdameritrade", "robinhood", "coinbase", "kraken", "binance", "paypal",
    "venmo", "zelle", "stripe", "square"
};

// Known healthcare domain patterns
const std::vector<std::string> PrivacyFilter::kHealthcareDomains = {
    "health", "medical", "hospital", "clinic", "doctor", "patient",
    "pharmacy", "cvs", "walgreens", "medicare", "medicaid", "anthem",
    "bluecross", "aetna", "cigna", "unitedhealth", "kaiser", "webmd",
    "mayoclinic", "clevelandclinic", "zocdoc"
};

// Known social media domain patterns
const std::vector<std::string> PrivacyFilter::kSocialMediaDomains = {
    "facebook", "instagram", "twitter", "x.com", "tiktok", "snapchat",
    "linkedin", "reddit", "pinterest", "tumblr", "discord", "telegram",
    "whatsapp", "messenger", "threads"
};

// PII patterns to filter from search queries
const std::vector<std::string> PrivacyFilter::kPiiPatterns = {
    R"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)",  // Email
    R"(\b\d{3}[-.]?\d{3}[-.]?\d{4}\b)",  // Phone number
    R"(\b\d{3}[-]?\d{2}[-]?\d{4}\b)",    // SSN
    R"(\b\d{16}\b)",                      // Credit card
    R"(\b\d{5}(-\d{4})?\b)"              // ZIP code
};

PrivacyFilter::PrivacyFilter() {
  LoadSettings();
}

PrivacyFilter::~PrivacyFilter() {
  SaveSettings();
}

bool PrivacyFilter::IsExcluded(const GURL& url) const {
  if (!url.is_valid()) {
    return true;  // Exclude invalid URLs
  }

  std::string domain = url.host();

  // Check user exclusions first
  if (IsUserExcluded(domain)) {
    return true;
  }

  // Check category exclusions
  if (IsCategoryExcluded(domain)) {
    return true;
  }

  return false;
}

bool PrivacyFilter::IsCategoryExcluded(const std::string& domain) const {
  if (exclude_banking_ && IsBankingSite(domain)) {
    return true;
  }
  if (exclude_healthcare_ && IsHealthcareSite(domain)) {
    return true;
  }
  if (exclude_social_media_ && IsSocialMediaSite(domain)) {
    return true;
  }
  return false;
}

bool PrivacyFilter::IsUserExcluded(const std::string& domain) const {
  // Check exact match
  if (user_excluded_domains_.count(domain) > 0) {
    return true;
  }

  // Check if subdomain of excluded domain
  for (const auto& excluded : user_excluded_domains_) {
    if (domain.length() > excluded.length()) {
      std::string suffix = "." + excluded;
      if (domain.compare(domain.length() - suffix.length(),
                         suffix.length(), suffix) == 0) {
        return true;
      }
    }
  }

  return false;
}

void PrivacyFilter::AddExcludedDomain(const std::string& domain) {
  std::string normalized = base::ToLowerASCII(domain);
  user_excluded_domains_.insert(normalized);
  SaveSettings();
  VLOG(1) << "PAT: Added excluded domain: " << normalized;
}

void PrivacyFilter::RemoveExcludedDomain(const std::string& domain) {
  std::string normalized = base::ToLowerASCII(domain);
  user_excluded_domains_.erase(normalized);
  SaveSettings();
  VLOG(1) << "PAT: Removed excluded domain: " << normalized;
}

std::vector<std::string> PrivacyFilter::GetExcludedDomains() const {
  return std::vector<std::string>(user_excluded_domains_.begin(),
                                   user_excluded_domains_.end());
}

void PrivacyFilter::SetBankingExcluded(bool excluded) {
  exclude_banking_ = excluded;
  SaveSettings();
}

void PrivacyFilter::SetHealthcareExcluded(bool excluded) {
  exclude_healthcare_ = excluded;
  SaveSettings();
}

void PrivacyFilter::SetSocialMediaExcluded(bool excluded) {
  exclude_social_media_ = excluded;
  SaveSettings();
}

bool PrivacyFilter::IsBankingSite(const std::string& domain) const {
  std::string lower_domain = base::ToLowerASCII(domain);
  for (const auto& pattern : kBankingDomains) {
    if (lower_domain.find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

bool PrivacyFilter::IsHealthcareSite(const std::string& domain) const {
  std::string lower_domain = base::ToLowerASCII(domain);
  for (const auto& pattern : kHealthcareDomains) {
    if (lower_domain.find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

bool PrivacyFilter::IsSocialMediaSite(const std::string& domain) const {
  std::string lower_domain = base::ToLowerASCII(domain);
  for (const auto& pattern : kSocialMediaDomains) {
    if (lower_domain.find(pattern) != std::string::npos) {
      return true;
    }
  }
  return false;
}

std::string PrivacyFilter::SanitizeElementSelector(
    const std::string& selector) const {
  // Extract only the element tag name
  // e.g., "button#submit.primary" -> "button"
  // e.g., "input[type=text]" -> "input"

  std::string result;
  for (char c : selector) {
    if (std::isalpha(c)) {
      result += c;
    } else {
      break;  // Stop at first non-alpha character
    }
  }

  return result.empty() ? "unknown" : base::ToLowerASCII(result);
}

std::string PrivacyFilter::SanitizeSearchQuery(const std::string& query) const {
  std::string result = query;

  // Remove any PII patterns
  for (const auto& pattern : kPiiPatterns) {
    std::regex re(pattern, std::regex::icase);
    result = std::regex_replace(result, re, "[REDACTED]");
  }

  // If query is mostly redacted, return empty
  if (result.find("[REDACTED]") != std::string::npos) {
    // Count redacted vs original
    size_t redacted_count = 0;
    size_t pos = 0;
    while ((pos = result.find("[REDACTED]", pos)) != std::string::npos) {
      redacted_count++;
      pos += 10;
    }
    if (redacted_count > 2) {
      return "";  // Too much PII, skip entirely
    }
  }

  return result;
}

void PrivacyFilter::LoadSettings() {
  // TODO: Load from encrypted preferences file
  // For now, use defaults
  VLOG(1) << "PAT: Privacy filter settings loaded";
}

void PrivacyFilter::SaveSettings() {
  // TODO: Save to encrypted preferences file
  VLOG(1) << "PAT: Privacy filter settings saved";
}

}  // namespace pat
