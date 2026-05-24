from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel
from schemas.metric import MetricKey
from db.enums import TimeGranularity


class ReportTs(datetime):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            s = value.strip()
            if not s:
                raise HTTPException(422, "timestamp must not be empty")
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                raise HTTPException(422, "timestamp must be ISO8601 datetime string")

        raise HTTPException(422, "timestamp must be datetime or ISO8601 string")


class MetricKeys:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if value is None:
            return None

        if not isinstance(value, list):
            raise HTTPException(422, "metric_keys must be a list")

        if len(value) == 0:
            raise HTTPException(422, "metric_keys must not be empty")

        if len(value) > 50:
            raise HTTPException(422, "metric_keys list is too large (max 50)")

        keys: List[str] = []
        for i, item in enumerate(value):
            try:
                keys.append(MetricKey.validate(item))
            except HTTPException as e:
                raise HTTPException(422, f"metric_keys[{i}]: {e.detail}")
        return keys


class IncludeTimeseriesBool:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return value
        raise HTTPException(422, "include_timeseries must be boolean (true/false)")


class Granularity:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if value is None:
            return None
        try:
            v = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "granularity must be a string")

        try:
            return TimeGranularity(v)
        except Exception:
            raise HTTPException(
                422, f"granularity must be one of: {', '.join(g.value for g in TimeGranularity)}")


class ReportRequest(BodyModel):
    __required_fields__ = {"from_ts", "to_ts"}

    from_ts: ReportTs
    to_ts: ReportTs

    metric_keys: Optional[MetricKeys] = None

    include_timeseries: IncludeTimeseriesBool = False
    granularity: Optional[Granularity] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        if data.to_ts <= data.from_ts:
            raise HTTPException(422, "to_ts must be greater than from_ts")

        max_days = 90
        if (data.to_ts - data.from_ts).days > max_days:
            raise HTTPException(422, f"report window is too large (max {max_days} days)")

        if data.include_timeseries:
            if data.granularity is None:
                raise HTTPException(422, "granularity is required when include_timeseries=true")
        else:
            if data.granularity is not None:
                raise HTTPException(422, "granularity is allowed only when include_timeseries=true")

        return data


class MetricValue(BaseModel):
    raw: float
    aux: Optional[Dict[str, float]] = None


class VariantReport(BaseModel):
    variant_id: UUID
    variant_name: str
    is_control: bool

    metrics: Dict[str, MetricValue]


class TimeseriesPoint(BaseModel):
    ts: datetime
    value: float


class VariantMetricTimeseries(BaseModel):
    metric_key: str
    points: List[TimeseriesPoint]


class VariantTimeseries(BaseModel):
    variant_id: UUID
    variant_name: str

    series: List[VariantMetricTimeseries]


class ReportContext(BaseModel):
    from_ts: datetime
    to_ts: datetime
    unit: str
    include_timeseries: bool
    granularity: Optional[str] = None


class ExperimentReport(OutModel):
    experiment_id: UUID
    generated_at: datetime

    context: ReportContext

    variants: List[VariantReport]

    timeseries: Optional[List[VariantTimeseries]] = None
