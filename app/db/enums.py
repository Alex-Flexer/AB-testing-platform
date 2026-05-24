import enum


class ExperimentStatus(enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ReviewStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserRole(enum.Enum):
    ADMIN = "admin"
    EXPERIMENTER = "experimenter"
    APPROVER = "approver"
    VIEWER = "viewer"


class FlagType(str, enum.Enum):
    STRING = "string"
    NUMBER = "number"
    BOOL = "bool"


class ReviewDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class AggregationType(str, enum.Enum):
    COUNT = "count"
    UNIQUE_COUNT = "unique_count"
    RATE = "rate"
    AVG = "avg"
    P95 = "p95"


class TimeGranularity(str, enum.Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class GuardrailAction(str, enum.Enum):
    PAUSE = "pause"
    ROLLBACK_TO_CONTROL = "rollback_to_control"


class ComparisonOperator(str, enum.Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="


class MetricRole(str, enum.Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GUARDRAIL = "guardrail"
