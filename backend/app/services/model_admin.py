"""Model registry, discovery and playground (M3).

Three responsibilities, all behind services so the routes stay thin:

* ``ModelService``      — manual add, edit, enable/disable, deprecate, delete.
* ``EndpointService``   — «نقاط اتصال مدل»: the path/method/credential a model is
  dispatched through, with the provider default as the fallback.
* ``DiscoveryService``  — «کشف مدل‌ها»: asks the provider for its catalogue and
  reconciles it with the registry instead of trusting it blindly.

The playground never invents a result: it either returns the provider's answer with
real token counts and latency, or the typed upstream error code.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import EncryptionError, decrypt_secret
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.health.observations import record_failure_observation
from app.health.targets import HealthTarget, record_health_check
from app.models.enums import AuditAction, HealthStatus, ProviderKind
from app.models.identity import AdminUser
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.providers.adapters import (
    ChatMessage,
    UpstreamError,
    build_adapter,
    default_chat_path,
    supports_streaming,
)
from app.providers.registry import get_spec
from app.repositories.providers import (
    CredentialRepository,
    ModelEndpointRepository,
    ModelRepository,
    ProviderRepository,
)
from app.schemas.providers import (
    ModelCreate,
    ModelDiscoveryResultDetail,
    ModelEndpointCreate,
    ModelEndpointRead,
    ModelEndpointUpdate,
    ModelRead,
    ModelTestRequest,
    ModelTestResult,
    ModelWrite,
)
from app.services.audit import AuditService

logger = get_logger(__name__)

MODEL_MUTABLE_FIELDS = (
    "display_name",
    "context_window",
    "max_output_tokens",
    "input_price_per_1m",
    "output_price_per_1m",
    "capabilities",
    "enabled",
    "deprecated",
)

ENDPOINT_MUTABLE_FIELDS = (
    "path",
    "method",
    "streaming_supported",
    "param_map",
    "enabled",
    "credential_id",
)


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ModelRepository(session)
        self.providers = ProviderRepository(session)
        self.audit = AuditService(session)

    # -- reads ---------------------------------------------------------------
    async def list(
        self,
        *,
        search: str | None = None,
        provider_id: uuid.UUID | None = None,
        enabled: bool | None = None,
        deprecated: bool | None = None,
        offset: int = 0,
        limit: int = 25,
        order_by: str = "name",
    ) -> tuple[Sequence[ModelRead], int]:
        models = await self.repository.list_filtered(
            search=search,
            provider_id=provider_id,
            enabled=enabled,
            deprecated=deprecated,
            offset=offset,
            limit=limit,
            order_by=order_by,
        )
        total = await self.repository.count_filtered(
            search=search, provider_id=provider_id, enabled=enabled, deprecated=deprecated
        )
        return [ModelRead.model_validate(model) for model in models], total

    async def get(self, model_id: uuid.UUID) -> Model:
        model = await self.repository.get(model_id)
        if model is None:
            raise NotFoundError("The model does not exist.", code="model_not_found")
        return model

    async def read(self, model: Model) -> ModelRead:
        return ModelRead.model_validate(model)

    # -- writes --------------------------------------------------------------
    async def create(
        self,
        payload: ModelCreate,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Model:
        provider = await self.providers.get(payload.provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        if await self.repository.get_by_name(provider.id, payload.name):
            raise ConflictError(
                "This provider already exposes a model with that name.",
                code="model_name_duplicate",
            )
        model = Model(
            provider_id=provider.id,
            name=payload.name,
            display_name=payload.display_name,
            context_window=payload.context_window,
            max_output_tokens=payload.max_output_tokens,
            input_price_per_1m=payload.input_price_per_1m,
            output_price_per_1m=payload.output_price_per_1m,
            capabilities=payload.capabilities,
            enabled=payload.enabled if payload.enabled is not None else True,
            deprecated=payload.deprecated if payload.deprecated is not None else False,
        )
        self.session.add(model)
        await self.session.flush()
        await self._ensure_default_endpoint(model, provider)
        await self.audit.record(
            AuditAction.MODEL_CREATED,
            actor=actor,
            entity_type="model",
            entity_id=str(model.id),
            diff={"provider_id": str(provider.id), "name": model.name, "manual": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return model

    async def update(
        self,
        model_id: uuid.UUID,
        payload: ModelWrite,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Model:
        model = await self.get(model_id)
        changes: dict[str, Any] = {}
        for field in MODEL_MUTABLE_FIELDS:
            value = getattr(payload, field, None)
            if value is None:
                continue
            if getattr(model, field) != value:
                changes[field] = {"from": _jsonable(getattr(model, field)), "to": _jsonable(value)}
                setattr(model, field, value)
        if changes:
            await self.session.flush()
            await self.audit.record(
                AuditAction.MODEL_UPDATED,
                actor=actor,
                entity_type="model",
                entity_id=str(model.id),
                diff=changes,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return model

    async def delete(
        self,
        model_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        model = await self.get(model_id)
        await self.audit.record(
            AuditAction.MODEL_DELETED,
            actor=actor,
            entity_type="model",
            entity_id=str(model.id),
            diff={"name": model.name, "provider_id": str(model.provider_id)},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.repository.delete(model)

    # -- helpers -------------------------------------------------------------
    async def _ensure_default_endpoint(self, model: Model, provider: Provider) -> None:
        """Give a new model its documented dispatch target instead of ``None``."""
        endpoints = ModelEndpointRepository(self.session)
        if await endpoints.count_for_model(model.id) > 0:
            return
        self.session.add(
            ModelEndpoint(
                model_id=model.id,
                provider_id=provider.id,
                path=default_chat_path(provider.kind, model.name),
                method="POST",
                streaming_supported=supports_streaming(provider.kind),
                enabled=True,
            )
        )
        await self.session.flush()


class EndpointService:
    """«نقاط اتصال مدل» — where a model is actually reachable."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ModelEndpointRepository(session)
        self.models = ModelRepository(session)
        self.credentials = CredentialRepository(session)
        self.audit = AuditService(session)

    async def list_for_model(self, model_id: uuid.UUID) -> Sequence[ModelEndpointRead]:
        await self._model_or_404(model_id)
        rows = await self.repository.list_for_model(model_id)
        return [ModelEndpointRead.model_validate(row) for row in rows]

    async def create(
        self,
        model_id: uuid.UUID,
        payload: ModelEndpointCreate,
        *,
        actor: AdminUser | None = None,
    ) -> ModelEndpoint:
        model = await self._model_or_404(model_id)
        self._validate_path(payload.path)
        await self._validate_credential(payload.credential_id, model.provider_id)
        endpoint = ModelEndpoint(
            model_id=model.id,
            provider_id=model.provider_id,
            credential_id=payload.credential_id,
            path=payload.path,
            method=payload.method.upper(),
            streaming_supported=payload.streaming_supported,
            param_map=payload.param_map,
            enabled=payload.enabled,
        )
        self.session.add(endpoint)
        await self.session.flush()
        await self.audit.record(
            AuditAction.ENDPOINT_CREATED,
            actor=actor,
            entity_type="model_endpoint",
            entity_id=str(endpoint.id),
            diff={"model_id": str(model.id), "path": endpoint.path},
        )
        return endpoint

    async def update(
        self,
        model_id: uuid.UUID,
        endpoint_id: uuid.UUID,
        payload: ModelEndpointUpdate,
        *,
        actor: AdminUser | None = None,
    ) -> ModelEndpoint:
        model = await self._model_or_404(model_id)
        endpoint = await self._endpoint_or_404(model_id, endpoint_id)
        if payload.path is not None:
            self._validate_path(payload.path)
        if payload.credential_id is not None or "credential_id" in payload.model_fields_set:
            await self._validate_credential(payload.credential_id, model.provider_id)
        changes: dict[str, Any] = {}
        for field in ENDPOINT_MUTABLE_FIELDS:
            if field not in payload.model_fields_set:
                continue
            value = getattr(payload, field)
            if field == "method" and isinstance(value, str):
                value = value.upper()
            if getattr(endpoint, field) != value:
                changes[field] = {
                    "from": _jsonable(getattr(endpoint, field)),
                    "to": _jsonable(value),
                }
                setattr(endpoint, field, value)
        if changes:
            await self.session.flush()
            await self.audit.record(
                AuditAction.ENDPOINT_UPDATED,
                actor=actor,
                entity_type="model_endpoint",
                entity_id=str(endpoint.id),
                diff=changes,
            )
        return endpoint

    async def delete(
        self,
        model_id: uuid.UUID,
        endpoint_id: uuid.UUID,
        *,
        actor: AdminUser | None = None,
    ) -> None:
        await self._model_or_404(model_id)
        endpoint = await self._endpoint_or_404(model_id, endpoint_id)
        await self.audit.record(
            AuditAction.ENDPOINT_DELETED,
            actor=actor,
            entity_type="model_endpoint",
            entity_id=str(endpoint.id),
            diff={"model_id": str(model_id), "path": endpoint.path},
        )
        await self.repository.delete(endpoint)

    # -- helpers -------------------------------------------------------------
    async def _model_or_404(self, model_id: uuid.UUID) -> Model:
        model = await self.models.get(model_id)
        if model is None:
            raise NotFoundError("The model does not exist.", code="model_not_found")
        return model

    async def _endpoint_or_404(self, model_id: uuid.UUID, endpoint_id: uuid.UUID) -> ModelEndpoint:
        endpoint = await self.repository.get(endpoint_id)
        if endpoint is None or endpoint.model_id != model_id:
            raise NotFoundError(
                "The endpoint does not belong to this model.", code="endpoint_not_found"
            )
        return endpoint

    async def _validate_credential(
        self, credential_id: uuid.UUID | None, provider_id: uuid.UUID
    ) -> None:
        if credential_id is None:
            return
        credential = await self.credentials.get(credential_id)
        if credential is None or credential.provider_id != provider_id:
            raise NotFoundError("The credential does not exist.", code="credential_not_found")

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/"):
            raise ValidationError(
                "The endpoint path must start with '/'.", code="endpoint_path_invalid"
            )


class DiscoveryService:
    """«کشف مدل‌ها» — reconcile the provider catalogue with the registry."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.providers = ProviderRepository(session)
        self.credentials = CredentialRepository(session)
        self.models = ModelRepository(session)
        self.endpoints = ModelEndpointRepository(session)
        self.audit = AuditService(session)

    async def discover(
        self,
        provider_id: uuid.UUID,
        *,
        overwrite_existing: bool = False,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ModelDiscoveryResultDetail:
        provider = await self.providers.get(provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        spec = get_spec(provider.kind)
        if not spec.supports_model_discovery:
            raise ValidationError(
                f"{provider.kind.value} does not expose a model catalogue.",
                code="provider_discovery_unsupported",
            )
        credential = await self.credentials.default_for_provider(provider.id)
        if credential is None:
            raise ConflictError(
                "Store a credential before discovering models.",
                code="credential_missing",
            )
        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=self._decrypt(credential),
            timeout_ms=provider.timeout_ms,
        )

        started = datetime.now(UTC)
        try:
            upstream_models = await adapter.list_models()
        except UpstreamError as exc:
            status = _health_for(exc.code)
            # The failed discovery request rolls back, but the observation about the
            # provider must not: it is written in its own transaction.
            await record_failure_observation(
                HealthTarget.provider(provider.id),
                HealthTarget.credential(credential.id, provider_id=provider.id),
                status=status,
                provider_id=provider.id,
                status_code=exc.status_code,
                error_code=exc.code,
            )
            raise AppError(
                exc.message,
                code=exc.code,
                status_code=502,
                details=exc.as_details(),
            ) from exc

        created = updated = skipped = failed = 0
        touched: list[Model] = []
        for entry in upstream_models:
            try:
                existing = await self.models.get_by_name(provider.id, entry.model_id)
                if existing is None:
                    model = Model(
                        provider_id=provider.id,
                        name=entry.model_id,
                        display_name=entry.display_name,
                        context_window=entry.context_window,
                        max_output_tokens=entry.max_output_tokens,
                        capabilities=entry.capabilities or None,
                        enabled=True,
                        deprecated=False,
                        discovered_at=started,
                    )
                    self.session.add(model)
                    await self.session.flush()
                    await self._ensure_endpoint(model, provider)
                    created += 1
                    touched.append(model)
                elif overwrite_existing:
                    existing.display_name = entry.display_name or existing.display_name
                    existing.context_window = entry.context_window or existing.context_window
                    existing.max_output_tokens = (
                        entry.max_output_tokens or existing.max_output_tokens
                    )
                    existing.capabilities = entry.capabilities or existing.capabilities
                    existing.discovered_at = started
                    await self.session.flush()
                    await self._ensure_endpoint(existing, provider)
                    updated += 1
                    touched.append(existing)
                else:
                    skipped += 1
            except Exception:  # pragma: no cover - defensive, keeps one bad row from failing all
                logger.warning("model_discovery_row_failed", extra={"model": entry.model_id})
                failed += 1

        await record_health_check(
            self.session,
            HealthTarget.provider(provider.id),
            status=HealthStatus.HEALTHY,
            latency_ms=None,
        )
        await record_health_check(
            self.session,
            HealthTarget.credential(credential.id, provider_id=provider.id),
            status=HealthStatus.HEALTHY,
        )
        provider.health_status = HealthStatus.HEALTHY.value
        await self.session.flush()

        await self.audit.record(
            AuditAction.MODELS_DISCOVERED,
            actor=actor,
            entity_type="provider",
            entity_id=str(provider.id),
            diff={
                "discovered": len(upstream_models),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
                "overwrite_existing": overwrite_existing,
                "credential_id": str(credential.id),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ModelDiscoveryResultDetail(
            provider_id=provider.id,
            provider_name=provider.name,
            discovered=len(upstream_models),
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            models=[ModelRead.model_validate(model) for model in touched],
        )

    async def _ensure_endpoint(self, model: Model, provider: Provider) -> None:
        if await self.endpoints.count_for_model(model.id) > 0:
            return
        self.session.add(
            ModelEndpoint(
                model_id=model.id,
                provider_id=provider.id,
                path=default_chat_path(provider.kind, model.name),
                method="POST",
                streaming_supported=supports_streaming(provider.kind),
                enabled=True,
            )
        )
        await self.session.flush()

    @staticmethod
    def _decrypt(credential: ProviderCredential) -> str:
        try:
            return decrypt_secret(credential.encrypted_secret)
        except EncryptionError as exc:  # pragma: no cover - depends on deployment key
            raise AppError(
                "The stored credential could not be decrypted.",
                code="credential_decryption_failed",
                status_code=500,
            ) from exc


class PlaygroundService:
    """«آزمایش مدل» — send one prompt through the real adapter."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.models = ModelRepository(session)
        self.endpoints = ModelEndpointRepository(session)
        self.credentials = CredentialRepository(session)
        self.providers = ProviderRepository(session)
        self.audit = AuditService(session)

    async def run(
        self,
        model_id: uuid.UUID,
        payload: ModelTestRequest,
        *,
        actor: AdminUser | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ModelTestResult:
        model, provider, credential = await self._resolve(model_id)
        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=self._decrypt(credential),
            timeout_ms=provider.timeout_ms,
        )
        started = datetime.now(UTC)
        try:
            result = await adapter.chat(
                model=model.name,
                messages=[ChatMessage(role="user", content=payload.prompt)],
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        except UpstreamError as exc:
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            await self._record_failure(provider, credential, model, exc, latency_ms)
            await self._audit(
                model,
                provider,
                credential,
                latency_ms=latency_ms,
                input_tokens=0,
                output_tokens=0,
                error_code=exc.code,
                actor=actor,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return ModelTestResult(
                model_id=model.id,
                provider_id=provider.id,
                latency_ms=latency_ms,
                input_tokens=0,
                output_tokens=0,
                output_text="",
                error_code=exc.code,
                finish_reason=None,
            )

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        await record_health_check(
            self.session,
            HealthTarget.model(model.id, provider_id=provider.id),
            status=HealthStatus.HEALTHY,
            latency_ms=latency_ms,
        )
        await record_health_check(
            self.session,
            HealthTarget.provider(provider.id),
            status=HealthStatus.HEALTHY,
            latency_ms=latency_ms,
        )
        provider.health_status = HealthStatus.HEALTHY.value
        await self.session.flush()
        await self._audit(
            model,
            provider,
            credential,
            latency_ms=latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            error_code=None,
            actor=actor,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ModelTestResult(
            model_id=model.id,
            provider_id=provider.id,
            latency_ms=latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            output_text=result.text,
            finish_reason=result.finish_reason,
        )

    async def stream(
        self,
        model_id: uuid.UUID,
        payload: ModelTestRequest,
        *,
        actor: AdminUser | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield plain dictionaries; the route renders them as SSE events."""
        model, provider, credential = await self._resolve(model_id)
        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=self._decrypt(credential),
            timeout_ms=provider.timeout_ms,
        )
        started = datetime.now(UTC)
        produced = 0
        try:
            async for delta in adapter.stream_chat(
                model=model.name,
                messages=[ChatMessage(role="user", content=payload.prompt)],
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            ):
                produced += len(delta)
                yield {"delta": delta}
        except UpstreamError as exc:
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            await self._record_failure(provider, credential, model, exc, latency_ms)
            await self._audit(
                model,
                provider,
                credential,
                latency_ms=latency_ms,
                input_tokens=0,
                output_tokens=0,
                error_code=exc.code,
                actor=actor,
            )
            yield {
                "done": True,
                "latency_ms": latency_ms,
                "output_tokens": 0,
                "error_code": exc.code,
                "detail": exc.message,
            }
            return

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        await record_health_check(
            self.session,
            HealthTarget.model(model.id, provider_id=provider.id),
            status=HealthStatus.HEALTHY,
            latency_ms=latency_ms,
        )
        await self.session.flush()
        await self._audit(
            model,
            provider,
            credential,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            error_code=None,
            actor=actor,
        )
        yield {
            "done": True,
            "latency_ms": latency_ms,
            # Streaming providers do not always report usage; the panel shows the
            # real value or «نامشخص», never an estimate presented as measured.
            "output_tokens": 0,
            "characters": produced,
            "finish_reason": "stop",
        }

    # -- helpers -------------------------------------------------------------
    async def _resolve(self, model_id: uuid.UUID) -> tuple[Model, Provider, ProviderCredential]:
        model = await self.models.get(model_id)
        if model is None:
            raise NotFoundError("The model does not exist.", code="model_not_found")
        provider = await self.providers.get(model.provider_id)
        if provider is None:
            raise NotFoundError("The provider does not exist.", code="provider_not_found")
        credential = await self._credential_for(model, provider)
        return model, provider, credential

    async def _credential_for(self, model: Model, provider: Provider) -> ProviderCredential:
        for endpoint in await self.endpoints.list_enabled_for_model(model.id):
            if endpoint.credential_id is not None:
                credential = await self.credentials.get(endpoint.credential_id)
                if credential is not None:
                    return credential
        credential = await self.credentials.default_for_provider(provider.id)
        if credential is None:
            raise ConflictError(
                "Store a credential before testing this model.",
                code="credential_missing",
            )
        return credential

    @staticmethod
    def _decrypt(credential: ProviderCredential) -> str:
        try:
            return decrypt_secret(credential.encrypted_secret)
        except EncryptionError as exc:  # pragma: no cover - depends on deployment key
            raise AppError(
                "The stored credential could not be decrypted.",
                code="credential_decryption_failed",
                status_code=500,
            ) from exc

    async def _record_failure(
        self,
        provider: Provider,
        credential: ProviderCredential,
        model: Model,
        exc: UpstreamError,
        latency_ms: int,
    ) -> None:
        status = _health_for(exc.code)
        for target in (
            HealthTarget.model(model.id, provider_id=provider.id),
            HealthTarget.provider(provider.id),
            HealthTarget.credential(credential.id, provider_id=provider.id),
        ):
            await record_health_check(
                self.session,
                target,
                status=status,
                latency_ms=latency_ms,
                status_code=exc.status_code,
                error_code=exc.code,
            )
        provider.health_status = status.value
        await self.session.flush()

    async def _audit(
        self,
        model: Model,
        provider: Provider,
        credential: ProviderCredential,
        *,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        error_code: str | None,
        actor: AdminUser | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self.audit.record(
            AuditAction.MODEL_TESTED,
            actor=actor,
            entity_type="model",
            entity_id=str(model.id),
            diff={
                "provider_id": str(provider.id),
                "credential_id": str(credential.id),
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_code": error_code,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )


def _health_for(error_code: str | None) -> HealthStatus:
    if error_code == "provider_rate_limited":
        return HealthStatus.RATE_LIMITED
    if error_code in {"provider_unauthorized", "provider_forbidden", "provider_model_not_found"}:
        return HealthStatus.DOWN
    if error_code in {
        "credential_missing",
        "provider_base_url_missing",
        "credential_decryption_failed",
    }:
        return HealthStatus.UNKNOWN
    return HealthStatus.DEGRADED


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, ProviderKind):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


__all__ = [
    "DiscoveryService",
    "EndpointService",
    "ModelService",
    "PlaygroundService",
]
