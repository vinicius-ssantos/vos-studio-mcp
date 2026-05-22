"""Normalized error types for tool output (ADR-0011)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    SPRINT_CLOSED = "sprint_closed"
    BUDGET_EXCEEDED = "budget_exceeded"
    INVALID_INPUT = "invalid_input"
    PROVIDER_ERROR = "provider_error"


class VosError(Exception):
    """Domain error with a normalized error_code and a safe message for tool output."""

    def __init__(self, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
