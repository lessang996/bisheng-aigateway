from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from app.exceptions.errors import GatewayError


async def gateway_exception_handler(request: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
