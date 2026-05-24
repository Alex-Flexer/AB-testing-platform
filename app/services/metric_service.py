from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import AggregationType as AggregationEnum
from db.repositories.metrics_repo import MetricRepository
from exceptions.app_exceptions import (
    AppException,
    UnprocessableEntity,
    MetricKeyAlreadyExists,
    MetricNotFound
)


class MetricService:
    def __init__(self):
        self.repo = MetricRepository

    @staticmethod
    def _normalize_event_key(v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @staticmethod
    def _normalize_field_path(v: str | None) -> str | None:
        return str(v).strip() if v is not None else None

    @classmethod
    def _validate_agg_fields(
        cls,
        aggregation_type: AggregationEnum,
        numerator_event: str | None,
        denominator_event: str | None,
        field_path: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        num = cls._normalize_event_key(numerator_event)
        den = cls._normalize_event_key(denominator_event)
        fp = cls._normalize_field_path(field_path)

        agg = aggregation_type

        if agg in (AggregationEnum.AVG, AggregationEnum.P95):
            if fp is None:
                raise UnprocessableEntity("field_path is required when aggregation_type=avg or p95")

            return None, None, fp

        if agg == AggregationEnum.RATE:
            if num is None:
                raise UnprocessableEntity("numerator_event is required when aggregation_type=rate")

            if den is None:
                raise UnprocessableEntity(
                    "denominator_event is required when aggregation_type=rate")

            return num, den, None

        if num is None:
            raise UnprocessableEntity(
                "numerator_event is required when aggregation_type=count or unique_count")
        return num, None, None

    async def create_metric(self, session: AsyncSession, data, created_by: UUID | None):
        existing = await self.repo.get_by_key(session, data.key)
        if existing is not None:
            raise MetricKeyAlreadyExists()

        numerator_event, denominator_event, field_path = self._validate_agg_fields(
            aggregation_type=data.aggregation_type,
            numerator_event=getattr(data, "numerator_event", None),
            denominator_event=getattr(data, "denominator_event", None),
            field_path=getattr(data, "field_path", None),
        )

        try:
            m = await self.repo.create(
                session,
                key=str(data.key),
                name=str(data.name),
                description=getattr(data, "description", None),
                aggregation_type=data.aggregation_type,
                numerator_event=numerator_event,
                denominator_event=denominator_event,
                field_path=field_path,
                requires_exposure=bool(getattr(data, "requires_exposure", False)),
                created_by=created_by,
            )
            await session.commit()
            return m

        except IntegrityError:
            await session.rollback()
            raise MetricKeyAlreadyExists()

        except Exception:
            await session.rollback()
            raise AppException()

    async def get_metric(self, session: AsyncSession, metric_id: UUID):
        m = await self.repo.get_by_id(session, metric_id)
        if m is None:
            raise MetricNotFound()
        return m

    async def list_metrics(self, session: AsyncSession, *, offset: int = 0, limit: int = 50):
        if offset < 0:
            raise UnprocessableEntity("offset must be >= 0")

        if limit <= 0 or limit > 200:
            raise UnprocessableEntity("limit must be in range 1..200")

        items = await self.repo.list(session, offset=offset, limit=limit)
        total = await self.repo.count(session)
        return items, total

    async def update_metric(self, session: AsyncSession, metric_id: UUID, data):
        m = await self.repo.get_by_id(session, metric_id)
        if m is None:
            raise MetricNotFound()

        new_name = getattr(data, "name", None)
        new_desc = getattr(data, "description", None)
        new_requires_exposure = getattr(data, "requires_exposure", None)

        agg = getattr(data, "aggregation_type", None)
        num = getattr(data, "numerator_event", None)
        den = getattr(data, "denominator_event", None)
        fp = getattr(data, "field_path", None)

        effective_agg = agg if agg is not None else m.aggregation_type

        touched_agg_fields = any(x is not None for x in (agg, num, den, fp))

        if touched_agg_fields:
            numerator_event, denominator_event, field_path = self._validate_agg_fields(
                aggregation_type=effective_agg,
                numerator_event=num if num is not None else m.numerator_event,
                denominator_event=den if den is not None else m.denominator_event,
                field_path=fp if fp is not None else m.field_path,
            )
        else:
            numerator_event, denominator_event, field_path = m.numerator_event, m.denominator_event, m.field_path

        try:
            m = await self.repo.update(
                session,
                m,
                name=new_name,
                description=new_desc,
                aggregation_type=agg,
                numerator_event=numerator_event,
                denominator_event=denominator_event,
                field_path=field_path,
                requires_exposure=new_requires_exposure,
            )
            await session.commit()
            return m

        except IntegrityError:
            await session.rollback()
            raise MetricKeyAlreadyExists()

        except Exception:
            await session.rollback()
            raise AppException()

    async def delete_metric(self, session: AsyncSession, metric_id: UUID):
        try:
            deleted = await self.repo.delete_by_id(session, metric_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise AppException()

        if not deleted:
            raise MetricNotFound()
