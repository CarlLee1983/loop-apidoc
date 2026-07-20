"""Replaceable runtime and platform adapters for Core ports."""

from loop_apidoc.adapters.fragments import (
    FragmentRequest,
    acquire_fragment_bundle,
)
from loop_apidoc.adapters.runtime import CallableRuntimeAdapter

__all__ = [
    "CallableRuntimeAdapter",
    "FragmentRequest",
    "acquire_fragment_bundle",
]
