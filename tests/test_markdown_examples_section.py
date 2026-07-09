from datetime import datetime, timezone

from loop_apidoc.generate.markdown import build_markdown
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan, PlanItemStatus


def _manifest() -> Manifest:
    return Manifest(sources_root=".", generated_at=datetime(2026, 7, 9, tzinfo=timezone.utc))


def _plan(*endpoints: EndpointEntry) -> NormalizationPlan:
    return NormalizationPlan(notebook_url="x", endpoints=list(endpoints))


def _endpoint(method: str, path: str, examples: list[dict]) -> EndpointEntry:
    return EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method=method, path=path, examples=examples
    )


def test_dict_example_renders_as_json_not_python_repr():
    """A dict body must serialize as JSON — `str(dict)` leaks Python repr
    (single quotes, True/None) that no JSON tool can consume."""
    plan = _plan(
        _endpoint(
            "POST",
            "/hrxt/getBalance",
            [{"value": {"code": 1000, "ok": True, "data": None, "msg": "成功"}}],
        )
    )
    md = build_markdown(plan, _manifest())

    assert '"code": 1000' in md
    assert '"ok": true' in md
    assert '"data": null' in md
    assert "'code'" not in md
    assert "True" not in md
    assert "成功" in md  # CJK stays unescaped
    assert "```json" in md


def test_example_title_identifies_its_endpoint():
    """Sources routinely give every endpoint the same example title; the
    rendered block must still say which endpoint it belongs to."""
    plan = _plan(
        _endpoint("POST", "/hrxt/getBalance", [{"title": "Response success", "value": {"a": 1}}]),
        _endpoint("POST", "/hrxt/credit", [{"title": "Response success", "value": {"a": 1}}]),
    )
    md = build_markdown(plan, _manifest())

    assert "POST /hrxt/getBalance — Response success" in md
    assert "POST /hrxt/credit — Response success" in md


def test_untitled_example_falls_back_to_endpoint_identity():
    plan = _plan(_endpoint("POST", "/hrxt/getBalance", [{"value": {"a": 1}}]))
    md = build_markdown(plan, _manifest())

    assert "**POST /hrxt/getBalance**" in md


def test_string_example_kept_verbatim_with_plain_fence():
    plan = _plan(_endpoint("POST", "/hrxt/getBalance", [{"value": "code=1000&msg=OK"}]))
    md = build_markdown(plan, _manifest())

    assert "code=1000&msg=OK" in md
    assert "```json" not in md


def test_body_key_still_supported():
    plan = _plan(_endpoint("POST", "/hrxt/getBalance", [{"body": {"a": 1}}]))
    md = build_markdown(plan, _manifest())

    assert '"a": 1' in md
