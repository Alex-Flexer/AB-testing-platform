import re
from datetime import datetime, date
from typing import List, Optional, Union
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel


# =========================
#      Custom Types
# =========================

_FLAG_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,254}$")


AttrValue = Union[str, int, float, bool, date]


class SubjectId(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "subject_id must be a string (or string-convertible)")
        if not v:
            raise HTTPException(422, "subject_id must not be empty")
        if len(v) > 255:
            raise HTTPException(422, "subject_id is too long (max 255 chars)")
        return v


class FlagKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "flag key must be a string")
        if not v:
            raise HTTPException(422, "flag key must not be empty")
        if not _FLAG_KEY_RE.match(v):
            raise HTTPException(
                422,
                "flag key must match pattern: starts with a letter; allowed: letters, digits, '_', '-', '.', length 2..255",
            )
        return v


class FlagKeys:
    """
    Wrapper type to validate list[FlagKey] with custom error message.
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if not isinstance(value, list):
            raise HTTPException(422, "flags must be a list of flag keys")
        if len(value) == 0:
            raise HTTPException(422, "flags must not be empty")
        if len(value) > 200:
            raise HTTPException(422, "flags list is too large (max 200)")

        keys: List[str] = []
        for i, item in enumerate(value):
            try:
                keys.append(FlagKey.validate(item))
            except HTTPException as e:
                raise HTTPException(422, f"flags[{i}]: {e.detail}")
        return keys


class Attributes:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def _validate_attrs(cls, value, path: str = "", depth: int = 0):
        if depth > 12:
            raise HTTPException(422, "attributes is too deep (max depth 12)")

        if value is None:
            return None

        if isinstance(value, dict) and len(value) > 200:
            raise HTTPException(422, "attributes object is too large (max 200 keys)")

        if isinstance(value, str) and len(value) > 2000:
            raise HTTPException(
                422, f"attributes '{path}' string value is too long (max 2000 chars)")

        if isinstance(value, list):
            if len(value) > 200:
                raise HTTPException(422, f"attributes '{path}' list is too large (max 200 items)")

            for idx, sub in enumerate(value):
                new_path = f"{path}->{idx}" if path else str(idx)
                cls._validate_attrs(sub, path=path, depth=depth + 1)

        elif isinstance(value, dict):
            for k, v in value.items():
                try:
                    k = str(k).strip()

                except (ValueError, TypeError):
                    raise HTTPException(422, "attribute keys must be string-convertible")

                new_path = f"{path}->{k}" if path else k

                if '.' in k:
                    raise HTTPException(422,  f"{new_path} - keys must not contain '.'")

                cls._validate_attrs(v, new_path, depth + 1)

        elif not isinstance(value, (int, float, str, list, dict)):
            raise HTTPException(422, f"attribute '{path}' has unsupported type")

    @classmethod
    def validate(cls, value):
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise HTTPException(422, "attributes must be an object (key-value map)")

        cls._validate_attrs(value)
        return value


# =========================
# Pydantic Schemas
# =========================

class DecideRequest(BodyModel):
    __required_fields__ = {"subject_id", "flags"}

    subject_id: SubjectId
    flags: FlagKeys
    attributes: Optional[Attributes] = None


class DecisionMeta(BaseModel):
    """
    Metadata returned for each flag decision.
    """
    decision_id: UUID
    experiment_id: Optional[UUID] = None
    variant_id: Optional[UUID] = None
    variant_name: Optional[str] = None
    is_default: bool


class FlagDecision(BaseModel):
    flag_key: str
    value: str
    meta: DecisionMeta


class DecideResponse(BaseModel):
    subject_id: str
    decisions: List[FlagDecision]
    decided_at: datetime
