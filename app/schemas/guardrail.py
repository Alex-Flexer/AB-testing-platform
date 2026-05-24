from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel
from db.enums import GuardrailAction, ComparisonOperator


# =========================
#      Custom Types
# =========================

class MetricKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "metric_key must be a string (or string-convertible)")
        if not v:
            raise HTTPException(422, "metric_key must not be empty")
        if len(v) > 128:
            raise HTTPException(422, "metric_key is too long (max 128 chars)")
        return v


class Threshold(float):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            raise HTTPException(422, "threshold must be number")
        if isinstance(value, (int, float)):
            return float(value)
        raise HTTPException(422, "threshold must be number")


class WindowMinutes(int):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            raise HTTPException(422, "window_minutes must be integer")
        try:
            v = int(value)
        except (ValueError, TypeError):
            raise HTTPException(422, "window_minutes must be integer")

        if v <= 0:
            raise HTTPException(422, "window_minutes must be greater than 0")

        if v > 7 * 24 * 60:
            raise HTTPException(422, "window_minutes is too large (max 10080 minutes)")

        return v


class Operator:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "comparison_operator must be a string")

        try:
            return ComparisonOperator(v)
        except ValueError:
            raise HTTPException(
                422,
                f"comparison_operator must be one of: {', '.join(op.value for op in ComparisonOperator)}",
            )


class Action:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "action must be a string")

        try:
            return GuardrailAction(v)
        except ValueError:
            raise HTTPException(
                422,
                f"action must be one of: {', '.join(a.value for a in GuardrailAction)}",
            )


class EnabledBool:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return value
        raise HTTPException(422, "enabled must be boolean (true/false)")


# =========================
#        Schemas
# =========================

class GuardrailCreate(BodyModel):
    __required_fields__ = {
        "metric_key",
        "comparison_operator",
        "threshold",
        "window_minutes",
        "action"
    }

    metric_key: MetricKey
    comparison_operator: Operator
    threshold: Threshold
    window_minutes: WindowMinutes

    action: Action
    enabled: EnabledBool = True


class GuardrailUpdate(BodyModel):
    comparison_operator: Optional[Operator] = None
    threshold: Optional[Threshold] = None
    window_minutes: Optional[WindowMinutes] = None

    action: Optional[Action] = None
    enabled: Optional[EnabledBool] = None


class GuardrailOut(OutModel):
    id: UUID
    experiment_id: UUID

    metric_key: str
    comparison_operator: str
    threshold: float
    window_minutes: int

    action: str
    enabled: bool

    created_at: datetime


class Guardrails(BaseModel):
    items: List[GuardrailOut]
    total: int


class GuardrailTriggerOut(OutModel):
    id: UUID
    experiment_id: UUID
    guardrail_id: UUID

    metric_key: str
    comparison_operator: str
    threshold: float
    window_minutes: int

    action: str
    actual_value: float
    triggered_at: datetime


class GuardrailTriggers(BaseModel):
    items: List[GuardrailTriggerOut]
    total: int
