from db.enums import FlagType
import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel


# gpt made regex
_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,254}$")
_NUM_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


class FlagKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "flag key must be a string (or string-convertible)")

        if not value:
            raise HTTPException(422, "flag key must not be empty")

        # Common convention: keep keys stable and ascii-safe
        if not _KEY_RE.match(value):
            raise HTTPException(
                422,
                "flag key must match pattern: starts with a letter; allowed: letters, digits, '_', '-', '.', length 2..255",
            )

        return value


class Type:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "type must be a string")

        try:
            return FlagType(value)
        except ValueError:
            raise HTTPException(
                422,
                f"type must be one of: {', '.join(t.value for t in FlagType)}",
            )


class DefaultValue(str):
    """
    We keep DB storage as string (as in your models), but validate client input
    and store normalized string representation.
    Validation depends on flag type, so it's validated in FeatureFlagCreate/Update.
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (str, int, float)):
            return str(value).strip()

        raise HTTPException(422, "unsupported value type")


class Description(str):
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
            # If they send "", treat as invalid (use null to unset)
            raise HTTPException(422, "description must not be empty (use null to unset)")

        if len(value) > 5000:
            raise HTTPException(422, "description is too long (max 5000 chars)")

        return value


# =========================
# Pydantic Schemas
# =========================

class FeatureFlagCreate(BodyModel):
    __required_fields__ = {"key", "type", "default_value"}

    key: FlagKey
    type: Type
    default_value: DefaultValue
    description: Optional[Description] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        # Use default schema generation, then wrap with a post-validator
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        if data.type == FlagType.BOOL and data.default_value not in ("false", "true"):
            raise HTTPException(422, "default_value must be boolean for type=bool")

        if data.type == FlagType.NUMBER and not _NUM_RE.match(data.default_value):
            raise HTTPException(422, "default_value must be number for type=number")

        return data


class FeatureFlagUpdate(BodyModel):
    __required_fields__ = {"default_value"}

    # According to your spec: only default_value can be updated
    default_value: DefaultValue

    # We need flag type to validate; this schema is used with path flag_id,
    # so type will be taken from DB in service layer.
    # Therefore: we keep only raw default_value here; validate in service
    # OR add an alternative schema FeatureFlagUpdateWithType.

    # If you want validation *inside schema*, use this:
    # type: Type
    # and apply same cross-field validator as in create.


class FeatureFlagOut(OutModel):
    id: UUID
    key: FlagKey
    type: FlagType
    default_value: str
    description: Optional[str] = None
    created_at: datetime


class FeatureFlags(BaseModel):
    items: List[FeatureFlagOut]
    total: int
