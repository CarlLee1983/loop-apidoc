"""`referenced_names` at its own seam.

The circular-reference guarantee used to be asserted only through the CLI, as
`exit_code == 0`. Deleting the `seen` guard in
`loop_apidoc/extraction/field_names.py` does not make that assertion fail; it
makes the test hang, and a property that cannot fail in finite time is not being
proved (#127). These tests read the returned names instead, and carry a tight
timeout so the loop surfaces as a failure with a name attached — verified by
deleting the guard: three named failures in 10s, where the CLI test previously
hung the whole suite.
"""

from __future__ import annotations

import pytest

from loop_apidoc.extraction.field_names import referenced_names, schema_index


def _schema(name: str, *, fields: list[str], ref: str | None = None) -> dict:
    schema = {
        "name": name,
        "fields": [
            {"name": field, "type": "str", "required": False, "description": None}
            for field in fields
        ],
        "enums": [],
        "constraints": None,
        "source": "manual.md lines 2-3",
    }
    if ref is not None:
        schema["schema_ref"] = ref
    return schema


@pytest.mark.timeout(10)
def test_a_self_referential_schema_yields_its_own_names():
    schemas = schema_index(
        {"schemas": [_schema("Loop", fields=["self_ref"], ref="Loop")]}
    )

    names = referenced_names({"request": {"schema_ref": "Loop"}}, schemas)

    assert "self_ref" in names


@pytest.mark.timeout(10)
def test_a_two_schema_cycle_yields_both_sides_names():
    # A → B → A: the mutual cycle, distinct from the self-reference above.
    # (`- seen` in the pending update is a shortcut, not the guard — dropping it
    # alone still terminates; `seen` is what stops the walk.)
    schemas = schema_index(
        {
            "schemas": [
                _schema("A", fields=["a_field"], ref="B"),
                _schema("B", fields=["b_field"], ref="A"),
            ]
        }
    )

    names = referenced_names({"request": {"schema_ref": "A"}}, schemas)

    assert {"a_field", "b_field"} <= names


@pytest.mark.timeout(10)
def test_an_unresolvable_reference_is_skipped_not_guessed():
    schemas = schema_index({"schemas": [_schema("A", fields=["a_field"])]})

    names = referenced_names({"request": {"schema_ref": "Absent"}}, schemas)

    assert names == set()
