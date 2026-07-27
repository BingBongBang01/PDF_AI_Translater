def is_rate_limit_error(msg: str) -> bool:
    msg = msg.lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg

def is_auth_error(msg: str) -> bool:
    msg = msg.lower()
    return "401" in msg or "403" in msg or "unauthorized" in msg or "authentication" in msg or "invalid api key" in msg

def is_quota_exhaustion(msg: str) -> bool:
    msg = msg.lower()
    return "quota" in msg or "exceeded" in msg or "out of credits" in msg or "billing" in msg

def is_permanent_exhaustion(msg: str) -> bool:
    return is_auth_error(msg) or is_quota_exhaustion(msg)
