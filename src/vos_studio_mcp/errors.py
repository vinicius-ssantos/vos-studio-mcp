"""Normalized error types for tool output (ADR-0011, ADR-0030)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    # Input / validation
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"
    VALIDATION_ERROR = "validation_error"

    # Business rules
    SPRINT_CLOSED = "sprint_closed"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_REJECTED = "budget_rejected"

    # Provider / external
    PROVIDER_ERROR = "provider_error"
    PROVIDER_AUTH_ERROR = "provider_auth_error"
    PROVIDER_TIMEOUT = "provider_timeout"

    # Security
    RLS_DENIED = "rls_denied"
    AUTH_REQUIRED = "auth_required"


class VosError(Exception):
    """Domain error with a normalized error_code and a safe message for tool output."""

    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
