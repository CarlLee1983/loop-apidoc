from __future__ import annotations

import re


class DomainIdentityError(ValueError):
    """A source-derived value cannot form a legal canonical API identity."""


_METHODS = frozenset(
    {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)
_NAME_RE = re.compile(r"^[^\s:][^:]*$")


def canonical_operation_identity(method: str, path: str) -> str:
    normalized_method = method.strip().upper()
    normalized_path = path.strip()
    if normalized_method not in _METHODS:
        raise DomainIdentityError(f"unsupported HTTP method: {method!r}")
    if not normalized_path.startswith("/"):
        raise DomainIdentityError(f"operation path must start with '/': {path!r}")
    return f"operation:{normalized_method}:{normalized_path}"


def canonical_schema_identity(name: str) -> str:
    normalized = name.strip()
    if not normalized or not _NAME_RE.match(normalized):
        raise DomainIdentityError(f"invalid schema name: {name!r}")
    return f"schema:{normalized}"


def canonical_claim_identity(claim_kind: str, subject: str, predicate: str) -> str:
    parts = (claim_kind.strip(), subject.strip(), predicate.strip())
    if any(not part or ":" in part for part in parts):
        raise DomainIdentityError(
            "claim identity parts must be non-empty and colon-free"
        )
    return f"claim:{parts[0]}:{parts[1]}:{parts[2]}"
