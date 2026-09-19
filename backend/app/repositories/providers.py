"""Repositories for providers, credentials, models and model endpoints (M2/M3)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select

from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.repositories.base import BaseRepository


def _like(value: str) -> str:
    return f"%{value.strip().lower()}%"


class ProviderRepository(BaseRepository[Provider]):
    model = Provider

    def filtered(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        kind: str | None = None,
    ) -> Select:
        statement = select(Provider)
        if search:
            statement = statement.where(
                or_(
                    func.lower(Provider.name).like(_like(search)),
                    func.lower(Provider.slug).like(_like(search)),
                )
            )
        if enabled is not None:
            statement = statement.where(Provider.enabled.is_(enabled))
        if kind is not None:
            statement = statement.where(Provider.kind == kind)
        return statement

    async def list_filtered(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 25,
        order_by: str = "priority",
    ) -> Sequence[Provider]:
        statement = self.filtered(search=search, enabled=enabled, kind=kind)
        statement = statement.order_by(*self._order(order_by)).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        search: str | None = None,
        enabled: bool | None = None,
        kind: str | None = None,
    ) -> int:
        statement = self.filtered(search=search, enabled=enabled, kind=kind).with_only_columns(
            func.count(Provider.id)
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def slug_exists(self, slug: str, *, exclude_id: uuid.UUID | None = None) -> bool:
        statement = select(func.count(Provider.id)).where(Provider.slug == slug)
        if exclude_id is not None:
            statement = statement.where(Provider.id != exclude_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one()) > 0

    async def counts(self, provider_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        """Credential and model counts per provider, in two queries instead of N."""
        result: dict[uuid.UUID, dict[str, int]] = {
            provider_id: {"credential_count": 0, "model_count": 0} for provider_id in provider_ids
        }
        if not provider_ids:
            return result

        credential_rows = await self.session.execute(
            select(ProviderCredential.provider_id, func.count(ProviderCredential.id))
            .where(ProviderCredential.provider_id.in_(provider_ids))
            .group_by(ProviderCredential.provider_id)
        )
        for provider_id, count in credential_rows.all():
            result[provider_id]["credential_count"] = int(count)

        model_rows = await self.session.execute(
            select(Model.provider_id, func.count(Model.id))
            .where(Model.provider_id.in_(provider_ids))
            .group_by(Model.provider_id)
        )
        for provider_id, count in model_rows.all():
            result[provider_id]["model_count"] = int(count)
        return result

    @staticmethod
    def _order(order_by: str):
        mapping = {
            "priority": (Provider.priority.asc(), Provider.name.asc()),
            "name": (Provider.name.asc(),),
            "-name": (Provider.name.desc(),),
            "created_at": (Provider.created_at.asc(),),
            "-created_at": (Provider.created_at.desc(),),
        }
        return mapping.get(order_by, mapping["priority"])


class CredentialRepository(BaseRepository[ProviderCredential]):
    model = ProviderCredential

    async def list_for_provider(
        self, provider_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> Sequence[ProviderCredential]:
        result = await self.session.execute(
            select(ProviderCredential)
            .where(ProviderCredential.provider_id == provider_id)
            .order_by(ProviderCredential.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_for_provider(self, provider_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(ProviderCredential.id)).where(
                ProviderCredential.provider_id == provider_id
            )
        )
        return int(result.scalar_one())

    async def default_for_provider(self, provider_id: uuid.UUID) -> ProviderCredential | None:
        """The credential used when an endpoint does not name one explicitly."""
        result = await self.session.execute(
            select(ProviderCredential)
            .where(ProviderCredential.provider_id == provider_id)
            .order_by(ProviderCredential.created_at.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def label_exists(
        self, provider_id: uuid.UUID, label: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        statement = select(func.count(ProviderCredential.id)).where(
            ProviderCredential.provider_id == provider_id,
            func.lower(ProviderCredential.label) == label.strip().lower(),
        )
        if exclude_id is not None:
            statement = statement.where(ProviderCredential.id != exclude_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one()) > 0

    async def used_by_endpoints(self, credential_id: uuid.UUID) -> int:
        """How many endpoints bind this credential explicitly (reference check)."""
        result = await self.session.execute(
            select(func.count(ModelEndpoint.id)).where(ModelEndpoint.credential_id == credential_id)
        )
        return int(result.scalar_one())


class ModelRepository(BaseRepository[Model]):
    model = Model

    def filtered(
        self,
        *,
        search: str | None = None,
        provider_id: uuid.UUID | None = None,
        enabled: bool | None = None,
        deprecated: bool | None = None,
    ) -> Select:
        statement = select(Model)
        if search:
            statement = statement.where(
                or_(
                    func.lower(Model.name).like(_like(search)),
                    func.lower(func.coalesce(Model.display_name, "")).like(_like(search)),
                )
            )
        if provider_id is not None:
            statement = statement.where(Model.provider_id == provider_id)
        if enabled is not None:
            statement = statement.where(Model.enabled.is_(enabled))
        if deprecated is not None:
            statement = statement.where(Model.deprecated.is_(deprecated))
        return statement

    async def list_filtered(
        self,
        *,
        search: str | None = None,
        provider_id: uuid.UUID | None = None,
        enabled: bool | None = None,
        deprecated: bool | None = None,
        offset: int = 0,
        limit: int = 25,
        order_by: str = "name",
    ) -> Sequence[Model]:
        statement = self.filtered(
            search=search, provider_id=provider_id, enabled=enabled, deprecated=deprecated
        )
        statement = statement.order_by(*self._order(order_by)).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def count_filtered(
        self,
        *,
        search: str | None = None,
        provider_id: uuid.UUID | None = None,
        enabled: bool | None = None,
        deprecated: bool | None = None,
    ) -> int:
        statement = self.filtered(
            search=search, provider_id=provider_id, enabled=enabled, deprecated=deprecated
        ).with_only_columns(func.count(Model.id))
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def get_by_name(self, provider_id: uuid.UUID, name: str) -> Model | None:
        result = await self.session.execute(
            select(Model).where(Model.provider_id == provider_id, Model.name == name)
        )
        return result.scalars().first()

    @staticmethod
    def _order(order_by: str):
        mapping = {
            "name": (Model.name.asc(),),
            "-name": (Model.name.desc(),),
            "created_at": (Model.created_at.asc(),),
            "-created_at": (Model.created_at.desc(),),
            "provider": (Model.provider_id.asc(), Model.name.asc()),
        }
        return mapping.get(order_by, mapping["name"])


class ModelEndpointRepository(BaseRepository[ModelEndpoint]):
    model = ModelEndpoint

    async def list_for_model(
        self, model_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> Sequence[ModelEndpoint]:
        result = await self.session.execute(
            select(ModelEndpoint)
            .where(ModelEndpoint.model_id == model_id)
            .order_by(ModelEndpoint.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def count_for_model(self, model_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(ModelEndpoint.id)).where(ModelEndpoint.model_id == model_id)
        )
        return int(result.scalar_one())

    async def count_for_provider(self, provider_id: uuid.UUID) -> int:
        """Endpoints reached through models of one provider (used by delete impact)."""
        result = await self.session.execute(
            select(func.count(ModelEndpoint.id))
            .join(Model, Model.id == ModelEndpoint.model_id)
            .where(Model.provider_id == provider_id)
        )
        return int(result.scalar_one())

    async def list_enabled_for_model(self, model_id: uuid.UUID) -> Sequence[ModelEndpoint]:
        result = await self.session.execute(
            select(ModelEndpoint)
            .where(ModelEndpoint.model_id == model_id, ModelEndpoint.enabled.is_(True))
            .order_by(ModelEndpoint.created_at.asc())
        )
        return result.scalars().all()


__all__ = [
    "CredentialRepository",
    "ModelEndpointRepository",
    "ModelRepository",
    "ProviderRepository",
]
