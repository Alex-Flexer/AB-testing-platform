import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.enums import FlagType
from db.base import Base


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(255), nullable=False, unique=True)
    description = Column(Text)

    type = Column(Enum(FlagType), nullable=False)
    default_value = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    experiments = relationship("Experiment", back_populates="feature_flag")
