from typing import Optional


class AIServiceUnavailableError(RuntimeError):
    """Raised when an upstream AI provider is temporarily unavailable."""

    def __init__(self, message: str, retry_after_seconds: int = 15):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def get_error_status_code(error: Exception) -> Optional[int]:
    raw_response = getattr(error, "raw_response", None)
    return getattr(raw_response, "status_code", None)


def get_error_text(error: Exception) -> str:
    parts = [
        str(error),
        getattr(error, "body", None),
    ]
    raw_response = getattr(error, "raw_response", None)
    parts.append(getattr(raw_response, "text", None))
    return " ".join(part for part in parts if part).lower()


def is_capacity_exceeded_error(error: Exception) -> bool:
    error_text = get_error_text(error)
    return get_error_status_code(error) == 429 and (
        "service_tier_capacity_exceeded" in error_text
        or "service tier capacity exceeded" in error_text
        or "capacity exceeded" in error_text
    )


def is_temporary_ai_unavailable_error(error: Exception) -> bool:
    error_text = get_error_text(error)
    status_code = get_error_status_code(error)

    if is_capacity_exceeded_error(error):
        return True

    return status_code == 503 and (
        "upstream connect error" in error_text
        or "disconnect/reset before headers" in error_text
        or "reset reason: overflow" in error_text
        or "overflow" in error_text
        or "temporarily unavailable" in error_text
    )
