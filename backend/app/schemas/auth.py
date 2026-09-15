from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class TokenResponse(BaseModel):
    access_token: str; refresh_token: str; token_type: str = "bearer"; expires_in: int
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100); password: str = Field(min_length=1, max_length=256)
class VerifyResponse(BaseModel):
    valid: bool; subject: Optional[str] = None; expires_at: Optional[datetime] = None
