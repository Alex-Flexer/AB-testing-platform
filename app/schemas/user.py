from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema
import re
from db.enums import UserRole

from schemas.base import BodyModel, OutModel


# gpt made regex
_RE_EMAIL = re.compile(r"""(?:[a-z0-9!#$%&'*+\x2f=?^_`\x7b-\x7d~\x2d]+(?:\.[a-z0-9!#$%&'*+\x2f=?^_`\x7b-\x7d~\x2d]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9\x2d]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9\x2d]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9\x2d]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])""")


class Email(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def __validate_email(cls, email: str) -> bool:
        return _RE_EMAIL.match(email) is not None

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "email must be a string (or string-convertible)")

        if not cls.__validate_email(value):
            raise HTTPException(422, "incorrect email format")

        if len(value) > 255:
            raise HTTPException(422, "email is too long (max 255 chars)")

        return value


class Password(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "password must be a string (or string-convertible)")

        if not value:
            raise HTTPException(422, "password must not be empty")

        if len(value) > 255:
            raise HTTPException(422, "email is too long (max 255 chars)")

        if len(value) < 8:
            raise HTTPException(422, "email is too short (min 8 chars)")

        return value


class Role:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            value = str(value).strip().lower()
        except (ValueError, TypeError):
            raise HTTPException(422, "role must be a string")

        try:
            return UserRole(value)
        except Exception:
            raise HTTPException(
                422,
                f"role must be one of: {', '.join(sorted(r.value for r in UserRole))}"
            )


class ActiveBool:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        # allow typical "truthy" forms as convenience
        if isinstance(value, bool):
            return value

        raise HTTPException(422, "is_active must be boolean (true/false)")


# =========================
# Pydantic Schemas
# =========================

class UserCreate(BodyModel):
    __required_fields__ = {"email", "password"}

    email: Email
    password: Password

    role: Role = UserRole.VIEWER
    is_active: ActiveBool = True


class UserUpdate(BodyModel):
    # PATCH semantics: only provided fields should be updated
    email: Optional[Email] = None
    role: Optional[Role] = None
    is_active: Optional[ActiveBool] = None


class UserOut(OutModel):
    id: UUID
    email: Email
    role: UserRole
    is_active: bool
    created_at: datetime


class Users(BaseModel):
    items: list[UserOut]
    total: int
