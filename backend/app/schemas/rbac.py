from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class UserWrite(StrictModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    employee_id: str | None = Field(default=None, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    is_active: bool = True
    local_login_enabled: bool = True
    role_ids: list[int] | None = None


class RoleWrite(StrictModel):
    code: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9:_-]*$')
    name: str = Field(min_length=1, max_length=100)
    data_scope: Literal['self', 'department', 'all'] = 'self'
    is_active: bool = True
    permission_ids: list[int] = []
    menu_ids: list[int] = []


class PermissionWrite(StrictModel):
    code: str = Field(min_length=1, max_length=100, pattern=r'^[a-z][a-z0-9:_-]*$')
    name: str = Field(min_length=1, max_length=100)


class MenuWrite(StrictModel):
    code: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9:_-]*$')
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    kind: Literal['directory', 'page', 'external'] = 'page'
    path: str | None = Field(default=None, max_length=500)
    icon: str = Field(default='', max_length=64)
    sort_order: int = 0
    is_active: bool = True
    permission_code: str | None = Field(default=None, max_length=100)
