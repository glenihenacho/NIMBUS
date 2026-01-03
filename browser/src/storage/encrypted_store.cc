// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#include "browser/src/storage/encrypted_store.h"

#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/logging.h"
#include "base/values.h"
#include "crypto/aead.h"

namespace pat {

EncryptedStore::EncryptedStore() {
  // Set default storage path
  storage_path_ = "pat_browsing_data.enc";
}

EncryptedStore::~EncryptedStore() {
  // Persist any cached events
  // Note: In production, events are persisted incrementally
}

bool EncryptedStore::Initialize(const std::string& key) {
  if (key.length() < 16) {
    LOG(ERROR) << "PAT: Encryption key too short";
    return false;
  }

  encryption_key_ = key;
  LOG(INFO) << "PAT: Encrypted store initialized";
  return true;
}

void EncryptedStore::StoreEvent(const BrowsingEvent& event) {
  events_.push_back(event);

  // Trim if over limit
  if (events_.size() > kMaxCachedEvents) {
    events_.erase(events_.begin());
  }

  VLOG(2) << "PAT: Stored event, total: " << events_.size();
}

std::vector<BrowsingEvent> EncryptedStore::GetAllEvents() const {
  return events_;
}

std::vector<BrowsingEvent> EncryptedStore::GetEventsInRange(
    base::Time start,
    base::Time end) const {
  std::vector<BrowsingEvent> result;

  for (const auto& event : events_) {
    if (event.timestamp >= start && event.timestamp <= end) {
      result.push_back(event);
    }
  }

  return result;
}

size_t EncryptedStore::GetEventCount() const {
  return events_.size();
}

void EncryptedStore::ClearAll() {
  events_.clear();
  LOG(INFO) << "PAT: All stored events cleared";
}

std::string EncryptedStore::ExportEncrypted() const {
  // Serialize all events to JSON
  base::Value::List events_list;

  for (const auto& event : events_) {
    base::Value::Dict event_dict;
    event_dict.Set("type", static_cast<int>(event.type));
    event_dict.Set("url_hash", event.url_hash);
    event_dict.Set("timestamp",
                   event.timestamp.InMillisecondsFSinceUnixEpoch());
    event_dict.Set("duration_ms", event.duration.InMilliseconds());
    event_dict.Set("scroll_depth", event.scroll_depth);
    event_dict.Set("element_type", event.element_type);
    event_dict.Set("search_query", event.search_query);
    events_list.Append(std::move(event_dict));
  }

  std::string json;
  base::JSONWriter::Write(events_list, &json);

  // Encrypt the JSON
  return Encrypt(json);
}

bool EncryptedStore::ImportEncrypted(const std::string& data) {
  // Decrypt
  std::string json = Decrypt(data);
  if (json.empty()) {
    LOG(ERROR) << "PAT: Failed to decrypt import data";
    return false;
  }

  // Parse JSON
  auto parsed = base::JSONReader::Read(json);
  if (!parsed || !parsed->is_list()) {
    LOG(ERROR) << "PAT: Failed to parse import data";
    return false;
  }

  // Import events
  for (const auto& item : parsed->GetList()) {
    if (!item.is_dict()) continue;

    const auto& dict = item.GetDict();
    BrowsingEvent event;

    auto type = dict.FindInt("type");
    if (type) {
      event.type = static_cast<BrowsingEventType>(*type);
    }

    const std::string* url_hash = dict.FindString("url_hash");
    if (url_hash) {
      event.url_hash = *url_hash;
    }

    auto timestamp = dict.FindDouble("timestamp");
    if (timestamp) {
      event.timestamp = base::Time::FromMillisecondsSinceUnixEpoch(*timestamp);
    }

    auto duration = dict.FindDouble("duration_ms");
    if (duration) {
      event.duration = base::Milliseconds(*duration);
    }

    auto scroll = dict.FindDouble("scroll_depth");
    if (scroll) {
      event.scroll_depth = *scroll;
    }

    const std::string* element = dict.FindString("element_type");
    if (element) {
      event.element_type = *element;
    }

    const std::string* query = dict.FindString("search_query");
    if (query) {
      event.search_query = *query;
    }

    events_.push_back(event);
  }

  LOG(INFO) << "PAT: Imported " << parsed->GetList().size() << " events";
  return true;
}

size_t EncryptedStore::GetStorageSizeBytes() const {
  // Estimate: ~200 bytes per event
  return events_.size() * 200;
}

std::string EncryptedStore::Encrypt(const std::string& plaintext) const {
  if (encryption_key_.empty()) {
    LOG(WARNING) << "PAT: No encryption key set";
    return plaintext;  // Fallback for development
  }

  // TODO: Use actual crypto::Aead for AES-256-GCM encryption
  // crypto::Aead aead(crypto::Aead::AES_256_GCM);
  // aead.Init(encryption_key_);
  // return aead.Seal(plaintext, nonce, additional_data);

  // Placeholder: base64-like encoding for development
  return "[ENCRYPTED]" + plaintext;
}

std::string EncryptedStore::Decrypt(const std::string& ciphertext) const {
  if (encryption_key_.empty()) {
    LOG(WARNING) << "PAT: No encryption key set";
    return ciphertext;
  }

  // TODO: Use actual crypto::Aead for decryption

  // Placeholder: remove prefix for development
  const std::string prefix = "[ENCRYPTED]";
  if (ciphertext.substr(0, prefix.length()) == prefix) {
    return ciphertext.substr(prefix.length());
  }

  return ciphertext;
}

std::string EncryptedStore::SerializeEvent(const BrowsingEvent& event) const {
  base::Value::Dict dict;
  dict.Set("type", static_cast<int>(event.type));
  dict.Set("url_hash", event.url_hash);
  dict.Set("timestamp", event.timestamp.InMillisecondsFSinceUnixEpoch());

  std::string json;
  base::JSONWriter::Write(dict, &json);
  return json;
}

BrowsingEvent EncryptedStore::DeserializeEvent(const std::string& data) const {
  BrowsingEvent event;

  auto parsed = base::JSONReader::Read(data);
  if (parsed && parsed->is_dict()) {
    const auto& dict = parsed->GetDict();

    auto type = dict.FindInt("type");
    if (type) {
      event.type = static_cast<BrowsingEventType>(*type);
    }

    const std::string* hash = dict.FindString("url_hash");
    if (hash) {
      event.url_hash = *hash;
    }
  }

  return event;
}

}  // namespace pat
