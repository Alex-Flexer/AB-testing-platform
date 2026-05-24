import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Boolean,
    ForeignKey,
    Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base
from db.enums import ComparisonOperator, GuardrailAction


class Guardrail(Base):
    __tablename__ = "guardrails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    experiment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False
    )

    metric_id = Column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="RESTRICT"),
        nullable=False
    )

    comparison_operator = Column(Enum(ComparisonOperator), nullable=False)  # >, >=, <, <=
    threshold = Column(Float, nullable=False)

    window_minutes = Column(Float, nullable=False)

    action = Column(Enum(GuardrailAction), nullable=False, default=GuardrailAction.PAUSE)

    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment = relationship("Experiment", back_populates="guardrails")
    metric = relationship("Metric")

    @property
    def metric_key(self) -> str:
        return self.metric.key
