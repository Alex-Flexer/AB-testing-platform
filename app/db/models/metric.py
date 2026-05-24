import uuid

from sqlalchemy import (
    Column,
    String,
    Boolean,
    ForeignKey,
    Text,
    DateTime,
    Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from db.base import Base
from db.enums import AggregationType

from datetime import datetime


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    key = Column(String(128), nullable=False, unique=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)

    aggregation_type = Column(Enum(AggregationType), nullable=False)

    numerator_event = Column(String(128), nullable=True)
    denominator_event = Column(String(128), nullable=True)

    field_path = Column(String(256), nullable=True)

    requires_exposure = Column(Boolean, default=False, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment_links = relationship(
        "ExperimentMetric",
        back_populates="metric",
        cascade="all, delete-orphan",
    )
