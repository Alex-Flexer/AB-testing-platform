import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel
from db.enums import AggregationType as AggregationEnum

# gpt made regex
_METRIC_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{1,127}$")  # 2..128


class MetricKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "metric key must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "metric key must not be empty")

        if not _METRIC_KEY_RE.match(v):
            raise HTTPException(
                422,
                "metric key must match pattern: starts with a letter; allowed: letters, digits, '_', '-', '.', length 2..128",
            )
        return v


class MetricTitle(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "metric name must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "metric name must not be empty")

        if len(v) > 255:
            raise HTTPException(422, "metric name is too long (max 255 chars)")

        return v


class EventKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "event key must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "event key must not be empty")

        if len(v) > 128:
            raise HTTPException(422, "event key is too long (max 128 chars)")

        if not _METRIC_KEY_RE.match(v):
            raise HTTPException(
                422,
                "event key must match pattern: starts with a letter; allowed: letters, digits, '_', '-', '.', length 2..128",
            )

        return v


class Aggregation:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "aggregation_type must be a string")

        try:
            return AggregationEnum(v)
        except ValueError:
            raise HTTPException(
                422,
                f"aggregation_type must be one of: {', '.join(a.value for a in AggregationEnum)}",
            )


class RequiresExposureBool:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return value
        raise HTTPException(422, "requires_exposure must be boolean (true/false)")


class FieldPath(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "metric name must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "metric name must not be empty")

        if len(v) > 255:
            raise HTTPException(422, "metric name is too long (max 255 chars)")

        return v


class MetricCreate(BodyModel):
    __required_fields__ = {"key", "name", "aggregation_type"}

    key: MetricKey
    name: MetricTitle

    aggregation_type: Aggregation

    numerator_event: Optional[EventKey] = None
    denominator_event: Optional[EventKey] = None

    field_path: Optional[FieldPath] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        agg = data.aggregation_type

        if agg in (AggregationEnum.AVG, AggregationEnum.P95):
            if data.field_path is None:
                raise HTTPException(422, "field_path is required when aggregation_type=avg or p95")

            if (data.numerator_event or data.denominator_event) is not None:
                raise HTTPException(
                    422, "numerator_event and denominator_event are not allowed when aggregation_type=avg or p95")

            return data

        if agg == AggregationEnum.RATE:
            if data.field_path is not None:
                raise HTTPException(422, "field_path is not allowed when aggregation_type=rate")

            if data.numerator_event is None:
                raise HTTPException(422, "numerator_event is required when aggregation_type=rate")

            if data.denominator_event is None:
                raise HTTPException(422, "denominator_event is required when aggregation_type=rate")

            return data

        if data.denominator_event is not None:
            raise HTTPException(422, "denominator_event is allowed only when aggregation_type=rate")

        if data.field_path is not None:
            raise HTTPException(422, "field_path is allowed only when aggregation_type=avg or p95")

        if data.numerator_event is None:
            raise HTTPException(
                422, "numerator_event is required when aggregation_type=count or unique_count")

        return data


class MetricOut(OutModel):
    id: UUID
    key: str
    name: str

    aggregation_type: str

    numerator_event: Optional[str] = None
    denominator_event: Optional[str] = None
    field_path: Optional[str] = None

    requires_exposure: bool

    created_by: Optional[UUID] = None
    created_at: datetime


class Metrics(BaseModel):
    items: List[MetricOut]
    total: int


class MetricUpdate(BodyModel):
    name: Optional[MetricTitle] = None
    description: Optional[str] = None
    aggregation_type: Optional[Aggregation] = None

    numerator_event: Optional[EventKey] = None
    denominator_event: Optional[EventKey] = None
    field_path: Optional[FieldPath] = None

    requires_exposure: Optional[RequiresExposureBool] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._not_empty_patch, schema)

    @classmethod
    def _not_empty_patch(cls, data):
        if (
            data.name is None
            and data.description is None
            and data.aggregation_type is None
            and data.numerator_event is None
            and data.denominator_event is None
            and data.field_path is None
            and data.requires_exposure is None
        ):
            raise HTTPException(422, "at least one field must be provided")
        return data
