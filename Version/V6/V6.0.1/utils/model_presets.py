"""Central registry of translation providers/models and their known-good
default parameters, so picking a model in the UI can auto-fill sane values
instead of leaving whatever the previous model had selected."""

DEFAULT_PROVIDER = "Google Gemini"
DEFAULT_MODEL = "gemini-2.5-flash"

PROVIDER_MODELS = {
    "Google Gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro"],
    "OpenAI": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "Anthropic": ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"],
    "Local Runtime": ["llama-3-8b", "gemma-2-9b"],
}

# temperature/top_p/max_tokens/chunk_size/context_size/retry/timeout tuned per
# model's real-world context window and throughput characteristics.
MODEL_PARAM_PRESETS = {
    "gemini-2.5-flash": {"temperature": 0.3, "top_p": 0.95, "max_tokens": 8192, "chunk_size": 2000, "context_size": 32000, "retry": 3, "timeout": 60},
    "gemini-2.5-pro":   {"temperature": 0.2, "top_p": 0.9,  "max_tokens": 8192, "chunk_size": 2500, "context_size": 65000, "retry": 3, "timeout": 90},
    "gemini-1.5-pro":   {"temperature": 0.3, "top_p": 0.9,  "max_tokens": 8192, "chunk_size": 2000, "context_size": 65000, "retry": 3, "timeout": 90},
    "gpt-4o":           {"temperature": 0.3, "top_p": 1.0,  "max_tokens": 4096, "chunk_size": 1800, "context_size": 32000, "retry": 3, "timeout": 60},
    "gpt-4-turbo":      {"temperature": 0.3, "top_p": 1.0,  "max_tokens": 4096, "chunk_size": 1500, "context_size": 32000, "retry": 3, "timeout": 60},
    "gpt-3.5-turbo":    {"temperature": 0.5, "top_p": 1.0,  "max_tokens": 2048, "chunk_size": 1200, "context_size": 8000,  "retry": 4, "timeout": 45},
    "claude-3-5-sonnet": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 8192, "chunk_size": 2500, "context_size": 65000, "retry": 3, "timeout": 90},
    "claude-3-opus":    {"temperature": 0.2, "top_p": 0.9,  "max_tokens": 4096, "chunk_size": 2000, "context_size": 65000, "retry": 3, "timeout": 90},
    "claude-3-haiku":   {"temperature": 0.4, "top_p": 1.0,  "max_tokens": 4096, "chunk_size": 1500, "context_size": 32000, "retry": 4, "timeout": 45},
    "llama-3-8b":       {"temperature": 0.5, "top_p": 0.9,  "max_tokens": 2048, "chunk_size": 1000, "context_size": 8000,  "retry": 2, "timeout": 30},
    "gemma-2-9b":       {"temperature": 0.5, "top_p": 0.9,  "max_tokens": 2048, "chunk_size": 1000, "context_size": 8000,  "retry": 2, "timeout": 30},
}


def get_preset(model_name: str) -> dict:
    return MODEL_PARAM_PRESETS.get(model_name, MODEL_PARAM_PRESETS[DEFAULT_MODEL])
