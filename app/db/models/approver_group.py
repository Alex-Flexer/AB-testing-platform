import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base


class ApproverGroupMember(Base):
    __tablename__ = "approver_group_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approver_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    approver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    group = relationship("ApproverGroup", back_populates="members")
    approver = relationship("User", foreign_keys=[approver_id])

    __table_args__ = (
        UniqueConstraint("group_id", "approver_id", name="uq_approver_group_member"),
    )


class ApproverGroup(Base):
    __tablename__ = "approver_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # владелец группы — experimenter (один experimenter -> одна группа)
    experimenter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    min_approvals = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experimenter = relationship("User", foreign_keys=[experimenter_id])

    members = relationship(
        "ApproverGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
