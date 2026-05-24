from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel
from db.enums import MetricRole as MetricRoleEnum


class MetricRole(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "role must be a string")

        try:
            return MetricRoleEnum(v).value
        except Exception:
            raise HTTPException(
                422, f"role must be one of: {', '.join(x.value for x in MetricRoleEnum)}")


class ExperimentMetricAttach(BodyModel):
    __required_fields__ = {"metric_id"}

    metric_id: UUID
    role: MetricRole = "secondary"


class MetricShort(BaseModel):
    id: UUID
    key: str
    name: str
    aggregation_type: str


class ExperimentMetricOut(OutModel):
    id: UUID
    experiment_id: UUID
    metric_id: UUID
    role: str
    created_at: datetime


class ExperimentMetrics(BaseModel):
    items: List[ExperimentMetricOut]
    total: int
