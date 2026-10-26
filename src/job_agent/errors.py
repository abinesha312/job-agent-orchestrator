"""Typed errors. Callers can tell a bad file from a dead job board."""


class ApplyPilotError(Exception):
    pass


class NotFound(ApplyPilotError):
    pass


class HttpFailure(ApplyPilotError):
    def __init__(self, message: str, *, url: str | None = None, status: int | None = None,
                 retryable: bool = True) -> None:
        super().__init__(message)
        self.url = url
        self.status = status
        self.retryable = retryable


class LlmFailure(ApplyPilotError):
    pass


class StorageFailure(ApplyPilotError):
    pass


class EvalBlocked(ApplyPilotError):
    def __init__(self, message: str, report: dict | None = None) -> None:
        super().__init__(message)
        self.report = report or {}
