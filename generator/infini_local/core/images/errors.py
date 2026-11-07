"""Small adapter failure contract; image quality/PNG validation lives elsewhere."""
from __future__ import annotations


class ImageBackendError(RuntimeError):
    def __init__(self, message: str, *, category: str, retryable: bool) -> None:
        self.category = category
        self.retryable = retryable
        super().__init__(message[:2000])


class ImageBackendConfigurationError(ImageBackendError):
    """Selected adapter cannot run with the supplied configuration."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="configuration", retryable=False)
