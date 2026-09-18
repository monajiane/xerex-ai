"""Audit log contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import AuditAction
from app.schemas.common import ApiModel


class AuditLogRead(ApiModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    action: AuditAction
    entity_type: str | None = None
    entity_id: str | None = None
    diff: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    created_at: datetime
