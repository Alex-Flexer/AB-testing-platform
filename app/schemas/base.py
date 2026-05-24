from pydantic import BaseModel, model_validator
from typing import ClassVar, Set, Any
from fastapi import HTTPException


class BodyModel(BaseModel):
    __required_fields__: ClassVar[Set[str]] = set()

    @model_validator(mode="before")
    @classmethod
    def _check_required_and_extra(cls, data: Any):
        if not isinstance(data, dict):
            raise HTTPException(422, "body must be a JSON object")

        missing = [f for f in cls.__required_fields__ if f not in data]
        if missing:
            raise HTTPException(422, f"missing required fields: {', '.join(sorted(missing))}")

        return data


class OutModel(BaseModel):
    class Config:
        from_attributes = True
