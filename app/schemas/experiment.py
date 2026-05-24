import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from db.enums import ExperimentStatus, ReviewDecision
from schemas.base import BodyModel, OutModel


# =========================
#      Custom Types
# =========================

# gpt made regex
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{1,254}$")  # 2..255
_VARIANT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,31}$")  # A/B/control, etc.


class ExperimentName(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "name must be a string (or string-convertible)")

        if not value:
            raise HTTPException(422, "name must not be empty")

        if not _NAME_RE.match(value):
            raise HTTPException(
                422,
                "name must be 2..255 chars; allowed: letters, digits, spaces, '_', '-', '.', must start with alnum",
            )
        return value


class Text(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if value is None:
            return None
        try:
            value = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "description must be a string (or string-convertible)")
        if not value:
            raise HTTPException(422, "description must not be empty (use null to unset)")
        if len(value) > 20000:
            raise HTTPException(422, "description is too long (max 20000 chars)")
        return value


class TrafficPct(float):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = float(value)
        except (ValueError, TypeError):
            raise HTTPException(422, "traffic_percentage must be a number")

        if v <= 0 or v > 100:
            raise HTTPException(422, "traffic_percentage must be in range (0, 100]")

        v = round(v, 6)
        return v


class Weight(float):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = float(value)
        except (ValueError, TypeError):
            raise HTTPException(422, "weight must be a number")

        if v <= 0:
            raise HTTPException(422, "weight must be > 0")

        v = round(v, 6)
        return v


class VariantName(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "variant name must be a string")

        if not value:
            raise HTTPException(422, "variant name must not be empty")

        if not _VARIANT_NAME_RE.match(value):
            raise HTTPException(
                422,
                "variant name must match: starts with a letter; allowed: letters, digits, '_' '-', length 1..32",
            )
        return value


class VariantValue(str):
    """
    Значение варианта храним строкой (как в БД).
    Проверка соответствия типу флага (string/bool/number) должна делаться в сервисе,
    т.к. тип флага лежит в БД (feature_flag_id).
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        # допускаем bool/int/float/str -> строка
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (str, int, float)):
            v = str(value).strip()
            if v == "":
                raise HTTPException(422, "variant value must not be empty")
            if len(v) > 255:
                raise HTTPException(422, "variant value is too long (max 255 chars)")
            return v
        raise HTTPException(422, "unsupported variant value type")


class TargetingRule(str):
    """
    Тут DSL из ТЗ. Полную проверку парсера можно сделать позже.
    На уровне схемы: базовая проверка размера/пустоты.
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if value is None:
            return None
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "targeting_rule must be a string (or string-convertible)")
        if not v:
            raise HTTPException(422, "targeting_rule must not be empty (use null to unset)")
        if len(v) > 20000:
            raise HTTPException(422, "targeting_rule is too long (max 20000 chars)")
        return v


class IsControl:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return value
        raise HTTPException(422, "is_control must be boolean (true/false)")

# =========================
#   Variant Schemas
# =========================


class VariantCreate(BodyModel):
    __required_fields__ = {"name", "value", "weight", "is_control"}

    name: VariantName
    value: VariantValue
    weight: Weight
    is_control: IsControl


class VariantUpdate(BodyModel):
    name: Optional[VariantName] = None
    value: Optional[VariantValue] = None
    weight: Optional[Weight] = None
    is_control: Optional[IsControl] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._not_empty_patch, schema)

    @classmethod
    def _not_empty_patch(cls, data):
        # запретить пустой объект {}
        if data.name is None and data.value is None and data.weight is None and data.is_control is None:
            raise HTTPException(422, "at least one field must be provided")
        return data


class VariantOut(OutModel):
    id: UUID
    experiment_id: UUID
    name: str
    value: str
    weight: float
    is_control: bool


# =========================
#  Experiment Schemas
# =========================

class ExperimentCreate(BodyModel):
    __required_fields__ = {"name", "feature_flag_id", "traffic_percentage", "variants"}

    name: ExperimentName
    description: Optional[Text] = None

    feature_flag_id: UUID
    traffic_percentage: TrafficPct

    targeting_rule: Optional[TargetingRule] = None

    # Варианты создаём сразу вместе с экспериментом
    variants: List[VariantCreate]

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        if not data.variants or len(data.variants) < 1:
            raise HTTPException(422, "variants must contain at least 1 item")

        # ровно один control
        if sum(v.is_control for v in data.variants) != 1:
            raise HTTPException(422, "exactly one variant must be control (is_control=true)")

        # имена уникальны (на уровне схемы)
        names = [v.name for v in data.variants]
        if len(set(names)) != len(names):
            raise HTTPException(422, "variant names must be unique within experiment")

        # сумма весов = traffic_percentage (как в ТЗ)
        total_weight = round(sum(v.weight for v in data.variants), 6)
        expected = round(float(data.traffic_percentage), 6)
        if total_weight != expected:
            raise HTTPException(
                422,
                f"sum of variant weights must equal traffic_percentage ({expected}), got {total_weight}",
            )

        return data


class ExperimentUpdate(BodyModel):
    """
    PATCH эксперимента (только в DRAFT по бизнес-правилам).
    Заморозку после RUNNING/PAUSED запретишь в сервисе.
    """
    name: Optional[ExperimentName] = None
    description: Optional[Text] = None
    traffic_percentage: Optional[TrafficPct] = None
    targeting_rule: Optional[TargetingRule] = None

    # если хочешь позволить обновлять варианты через PATCH эксперимента (можно, но сложнее):
    # variants: Optional[List[VariantCreate]] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._not_empty_patch, schema)

    @classmethod
    def _not_empty_patch(cls, data):
        if (
            data.name is None
            and data.description is None
            and data.traffic_percentage is None
            and data.targeting_rule is None
        ):
            raise HTTPException(422, "at least one field must be provided")
        return data


class ExperimentOut(OutModel):
    id: UUID
    name: str
    description: Optional[str] = None

    status: ExperimentStatus

    traffic_percentage: float
    targeting_rule: Optional[str] = None

    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None

    feature_flag_id: UUID
    owner_id: UUID

    created_at: datetime
    current_version: int

    variants: List[VariantOut] = []


class Experiments(BaseModel):
    items: List[ExperimentOut]
    total: int


# =========================
#   Review Schemas (basic)
# =========================

class ReviewComment(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if value is None:
            return None
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "comment must be a string (or string-convertible)")
        if not v:
            raise HTTPException(422, "comment must not be empty (use null to unset)")
        if len(v) > 10000:
            raise HTTPException(422, "comment is too long (max 10000 chars)")
        return v


class Decision:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "decision must be string")

        try:
            return ReviewDecision(value)
        except ValueError:
            raise HTTPException(
                422,
                f"decision must be one of: {', '.join(d.value for d in ReviewDecision)}"
            )


class ExperimentSubmitForReview(BodyModel):
    comment: Optional[ReviewComment] = None


class ExperimentReviewDecision(BodyModel):
    __required_fields__ = {"decision"}

    decision: Decision
    comment: Optional[ReviewComment] = None
