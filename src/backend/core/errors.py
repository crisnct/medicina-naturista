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


class LocalModelBusy(Exception):
    """The memory a local model needs is held by a model in use (a running report, vllm-embed,
    vllm-translate); the chat waits and asks again."""


class ModelLoadRequired(Exception):
    """A local model must be loaded before this step, and the caller asked to load it itself
    (the chat says why the message waits); nothing was changed."""
