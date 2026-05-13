"""Validation-step helper models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Typed repairable validation result."""

    ok: bool
    message: str | None = None
    title: str = "Validation Feedback"
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise TypeError("ok must be a bool")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")
        object.__setattr__(self, "title", self.title.strip())
        if self.message is not None:
            if not isinstance(self.message, str):
                raise TypeError("message must be a string when provided")
            normalized_message = self.message.strip()
            if not normalized_message:
                raise ValueError("message must be non-empty when provided")
            object.__setattr__(self, "message", normalized_message)
        if not self.ok and self.message is None:
            raise ValueError("invalid validation results require a message")
        normalized_details: list[str] = []
        for detail in self.details:
            if not isinstance(detail, str):
                raise TypeError("details entries must be strings")
            normalized = detail.strip()
            if not normalized:
                raise ValueError("details entries must be non-empty")
            normalized_details.append(normalized)
        object.__setattr__(self, "details", tuple(normalized_details))

    @classmethod
    def valid(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def invalid(
        cls,
        message: str,
        *,
        title: str = "Validation Feedback",
        details: Sequence[str] = (),
    ) -> "ValidationResult":
        return cls(ok=False, message=message, title=title, details=tuple(details))


def render_validation_feedback(result: ValidationResult) -> str:
    """Render the default markdown feedback artifact body."""

    if result.ok:
        raise ValueError("valid results do not render feedback")
    lines = [f"# {result.title}", "", result.message or ""]
    if result.details:
        lines.extend(("", "## Details"))
        lines.extend(f"- {detail}" for detail in result.details)
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["ValidationResult", "render_validation_feedback"]
