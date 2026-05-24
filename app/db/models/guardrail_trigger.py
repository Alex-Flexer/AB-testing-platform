import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base
from db.enums import ComparisonOperator, GuardrailAction


class GuardrailTrigger(Base):
    __tablename__ = "guardrail_triggers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    guardrail_id = Column(
        UUID(as_uuid=True),
        ForeignKey("guardrails.id", ondelete="CASCADE"),
        nullable=False,
    )

    # удобно для фильтрации/индекса и отчётов
    experiment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    metric_id = Column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="RESTRICT"),
        nullable=False,
    )

    comparison_operator = Column(Enum(ComparisonOperator), nullable=False)
    threshold = Column(Float, nullable=False)
    window_minutes = Column(Float, nullable=False)

    action = Column(Enum(GuardrailAction), nullable=False)

    actual_value = Column(Float, nullable=False)

    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    guardrail = relationship("Guardrail")
    metric = relationship("Metric")
    experiment = relationship("Experiment")

    __table_args__ = (
        Index("ix_guardrail_triggers_experiment_id", "experiment_id"),
        Index("ix_guardrail_triggers_triggered_at", "triggered_at"),
    )
