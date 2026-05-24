import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Float,
    Text,
    Enum,
    Integer,
    UniqueConstraint,
    JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.enums import ExperimentStatus, ReviewStatus

from db.base import Base


class ExperimentMetric(Base):
    __tablename__ = "experiment_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    experiment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False
    )

    metric_id = Column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False
    )

    # роль метрики в эксперименте: primary / secondary / guardrail
    role = Column(String(32), nullable=False, default="secondary")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment = relationship("Experiment", back_populates="metric_links")
    metric = relationship("Metric", back_populates="experiment_links")

    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "metric_id",
            name="uq_experiment_metrics_experiment_metric"
        ),
    )


class ExperimentVersion(Base):
    __tablename__ = "experiment_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    experiment_id = Column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)

    version = Column(Integer, nullable=False)  # 1,2,3...
    config = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    experiment = relationship("Experiment", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("experiment_id", "version", name="uq_experiment_version"),
    )


class ExperimentReview(Base):
    __tablename__ = "experiment_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    experiment_id = Column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    status = Column(Enum(ReviewStatus), default=ReviewStatus.PENDING)
    comment = Column(Text)

    reviewed_at = Column(DateTime)

    experiment = relationship("Experiment", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("experiment_id", "reviewer_id"),
    )


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    description = Column(Text)

    status = Column(Enum(ExperimentStatus), default=ExperimentStatus.DRAFT)

    traffic_percentage = Column(Float, nullable=False)

    start_at = Column(DateTime)
    end_at = Column(DateTime)

    feature_flag_id = Column(UUID(as_uuid=True), ForeignKey("feature_flags.id"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    feature_flag = relationship("FeatureFlag", back_populates="experiments")
    owner = relationship("User", back_populates="experiments")

    versions = relationship(
        "ExperimentVersion",
        back_populates="experiment",
        cascade="all, delete-orphan"
    )

    targeting_rule = Column(Text, nullable=True)

    current_version = Column(Integer, nullable=False, default=1)

    metric_links = relationship(
        "ExperimentMetric", back_populates="experiment", cascade="all, delete-orphan")

    guardrails = relationship(
        "Guardrail",
        back_populates="experiment",
        cascade="all, delete-orphan"
    )

    reviews = relationship(
        "ExperimentReview",
        back_populates="experiment",
        cascade="all, delete-orphan"
    )

    variants = relationship(
        "Variant",
        back_populates="experiment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
