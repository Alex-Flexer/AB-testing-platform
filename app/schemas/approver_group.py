from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_core import core_schema

from schemas.base import BodyModel, OutModel
from db.enums import UserRole


# =========================
#      Custom Types
# =========================

class MinApprovals(int):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if isinstance(value, bool):
            raise HTTPException(422, "min_approvals must be integer")
        try:
            v = int(value)
        except (ValueError, TypeError):
            raise HTTPException(422, "min_approvals must be integer")

        if v <= 0:
            raise HTTPException(422, "min_approvals must be greater than 0")

        if v > 50:
            raise HTTPException(422, "min_approvals is too large (max 50)")

        return v


class UserIds:
    """
    Validate list[UUID] with custom errors.
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, value):
        if not isinstance(value, list):
            raise HTTPException(422, "approver_ids must be a list")

        if len(value) == 0:
            raise HTTPException(422, "approver_ids must not be empty")

        if len(value) > 200:
            raise HTTPException(422, "approver_ids list is too large (max 200)")

        out: List[UUID] = []
        for i, item in enumerate(value):
            try:
                out.append(UUID(str(item)))
            except Exception:
                raise HTTPException(422, f"approver_ids[{i}] must be UUID")
        return out


# =========================
#        Schemas
# =========================

class ApproverGroupCreate(BodyModel):
    """
    Create or replace approver group for an experimenter.
    """
    __required_fields__ = {"experimenter_id", "min_approvals", "approver_ids"}

    experimenter_id: UUID
    min_approvals: MinApprovals
    approver_ids: UserIds

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        # min_approvals cannot exceed number of approvers
        if data.min_approvals > len(data.approver_ids):
            raise HTTPException(422, "min_approvals cannot be greater than number of approvers")
        return data


class ApproverGroupUpdate(BodyModel):
    min_approvals: Optional[MinApprovals] = None
    approver_ids: Optional[UserIds] = None

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        return core_schema.no_info_after_validator_function(cls._validate_cross_fields, schema)

    @classmethod
    def _validate_cross_fields(cls, data):
        if data.min_approvals is not None and data.approver_ids is not None:
            if data.min_approvals > len(data.approver_ids):
                raise HTTPException(422, "min_approvals cannot be greater than number of approvers")
        return data


class ApproverInfo(BaseModel):
    id: UUID
    email: str
    role: UserRole


class ApproverGroupMemberOut(OutModel):
    id: UUID
    approver_id: UUID
    added_at: datetime
    approver: ApproverInfo


class ApproverGroupOut(OutModel):
    id: UUID
    experimenter_id: UUID
    min_approvals: int
    created_at: datetime
    members: List[ApproverGroupMemberOut]


class ApproverGroups(BaseModel):
    items: List[ApproverGroupOut]
    total: int
