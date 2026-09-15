from typing import Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    agentId: Optional[int] = None
    userInput: str = Field(..., min_length=1, max_length=8000)
    sessionId: Optional[int] = Field(None, ge=1)
    bizKey: Optional[str] = Field(None, min_length=1, max_length=255)
