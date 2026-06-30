"""Standardized output generation layer (spec §8)."""

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.generate.models import (
    GenerateResult,
    ProvenanceDocument,
    ProvenanceEntry,
)
from loop_apidoc.generate.review import build_review_html
from loop_apidoc.generate.writer import build_result, generate_outputs

__all__ = [
    "REQUIRED_MARKDOWN_SECTIONS",
    "GenerateResult",
    "ProvenanceDocument",
    "ProvenanceEntry",
    "build_review_html",
    "build_result",
    "generate_outputs",
]
