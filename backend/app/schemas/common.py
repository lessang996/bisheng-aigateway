from typing import Optional
from pydantic import BaseModel, Field
class StreamRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000); model: Optional[str] = None
class SensitiveRuleCreate(BaseModel):
    pattern: str; type: str; action: str = "redact"; priority: int = 0; is_active: bool = True
class LogLevelRequest(BaseModel):
    level: str
class PrincipalSchema(BaseModel):
    principalName: str; principalDescription: Optional[str] = None
