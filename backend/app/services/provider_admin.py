"""Provider management service (M2).

Route handlers stay thin: they validate with Pydantic, call this service and return
the result. Everything that touches repositories, encryption, health recording and
the audit trail lives here.

The service never returns a secret: ``ProviderRead``/``CredentialRead`` expose a
masked ``key_hint`` only, and the audit ``diff`` for credential operations records
the label and hint — never the secret (PROMPT.md section 7).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import EncryptionError, decrypt_secret, encrypt_secret, key_hint
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.health.targets import HealthTarget, record_health_check
from app.models.enums import AuditAction, CredentialStatus, HealthStatus, ProviderKind
from app.models.identity import AdminUser
from app.models.providers import Provider, ProviderCredential
from app.providers.adapters import ProbeResult, build_adapter
from app.providers.registry import get_spec
from app.repositories.providers import (
    CredentialRepository,
    ModelEndpointRepository,
    ProviderRepository,
)
from app.schemas.providers import (
    CredentialCreate,
    CredentialRead,
    CredentialUpdate,
    ProviderCreate,
    ProviderDeleteImpact,
    ProviderRead,
    ProviderTestResult,
    ProviderUpdate,
)
from app.services.audit import AuditService

logger = get_logger(__name__)

PROVIDER_MUTABLE_FIELDS = (
    "name",
    "base_url",
    "description",
    "enabled",
    "priority",
    "weight",
    "timeout_ms",
    "max_retries",
)


def slugify(value: str) -> str:
    """ASCII slug for URLs and logs; Persian names fall back to a random suffix."""
    normalised = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:64]


class ProviderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProviderRepository(session)
        self.credentials = CredentialRepository(session)
        self.audit = AuditService(session)

    # -- reads -------------------------------------------------------------
    async def list(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        kind: ProviderKind | None = None,
        offset: int = 0,
        limit: int = 25,
        order_by: str = "priority",
    ) -> tuple[list[ProviderRead], int]:
        kind_value = kind.value if kind is not None else None
        providers = await self.repository.list_filtered(
            search=search,
            enabled=enabled,
            kind=kind_value,
            offset=offset,
            limit=limit,
            order_by=order_by,
        )
        total = await self.repository.count_filtered(
            search=search, enabled=enabled, kind=kind_value
        )
        counts = await self.repository.counts([provider.id for provider in providers])

        reads: list[ProviderRead] = []
        for provider in providers:
            read = ProviderRead.model_validate(provider)
            stats = counts.get(provider.id, {})
            reads.append(
                read.model_copy(
                    update={
                        "credential_count": stats.get("credential_count", 0),
                        "model_count": stats.get("model_count", 0),
                    }
                )
            )
        return reads, total

    async def get(self, provider_id: uuid.UUID) -> Provider:
        provider = await self.repository.get(provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        return provider

    async def read(self, provider: Provider) -> ProviderRead:
        counts = await self.repository.counts([provider.id])
        stats = counts.get(provider.id, {})
        return ProviderRead.model_validate(provider).model_copy(
            update={
                "credential_count": stats.get("credential_count", 0),
                "model_count": stats.get("model_count", 0),
            }
        )

    # -- writes ------------------------------------------------------------
    async def create(
        self,
        payload: ProviderCreate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Provider:
        base_url = str(payload.base_url).rstrip("/")
        spec = get_spec(payload.kind)
        if payload.kind is ProviderKind.OPENAI_COMPATIBLE and not base_url:
            raise ValidationError(
                "An OpenAI-compatible provider requires an explicit base URL.",
                code="base_url_required",
            )
        slug = payload.slug or slugify(payload.name) or slugify(payload.kind.value)
        slug = await self._unique_slug(slug)

        provider = Provider(
            name=payload.name,
            slug=slug,
            kind=payload.kind,
            base_url=base_url or (spec.default_base_url if spec else ""),
            description=payload.description,
            enabled=payload.enabled,
            priority=payload.priority,
            weight=payload.weight,
            timeout_ms=payload.timeout_ms,
            max_retries=payload.max_retries,
        )
        await self.repository.add(provider)
        await self.audit.record(
            AuditAction.PROVIDER_CREATED,
            actor=actor,
            entity_type="provider",
            entity_id=str(provider.id),
            diff={
                "name": provider.name,
                "kind": provider.kind.value,
                "base_url": provider.base_url,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return provider

    async def update(
        self,
        provider_id: uuid.UUID,
        payload: ProviderUpdate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Provider:
        provider = await self.get(provider_id)
        changes: dict[str, Any] = {}
        for field in PROVIDER_MUTABLE_FIELDS:
            value = getattr(payload, field, None)
            if value is None:
                continue
            if field == "base_url":
                value = str(value).rstrip("/")
            if getattr(provider, field) != value:
                changes[field] = {"from": getattr(provider, field), "to": value}
                setattr(provider, field, value)
        if not changes:
            return provider

        await self.session.flush()
        await self.audit.record(
            AuditAction.PROVIDER_UPDATED,
            actor=actor,
            entity_type="provider",
            entity_id=str(provider.id),
            diff=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return provider

    async def delete(
        self,
        provider_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        provider = await self.get(provider_id)
        counts = await self.repository.counts([provider.id])
        stats = counts.get(provider.id, {})
        await self.audit.record(
            AuditAction.PROVIDER_DELETED,
            actor=actor,
            entity_type="provider",
            entity_id=str(provider.id),
            diff={
                "name": provider.name,
                "kind": provider.kind.value,
                "credential_count": stats.get("credential_count", 0),
                "model_count": stats.get("model_count", 0),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Credentials, models and endpoints cascade at the database level.
        await self.repository.delete(provider)

    async def delete_impact(self, provider_id: uuid.UUID) -> ProviderDeleteImpact:
        """What a delete would remove — rendered inside the Persian confirm dialog."""
        provider = await self.get(provider_id)
        counts = await self.repository.counts([provider.id])
        stats = counts.get(provider.id, {})
        return ProviderDeleteImpact(
            provider_id=provider.id,
            name=provider.name,
            credential_count=stats.get("credential_count", 0),
            model_count=stats.get("model_count", 0),
            endpoint_count=await ModelEndpointRepository(self.session).count_for_provider(
                provider.id
            ),
        )

    # -- connectivity ------------------------------------------------------
    async def test_connection(
        self,
        provider_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        credential_id: uuid.UUID | None = None,
    ) -> ProviderTestResult:
        """Call the provider with the resolved credential and record the outcome.

        The result is honest: when no credential exists the answer says so instead
        of reporting a fabricated success, and the health record reflects the same
        truth.
        """
        provider = await self.get(provider_id)
        credential: ProviderCredential | None = None
        if credential_id is not None:
            credential = await self.credentials.get(credential_id)
            if credential is None or credential.provider_id != provider.id:
                raise NotFoundError(
                    "The credential does not belong to this provider.",
                    code="credential_not_found",
                )
        else:
            credential = await self.credentials.default_for_provider(provider.id)

        if credential is None:
            await record_health_check(
                self.session,
                HealthTarget.provider(provider.id),
                status=HealthStatus.UNKNOWN,
                error_code="credential_missing",
            )
            provider.health_status = HealthStatus.UNKNOWN.value
            await self.session.flush()
            result = ProviderTestResult(
                provider_id=provider.id,
                credential_id=None,
                ok=False,
                latency_ms=0,
                error_code="credential_missing",
                detail="No credential is configured for this provider.",
                model_count=None,
            )
            await self._audit_test(provider, result, actor, ip_address, user_agent)
            return result

        secret = self._decrypt_or_fail(credential)
        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=secret,
            timeout_ms=provider.timeout_ms,
        )
        probe = await adapter.probe()

        status = HealthStatus.HEALTHY if probe.ok else self._status_for(probe.error_code)
        await record_health_check(
            self.session,
            HealthTarget.credential(credential.id, provider_id=provider.id),
            status=status,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
        )
        await record_health_check(
            self.session,
            HealthTarget.provider(provider.id),
            status=status,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
        )
        provider.health_status = status.value
        CredentialVerifier.apply_probe(credential, probe)

        result = ProviderTestResult(
            provider_id=provider.id,
            credential_id=credential.id,
            ok=probe.ok,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
            detail=probe.detail,
            model_count=probe.model_count,
        )
        await self._audit_test(provider, result, actor, ip_address, user_agent)
        return result

    async def _audit_test(
        self,
        provider: Provider,
        result: ProviderTestResult,
        actor: AdminUser | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        await self.audit.record(
            AuditAction.PROVIDER_TESTED,
            actor=actor,
            entity_type="provider",
            entity_id=str(provider.id),
            diff={
                "ok": result.ok,
                "latency_ms": result.latency_ms,
                "error_code": result.error_code,
                "models": result.model_count,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    def _status_for(error_code: str | None) -> HealthStatus:
        if error_code in {"provider_rate_limited"}:
            return HealthStatus.RATE_LIMITED
        if error_code in {"provider_unauthorized", "provider_forbidden"}:
            return HealthStatus.DOWN
        if error_code in {"provider_timeout", "provider_unavailable", "provider_unreachable"}:
            return HealthStatus.DEGRADED
        return HealthStatus.DOWN

    def _decrypt_or_fail(self, credential: ProviderCredential) -> str:
        try:
            return decrypt_secret(credential.encrypted_secret)
        except EncryptionError as exc:  # pragma: no cover - defensive
            raise ValidationError(
                "The stored credential cannot be decrypted with the current key.",
                code="credential_decryption_failed",
                details={"credential_id": str(credential.id)},
            ) from exc

    async def _unique_slug(self, base: str) -> str:
        candidate = base or "provider"
        suffix = 1
        while await self.repository.slug_exists(candidate):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate


class CredentialVerifier:
    """Shared credential status transitions (used by the service and the tests)."""

    @staticmethod
    def apply_probe(credential: ProviderCredential, probe: ProbeResult) -> None:
        credential.last_verified_at = datetime.now(UTC)
        credential.last_error_code = probe.error_code
        if probe.ok:
            credential.status = CredentialStatus.ACTIVE
        elif probe.error_code in {"provider_rate_limited"}:
            # A rate-limited key is still a valid key; it is simply throttled now.
            credential.status = CredentialStatus.ACTIVE
        else:
            credential.status = CredentialStatus.INVALID


class CredentialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CredentialRepository(session)
        self.providers = ProviderRepository(session)
        self.audit = AuditService(session)

    # -- reads -------------------------------------------------------------
    async def list_for_provider(
        self, provider_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> tuple[list[CredentialRead], int]:
        provider = await self.providers.get(provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        credentials = await self.repository.list_for_provider(
            provider_id, offset=offset, limit=limit
        )
        total = await self.repository.count_for_provider(provider_id)
        return [CredentialRead.model_validate(item) for item in credentials], total

    async def get(self, credential_id: uuid.UUID) -> ProviderCredential:
        credential = await self.repository.get(credential_id)
        if credential is None:
            raise NotFoundError("The credential does not exist.", code="credential_not_found")
        return credential

    # -- writes ------------------------------------------------------------
    async def create(
        self,
        provider_id: uuid.UUID,
        payload: CredentialCreate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderCredential:
        provider = await self.providers.get(provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        if await self.repository.label_exists(provider_id, payload.label):
            raise ConflictError(
                "A credential with this label already exists for the provider.",
                code="credential_label_duplicate",
                details={"label": payload.label},
            )

        credential = ProviderCredential(
            provider_id=provider_id,
            label=payload.label,
            encrypted_secret=encrypt_secret(payload.secret),
            key_hint=key_hint(payload.secret),
            status=CredentialStatus.UNVERIFIED,
        )
        await self.repository.add(credential)
        await self.audit.record(
            AuditAction.CREDENTIAL_CREATED,
            actor=actor,
            entity_type="provider_credential",
            entity_id=str(credential.id),
            diff={
                "provider_id": str(provider_id),
                "label": payload.label,
                "key_hint": credential.key_hint,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return credential

    async def update(
        self,
        credential_id: uuid.UUID,
        payload: CredentialUpdate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderCredential:
        credential = await self.get(credential_id)
        changes: dict[str, Any] = {}
        if payload.label is not None and payload.label != credential.label:
            if await self.repository.label_exists(
                credential.provider_id, payload.label, exclude_id=credential.id
            ):
                raise ConflictError(
                    "A credential with this label already exists for the provider.",
                    code="credential_label_duplicate",
                    details={"label": payload.label},
                )
            changes["label"] = {"from": credential.label, "to": payload.label}
            credential.label = payload.label
        if payload.status is not None and payload.status != credential.status:
            changes["status"] = {"from": credential.status.value, "to": payload.status.value}
            credential.status = payload.status
        if not changes:
            return credential
        await self.session.flush()
        await self.audit.record(
            AuditAction.CREDENTIAL_UPDATED,
            actor=actor,
            entity_type="provider_credential",
            entity_id=str(credential.id),
            diff=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return credential

    async def rotate(
        self,
        credential_id: uuid.UUID,
        *,
        secret: str,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderCredential:
        """Replace the stored secret; the old ciphertext is overwritten in place."""
        credential = await self.get(credential_id)
        credential.encrypted_secret = encrypt_secret(secret)
        credential.key_hint = key_hint(secret)
        credential.status = CredentialStatus.UNVERIFIED
        credential.last_error_code = None
        await self.session.flush()
        await self.audit.record(
            AuditAction.CREDENTIAL_ROTATED,
            actor=actor,
            entity_type="provider_credential",
            entity_id=str(credential.id),
            diff={"key_hint": credential.key_hint},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return credential

    async def delete(
        self,
        credential_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        credential = await self.get(credential_id)
        bound_endpoints = await self.repository.used_by_endpoints(credential.id)
        await self.audit.record(
            AuditAction.CREDENTIAL_DELETED,
            actor=actor,
            entity_type="provider_credential",
            entity_id=str(credential.id),
            diff={
                "provider_id": str(credential.provider_id),
                "label": credential.label,
                "key_hint": credential.key_hint,
                "endpoints_unbound": bound_endpoints,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Endpoints keep working: ``model_endpoints.credential_id`` is ON DELETE SET NULL,
        # so they fall back to the provider's default credential instead of breaking.
        await self.repository.delete(credential)

    async def verify(
        self,
        credential_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ProviderTestResult:
        credential = await self.get(credential_id)
        provider = await self.providers.get(credential.provider_id)
        if provider is None:  # pragma: no cover - FK guarantees this
            raise NotFoundError("The provider does not exist.", code="provider_not_found")

        secret = ProviderService(self.session)._decrypt_or_fail(credential)
        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=secret,
            timeout_ms=provider.timeout_ms,
        )
        probe = await adapter.probe()
        status = HealthStatus.HEALTHY if probe.ok else ProviderService._status_for(probe.error_code)
        await record_health_check(
            self.session,
            HealthTarget.credential(credential.id, provider_id=provider.id),
            status=status,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
        )
        # The credential *is* how the provider is reached, so the provider-level
        # observation is updated from the same probe instead of being left stale.
        await record_health_check(
            self.session,
            HealthTarget.provider(provider.id),
            status=status,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
        )
        provider.health_status = status.value
        CredentialVerifier.apply_probe(credential, probe)
        await self.session.flush()
        await self.audit.record(
            AuditAction.CREDENTIAL_VERIFIED,
            actor=actor,
            entity_type="provider_credential",
            entity_id=str(credential.id),
            diff={
                "ok": probe.ok,
                "status": credential.status.value,
                "latency_ms": probe.latency_ms,
                "error_code": probe.error_code,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ProviderTestResult(
            provider_id=provider.id,
            credential_id=credential.id,
            ok=probe.ok,
            latency_ms=probe.latency_ms,
            status_code=probe.status_code,
            error_code=probe.error_code,
            detail=probe.detail,
            model_count=probe.model_count,
        )


__all__ = ["CredentialService", "CredentialVerifier", "ProviderService", "slugify"]
