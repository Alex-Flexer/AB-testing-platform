import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    experiment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id"),
        nullable=False,
        index=True,
    )
    variant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("variants.id"),
        nullable=False,
        index=True,
    )

    # subject_id / user_external_id as per your naming
    subject_id = Column(String(255), nullable=False, index=True)

    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment = relationship("Experiment")
    variant = relationship("Variant")

    __table_args__ = (
        # stickiness: one subject -> one variant per experiment
        UniqueConstraint("experiment_id", "subject_id", name="uq_decisions_experiment_subject"),
    )
