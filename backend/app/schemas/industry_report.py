from typing import Optional
from pydantic import BaseModel, Field, field_validator

class IndustryReportRequest(BaseModel):
    
    userInput: str = Field(..., min_length=1, max_length=8000)
    sessionId: Optional[int] = Field(None, ge=1)
    bizKey: Optional[str] = Field(None, min_length=1, max_length=255)
    agentId: Optional[int] = Field(None, ge=1)

    @field_validator("userInput")
    @classmethod
    def validate_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("userInput cannot be blank")
        return value
