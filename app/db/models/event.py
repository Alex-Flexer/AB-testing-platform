import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Text,
    Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base


class EventType(Base):
    __tablename__ = "event_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    key = Column(String(128), nullable=False, unique=True)

    description = Column(Text, nullable=False)

    requires_exposure = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("key", name="uq_event_type_key"),
    )


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("decisions.id"),
        nullable=False,
        index=True,
    )

    experiment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    variant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("variants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    subject_id = Column(String(255), nullable=False, index=True)

    event_name = Column(String(128), nullable=False, index=True)

    idempotency_key = Column(String(255), nullable=False, unique=True)

    occurred_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    props = Column(JSON)

    decision = relationship("Decision")
    experiment = relationship("Experiment")
    variant = relationship("Variant")

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_events_idempotency_key"),
    )
