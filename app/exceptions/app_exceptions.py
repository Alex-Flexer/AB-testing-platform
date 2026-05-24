class AppException(Exception):
    status_code: int = 400
    detail: str = "application error"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail


class EmailAlreadyExists(AppException):
    status_code = 409
    detail = "user with this email already exists"


class UserNotFound(AppException):
    status_code = 404
    detail = "user not found"


class UnprocessableEntity(AppException):
    status_code = 422
    detail = "input data is not compatible with required"


class InvalidCredentials(AppException):
    status_code = 401
    detail = "invalid token"


class Forbidden(AppException):
    status_code = 403
    detail = "permission denied"


class FeatureFlagNotFound(AppException):
    status_code = 404
    detail = "feature flag not found"


class FeatureFlagKeyAlreadyExists(AppException):
    status_code = 409
    detail = "feature flag with this key already exists"


class ExperimentNotFound(AppException):
    status_code = 404
    detail = "experiment not found"


class ExperimentStateConflict(AppException):
    status_code = 409
    detail = "experiment status is not compatible with requested status update"


class EventTypeNotFound(AppException):
    status_code = 404
    detail = "event type not found"


class MetricNotFound(AppException):
    status_code = 404
    detail = "metric not found"


class MetricKeyAlreadyExists(AppException):
    status_code = 409
    detail = "metric with this key already exists"
