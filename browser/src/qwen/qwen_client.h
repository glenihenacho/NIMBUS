// Copyright 2024 PAT Browser Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license.

#ifndef PAT_BROWSER_QWEN_QWEN_CLIENT_H_
#define PAT_BROWSER_QWEN_QWEN_CLIENT_H_

#include <string>

namespace pat {

// Low-level client for Qwen LLM inference.
// Wraps the Qwen GGUF model for on-device inference.
class QwenClient {
 public:
  // Load a Qwen model from disk
  // Returns opaque handle or nullptr on failure
  static void* LoadModel(const std::string& model_path);

  // Unload a model and free resources
  static void UnloadModel(void* handle);

  // Run inference with the given prompt
  // Returns generated text
  static std::string Infer(void* handle, const std::string& prompt);

  // Get model info
  static std::string GetModelInfo(void* handle);

  // Configuration
  static void SetMaxTokens(int max_tokens);
  static void SetTemperature(float temperature);
  static void SetTopP(float top_p);

 private:
  QwenClient() = delete;

  static int max_tokens_;
  static float temperature_;
  static float top_p_;
};

}  // namespace pat

#endif  // PAT_BROWSER_QWEN_QWEN_CLIENT_H_
