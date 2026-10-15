"""Stable, non-sensitive application failures translated at the HTTP boundary."""


class ApplicationError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 409, *, retry_after: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


class OperationCancelled(Exception):
    """A closed, superseded or timed-out operation must discard its result."""
