from typing import Optional

from sqlmodel import Field, SQLModel


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=64, unique=True)
    name: str = Field(max_length=100)
    data_scope: str = Field(default="self", max_length=20)
    is_active: bool = Field(default=True)
    is_builtin: bool = Field(default=False)


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=100, unique=True)
    name: str = Field(max_length=100)
    is_builtin: bool = Field(default=False)


class Menu(SQLModel, table=True):
    __tablename__ = "menus"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=64, unique=True)
    name: str = Field(max_length=100)
    parent_id: Optional[int] = Field(default=None, foreign_key="menus.id")
    kind: str = Field(default="page", max_length=20)
    path: Optional[str] = Field(default=None, max_length=500)
    icon: str = Field(default="", max_length=64)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    permission_code: Optional[str] = Field(default=None, max_length=100)


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    user_id: int = Field(foreign_key="users.id", primary_key=True)
    role_id: int = Field(foreign_key="roles.id", primary_key=True)


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"
    role_id: int = Field(foreign_key="roles.id", primary_key=True)
    permission_id: int = Field(foreign_key="permissions.id", primary_key=True)


class RoleMenu(SQLModel, table=True):
    __tablename__ = "role_menus"
    role_id: int = Field(foreign_key="roles.id", primary_key=True)
    menu_id: int = Field(foreign_key="menus.id", primary_key=True)
