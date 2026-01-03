// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_STORAGE_ENCRYPTED_STORE_H_
#define PAT_BROWSER_STORAGE_ENCRYPTED_STORE_H_

#include <string>
#include <vector>

#include "browser/src/collector/event_types.h"

namespace pat {

// Encrypted local storage for browsing events.
// All data is encrypted at rest using user's key.
class EncryptedStore {
 public:
  EncryptedStore();
  ~EncryptedStore();

  // Initialize storage with encryption key
  bool Initialize(const std::string& key);

  // Store a browsing event
  void StoreEvent(const BrowsingEvent& event);

  // Get all stored events
  std::vector<BrowsingEvent> GetAllEvents() const;

  // Get events within time range
  std::vector<BrowsingEvent> GetEventsInRange(base::Time start,
                                               base::Time end) const;

  // Get event count
  size_t GetEventCount() const;

  // Clear all stored events
  void ClearAll();

  // Export events as encrypted blob
  std::string ExportEncrypted() const;

  // Import events from encrypted blob
  bool ImportEncrypted(const std::string& data);

  // Storage stats
  size_t GetStorageSizeBytes() const;

 private:
  // Encrypt data
  std::string Encrypt(const std::string& plaintext) const;

  // Decrypt data
  std::string Decrypt(const std::string& ciphertext) const;

  // Serialize event to bytes
  std::string SerializeEvent(const BrowsingEvent& event) const;

  // Deserialize event from bytes
  BrowsingEvent DeserializeEvent(const std::string& data) const;

  // In-memory event cache
  std::vector<BrowsingEvent> events_;

  // Encryption key (derived from user password)
  std::string encryption_key_;

  // Storage file path
  std::string storage_path_;

  // Max events to keep in memory
  static constexpr size_t kMaxCachedEvents = 10000;
};

}  // namespace pat

#endif  // PAT_BROWSER_STORAGE_ENCRYPTED_STORE_H_
