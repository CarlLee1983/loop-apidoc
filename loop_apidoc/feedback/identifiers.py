from __future__ import annotations

from loop_apidoc.feedback.errors import FeedbackInputError


def require_safe_identifier(value: str, label: str) -> None:
    """Reject values that cannot be used as one governed path segment."""
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FeedbackInputError(f"unsafe {label}")
