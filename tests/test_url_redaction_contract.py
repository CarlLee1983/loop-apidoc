from __future__ import annotations

import importlib
import pkgutil
import typing

import pytest
from pydantic import BaseModel
from pydantic.functional_serializers import PlainSerializer

import loop_apidoc
from loop_apidoc.url_safety import redact_url


# The one model whose URL fields are deliberately NOT redacted, with the reason
# it is an exception rather than an oversight. `catalog.json` is written by
# `catalog-url` and read back by `cache-url-pages`, which then *fetches* every
# URL in it: for that file a URL is an instruction, not evidence, and a redacted
# instruction cannot be carried out. See docs/adr/0015.
#
# An allowlist rather than a list of covered models: the covered form would stay
# silent about a new model, and silence is the failure mode this guards.
EXEMPT_FIELDS = {
    "CatalogNode.url": "a fetch instruction, not evidence — ADR 0015",
    "CatalogNode.parent_url": "a fetch instruction, not evidence — ADR 0015",
    "UrlCatalog.entry_url": "a fetch instruction, not evidence — ADR 0015",
    "UrlSelection.entry_url": "a fetch instruction, not evidence — ADR 0015",
}


def _import_every_module() -> None:
    """`__subclasses__` only knows about classes that have been imported."""
    for module in pkgutil.walk_packages(loop_apidoc.__path__, "loop_apidoc."):
        try:
            importlib.import_module(module.name)
        except ImportError:  # pragma: no cover - an optional extra
            continue


def _models() -> list[type[BaseModel]]:
    _import_every_module()
    seen: dict[str, type[BaseModel]] = {}

    def walk(cls: type[BaseModel]) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__module__.startswith("loop_apidoc"):
                seen[f"{subclass.__module__}.{subclass.__qualname__}"] = subclass
            walk(subclass)

    walk(BaseModel)
    return list(seen.values())


def _serializes(items: object) -> bool:
    return any(
        isinstance(item, PlainSerializer) and item.func is redact_url
        for item in items  # type: ignore[union-attr]
    )


def _redacts(annotation: object) -> bool:
    """True if `redact_url` runs somewhere in this annotation — directly, or
    inside a `list[...]` / `... | None` wrapper."""
    if _serializes(getattr(annotation, "__metadata__", ())):
        return True
    return any(_redacts(argument) for argument in typing.get_args(annotation))


def _field_redacts(field: object) -> bool:
    # Pydantic lifts the outermost `Annotated` metadata onto the FieldInfo, so a
    # bare `url: RedactedUrl` has a plain `str` annotation; a nested one
    # (`list[RedactedUrl]`) keeps it on the annotation instead.
    return _serializes(getattr(field, "metadata", ())) or _redacts(field.annotation)


def _is_url_field(name: str) -> bool:
    return (
        name == "url"
        or name.endswith("_url")
        or name in {"internal_links", "discovered_from"}
    )


def _unprotected() -> dict[str, str]:
    found = {}
    for model in _models():
        for name, field in model.model_fields.items():
            if not _is_url_field(name) or _field_redacts(field):
                continue
            found[f"{model.__name__}.{name}"] = f"{model.__module__}: {field.annotation}"
    return found


def test_every_url_model_field_in_the_package_redacts_when_serialized():
    """Issue #156. The redaction seam is the annotated type, so a URL field
    typed `str` reintroduces the leak silently.

    This walks live `BaseModel` subclasses rather than parsing source: a model
    that inherits from a mixin is invisible to an AST scan keyed on a literal
    `BaseModel` base, and `EnvironmentEntry(_Cited).base_url` was exactly that
    miss. Walking the annotation also covers `list[RedactedUrl]` and any future
    alias for free.
    """
    unprotected = {
        field: where
        for field, where in _unprotected().items()
        if field not in EXEMPT_FIELDS
    }

    assert not unprotected, (
        "URL model fields must be annotated RedactedUrl, or listed in "
        f"EXEMPT_FIELDS with a reason: {unprotected}"
    )


@pytest.mark.parametrize("field", sorted(EXEMPT_FIELDS))
def test_an_exempt_field_still_exists_and_is_still_unredacted(field: str):
    """A stale exemption is a hole nobody is watching: once the field is gone or
    protected, the entry must go rather than stand ready to excuse a future
    field of the same name."""
    assert field in _unprotected(), (
        f"{field} is no longer an unredacted URL field; drop it from EXEMPT_FIELDS"
    )
