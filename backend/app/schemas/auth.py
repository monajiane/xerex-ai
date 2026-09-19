"""Authentication contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.core.config import settings
from app.models.enums import AdminRole, UserStatus
from app.schemas.common import ApiModel


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class BootstrapRequest(ApiModel):
    """Creates the first owner account. Only allowed while no user exists."""

    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def _enforce_min_length(cls, value: str) -> str:
        if len(value) < settings.password_min_length:
            raise ValueError(f"password must be at least {settings.password_min_length} characters")
        return value


class AdminUserRead(ApiModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    role: AdminRole
    status: UserStatus
    mfa_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime


class AdminUserCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    full_name: str | None = Field(default=None, max_length=120)
    role: AdminRole = AdminRole.VIEWER


class AdminUserUpdate(ApiModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: AdminRole | None = None
    status: UserStatus | None = None


class TokenPair(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")
    expires_at: datetime


class AuthenticatedSession(ApiModel):
    user: AdminUserRead
    tokens: TokenPair


class BootstrapStatus(ApiModel):
    """Whether the platform still requires its first owner account.

    ``requires_bootstrap`` describes the data (no owner exists yet);
    ``bootstrap_enabled`` reports the effective configuration switch;
    ``bootstrap_allowed`` is the combination the panel should act on.
    """

    requires_bootstrap: bool
    bootstrap_enabled: bool
    admin_user_count: int
    bootstrap_allowed: bool = False
    #: Current feature milestone of the backend, so pre-auth screens can state it
    #: without hard-coding a drifted value in the panel.
    milestone: str = "M1"
