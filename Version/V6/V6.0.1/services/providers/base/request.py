from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass(frozen=True)
class SystemPrompt:
    content: str
    variables: Dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class UserPrompt:
    content: str

@dataclass(frozen=True)
class PromptTemplate:
    system_prompt: SystemPrompt
    user_prompt: UserPrompt

@dataclass(frozen=True)
class GenerationConfig:
    temperature: float = 0.3
    top_p: float = 1.0
    max_tokens: int = 4000
    stop_sequences: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class SafetyConfig:
    harassment: str = "BLOCK_NONE"
    hate_speech: str = "BLOCK_NONE"
    sexually_explicit: str = "BLOCK_NONE"
    dangerous_content: str = "BLOCK_NONE"

@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_backoff: bool = True

@dataclass(frozen=True)
class TranslationChunk:
    chunk_id: str
    text: str
    page_number: int

@dataclass(frozen=True)
class TranslationRequest:
    request_id: str
    chunk: TranslationChunk
    prompt: PromptTemplate
    source_language: str
    target_language: str
    generation_config: GenerationConfig = field(default_factory=GenerationConfig)
    safety_config: SafetyConfig = field(default_factory=SafetyConfig)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    stream: bool = False
