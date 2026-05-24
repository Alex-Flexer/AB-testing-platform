import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel


# =========================
#      Custom Types
# =========================

_EVENT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{1,127}$")


class EventName(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "event_name must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "event_name must not be empty")

        if not _EVENT_NAME_RE.match(v):
            raise HTTPException(
                422,
                "event_name must match pattern: starts with a letter; allowed: letters, digits, '_', '.', ':', '-', length 2..128",
            )
        return v


class IdempotencyKey(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        try:
            v = str(value).strip()
        except (ValueError, TypeError):
            raise HTTPException(422, "idempotency_key must be a string (or string-convertible)")

        if not v:
            raise HTTPException(422, "idempotency_key must not be empty")

        if len(v) > 255:
            raise HTTPException(422, "idempotency_key is too long (max 255 chars)")

        return v


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


class Props:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def _validate_props(cls, value, path: str = "", depth: int = 0):
        if depth > 12:
            raise HTTPException(422, "props is too deep (max depth 12)")

        if value is None:
            return None

        if isinstance(value, dict) and len(value) > 200:
            raise HTTPException(422, "props object is too large (max 200 keys)")

        if isinstance(value, str) and len(value) > 2000:
            raise HTTPException(422, f"props '{path}' string value is too long (max 2000 chars)")

        if isinstance(value, list):
            if len(value) > 200:
                raise HTTPException(422, f"props '{path}' list is too large (max 200 items)")

            for idx, sub in enumerate(value):
                new_path = f"{path}->{idx}" if path else str(idx)
                cls._validate_props(sub, path, depth + 1)

        elif isinstance(value, dict):
            for k, v in value.items():
                try:
                    k = str(k).strip()

                except (ValueError, TypeError):
                    raise HTTPException(422, "props keys must be string-convertible")

                new_path = f"{path}->{k}" if path else k

                if '.' in k:
                    raise HTTPException(422, f"{new_path} - keys must not contain '.")

                cls._validate_props(v, new_path, depth + 1)

        elif not isinstance(value, (int, float, str, list, dict)):
            raise HTTPException(422, f"props '{path}' has unsupported type")

    @classmethod
    def validate(cls, value):
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise HTTPException(422, "props must be an object (key-value map)")

        cls._validate_props(value)
        return value


class EventTs(datetime):
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
                raise HTTPException(422, "ts must not be empty")
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                raise HTTPException(422, "ts must be ISO8601 datetime string")

        raise HTTPException(422, "ts must be datetime or ISO8601 string")


# =========================
# Pydantic Schemas
# =========================

class EventIn(BodyModel):
    __required_fields__ = {
        "idempotency_key",
        "decision_id",
        "event_name",
        "ts"
    }

    idempotency_key: IdempotencyKey
    decision_id: UUID

    event_name: EventName
    ts: EventTs

    props: Optional[Props] = None


class EventsIn(BodyModel):
    """
    Batch ingest request.
    """
    __required_fields__ = {"events"}

    events: List[EventIn]

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_events, schema)

    @classmethod
    def _validate_events(cls, data):
        if not data.events or len(data.events) == 0:
            raise HTTPException(422, "events must not be empty")

        if len(data.events) > 1000:
            raise HTTPException(422, "events batch is too large (max 1000)")
        return data


class EventRejectInfo(BaseModel):
    index: int
    idempotency_key: Optional[str] = None
    error: str


class EventsIngestResult(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    errors: List[EventRejectInfo] = []


class EventOut(OutModel):
    id: UUID
    decision_id: UUID
    event_name: str
    ts: datetime
    created_at: datetime
    props: Optional[dict] = None


class Events(BaseModel):
    items: List[EventOut]
    total: int


# =========================
# Optional: Event Type Catalog (admin-managed)
# =========================

class RequiresExposureBool:
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            return value
        raise HTTPException(422, "requires_exposure must be boolean (true/false)")


class EventTypeKey(EventName):
    """
    Reuse EventName rules for event type key.
    """


class EventTypeCreate(BodyModel):
    __required_fields__ = {"key", "description"}

    key: EventTypeKey
    description: str
    requires_exposure: RequiresExposureBool = False


class EventTypeEdit(BodyModel):
    description: Optional[str] = None
    requires_exposure: Optional[RequiresExposureBool] = None
    is_active: Optional[bool] = None


class EventTypeOut(OutModel):
    id: UUID
    key: str
    description: str
    requires_exposure: bool
    created_at: datetime
    is_active: bool
