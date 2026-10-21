"""Typed error categories that adapters map onto their own protocols."""

from __future__ import annotations


class SlideLegibleError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier."""

    category = "internal"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category, "code": self.code, "message": self.message}


class InvalidInput(SlideLegibleError):
    category = "invalid_input"


class UnsupportedContent(SlideLegibleError):
    category = "unsupported_content"


class AnalysisFailure(SlideLegibleError):
    category = "analysis_failure"


class CorrectionConflict(SlideLegibleError):
    category = "correction_conflict"


class UnsafeModification(SlideLegibleError):
    category = "unsafe_modification"


class RenderingUnavailable(SlideLegibleError):
    category = "rendering_unavailable"


class RenderingFailure(SlideLegibleError):
    category = "rendering_failure"


class ResourceLimitExceeded(SlideLegibleError):
    category = "resource_limit_exceeded"


class ArtifactAccessFailure(SlideLegibleError):
    category = "artifact_access_failure"
