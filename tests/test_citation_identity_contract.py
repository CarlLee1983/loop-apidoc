from __future__ import annotations

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "loop_apidoc"

# Reading `UrlSource.fetch_url` is reading the credential. These are the places
# that legitimately need it, with the reason. Everywhere else names a source by
# `citation_id`, because everywhere else the value is written down or compared
# against something that was.
#
# The check is exact rather than heuristic, and that is the whole reason the
# field is not called `url`: `fetch_url` is a name nothing else in the package
# uses, so "every read of this attribute" is a boundary rather than a spot
# check. A missed read is an `AttributeError`, not a silent leak.
#
# The boundary is attribute access. `dict(source)`, iterating a model,
# `getattr(source, "fetch_url")` and `source.__dict__` all reach the raw value
# without an `ast.Attribute` node; none occurs in the package, and none would be
# caught here if it did.
ALLOWED = {
    "loop_apidoc/manifest/models.py": "defines `citation_id` as its redaction",
    "loop_apidoc/plan/classify.py": (
        "matches an agent- or operator-written locator against both spellings; "
        "returns citation_id"
    ),
}


def _fetch_url_reads(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "fetch_url"
    )


def test_a_url_source_is_named_by_its_citation_identity_not_its_fetch_url():
    """Issue #158. `RedactedUrl` protects this model's own serialization and
    nothing else: a raw fetch URL copied into a plain `str` field elsewhere
    carries the credential into `plan.json`, the validation report and the
    generated documents — and, where the value is a join key, silently stops
    matching the redacted side. Neither failure is visible in a diff.
    """
    offenders = {
        module.relative_to(REPO).as_posix(): _fetch_url_reads(module)
        for module in sorted(PACKAGE.rglob("*.py"))
    }
    unexplained = {
        module: lines
        for module, lines in offenders.items()
        if lines and module not in ALLOWED
    }

    assert not unexplained, (
        "read the raw fetch URL off a manifest URL source; use `citation_id` "
        "unless the credential is genuinely needed, then add the module to "
        f"ALLOWED with a reason: {unexplained}"
    )


def test_every_allowed_module_still_reads_the_fetch_url():
    """A stale entry is a hole nobody is watching."""
    for module in ALLOWED:
        assert _fetch_url_reads(REPO / module), (
            f"{module} no longer reads a raw fetch URL; drop it from ALLOWED"
        )


def test_the_raw_accessor_is_not_spelled_like_the_serialized_key():
    """The rename is the control. If `UrlSource` ever grows a `url` attribute
    again, every guard above degrades from a boundary to a spot check."""
    from loop_apidoc.manifest.models import UrlSource

    assert "fetch_url" in UrlSource.model_fields
    assert "url" not in UrlSource.model_fields
    assert UrlSource.model_fields["fetch_url"].alias == "url"


def test_the_serialized_key_is_still_url():
    """A byte check, not a config check. `serialize_by_alias` arrived in pydantic
    2.11 and an unknown config key is ignored silently, so on an older resolution
    this model would write `fetch_url` into every manifest.json and no reader
    would accept it. `pyproject.toml` pins the floor; this fails if it slips."""
    from datetime import datetime, timezone

    from loop_apidoc.manifest.models import UrlSource

    source = UrlSource(
        url="https://docs.example.com/spec",
        fetched_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        http_status=200,
    )

    assert source.model_dump_json().startswith('{"url":')
    assert source.model_dump(mode="json")["url"] == "https://docs.example.com/spec"
    assert UrlSource.model_validate({"url": "https://x.test/"}.__or__(
        {"fetched_at": "2026-08-30T00:00:00Z", "http_status": 200}
    )).fetch_url == "https://x.test/"
