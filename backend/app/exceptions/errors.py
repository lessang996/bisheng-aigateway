from typing import Optional


class GatewayError(Exception):
    """Base exception for all gateway-level errors."""

    code: str = "ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        self.message = message
        self.details = details


class AuthenticationError(GatewayError):
    code = "AUTHENTICATION_ERROR"
    status_code = 401


class AuthorizationError(GatewayError):
    code = "AUTHORIZATION_ERROR"
    status_code = 403


class ValidationError(GatewayError):
    code = "VALIDATION_ERROR"
    status_code = 422


class RateLimitError(GatewayError):
    code = "RATE_LIMIT_ERROR"
    status_code = 429


class ExternalServiceError(GatewayError):
    code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502


class InternalServerError(GatewayError):
    code = "INTERNAL_SERVER_ERROR"
    status_code = 500
