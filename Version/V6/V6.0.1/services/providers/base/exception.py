class ProviderError(Exception):
    """Base exception for all AI provider errors."""
    pass

class RateLimitError(ProviderError):
    """Raised when a provider's rate limit is hit."""
    pass

class AuthenticationError(ProviderError):
    """Raised when API keys are invalid."""
    pass

class ContextLengthExceededError(ProviderError):
    """Raised when prompt exceeds model context window."""
    pass

class ServerError(ProviderError):
    """Raised on 5xx errors from the provider."""
    pass
