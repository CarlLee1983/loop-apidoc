"""OpenAPI JSON Pointer and fragment parsers used by claim verification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _openapi_operation_from_pointer(pointer: str) -> tuple[str, str] | None:
    """Return an OpenAPI operation path and method from a canonical pointer."""
    segments = pointer.split("/")
    if len(segments) != 4 or segments[0] or segments[1] != "paths":
        return None
    encoded_path, method = segments[2:]
    if method not in {
        "get",
        "put",
        "post",
        "delete",
        "options",
        "head",
        "patch",
        "trace",
    }:
        return None
    path = _decode_json_pointer_segment(encoded_path)
    if path is None or not path.startswith("/"):
        return None
    return path, method.upper()


def _openapi_response_status_from_pointer(pointer: str) -> str | None:
    """Return an OpenAPI response key only from a canonical response pointer."""
    segments = pointer.split("/")
    if len(segments) != 6 or segments[0] or segments[4] != "responses":
        return None
    if _openapi_operation_from_pointer("/".join(segments[:4])) is None:
        return None
    status = _decode_json_pointer_segment(segments[5])
    if status == "default":
        return status
    if (
        status is not None
        and len(status) == 3
        and status[0] in "12345"
        and (
            status[1:] == "XX"
            or all("0" <= character <= "9" for character in status[1:])
        )
    ):
        return status
    return None


def _openapi_response_schema_ref_from_pointer(
    pointer: str,
    source_ref: Any,
) -> tuple[str, str] | None:
    """Map one local response-schema ``$ref`` to its canonical claim path."""
    segments = pointer.split("/")
    if (
        len(segments) != 10
        or segments[0]
        or segments[4] != "responses"
        or segments[6] != "content"
        or segments[8] != "schema"
        or segments[9] != "$ref"
    ):
        return None
    status = _openapi_response_status_from_pointer("/".join(segments[:6]))
    media_type = _decode_json_pointer_segment(segments[7])
    schema_name = _local_openapi_schema_name(source_ref)
    if status is None or not media_type or schema_name is None:
        return None
    return f"/responses/{status}/schema_ref", schema_name


def _openapi_request_schema_ref_from_pointer(
    pointer: str,
    source_ref: Any,
) -> str | None:
    """Map one local request-body schema ``$ref`` to its canonical claim."""
    segments = pointer.split("/")
    if (
        len(segments) != 9
        or segments[0]
        or segments[4] != "requestBody"
        or segments[5] != "content"
        or segments[7] != "schema"
        or segments[8] != "$ref"
    ):
        return None
    if _openapi_operation_from_pointer("/".join(segments[:4])) is None:
        return None
    media_type = _decode_json_pointer_segment(segments[6])
    schema_name = _local_openapi_schema_name(source_ref)
    if not media_type or schema_name is None:
        return None
    return schema_name


def _openapi_request_body_property_from_pointer(
    pointer: str,
    operation_value: Any,
    source_property: Any,
) -> str | None:
    """Return a request-body field path for the operation's local schema.

    The pointer may descend through object ``properties`` and array ``items``.
    Array boundaries are represented with ``[]`` so the derived name remains the
    same structural name that the extraction contract uses (for example,
    ``data[].playerId``).  Any other JSON Pointer segment fails closed.
    """
    segments = pointer.split("/")
    if (
        len(segments) < 6
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
        or segments[4] != "properties"
    ):
        return None
    schema_name = _decode_json_pointer_segment(segments[3])
    property_name = _decode_json_pointer_segment(segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not schema_name
        or not property_name
        or operation_value.get("request_schema_ref") != schema_name
    ):
        return None

    field_name = property_name
    if isinstance(source_property, Mapping) and source_property.get("type") == "array":
        field_name = f"{field_name}[]"
    index = 6
    while index < len(segments):
        segment = segments[index]
        if segment == "items":
            field_name = f"{field_name}[]"
            index += 1
            continue
        if segment != "properties" or index + 1 >= len(segments):
            return None
        nested_name = _decode_json_pointer_segment(segments[index + 1])
        if not nested_name:
            return None
        field_name = f"{field_name}.{nested_name}"
        index += 2
    return field_name


def _openapi_request_body_property_required_from_schema_pointer(
    *,
    pointer: str,
    source_schema: Any,
    operation_value: Any,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive one direct body field's required flag from its request schema.

    The complete component schema is the evidence: it identifies the operation's
    declared request schema, exposes the direct property, and records the
    schema-level ``required`` array.  Nested paths and local ``$ref`` hops are
    intentionally outside this one-fragment derivation.
    """
    schema_name = _openapi_schema_name_from_pointer(pointer)
    if (
        schema_name is None
        or not isinstance(source_schema, Mapping)
        or not isinstance(operation_value, Mapping)
        or operation_value.get("request_schema_ref") != schema_name
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[:2] != ["parameters", "body"]
        or parts[3] != "required"
    ):
        return None
    field_name = _decode_json_pointer_segment(parts[2])
    if not field_name or "." in field_name:
        return None
    property_name = field_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if field_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_request_body_ref_property_from_fragments(
    *,
    property_pointer: str,
    ref_pointer: str,
    operation_value: Any,
    source_property: Any,
    source_ref: Any,
) -> str | None:
    """Map one array-item ``$ref`` and one child property to a body field.

    Both pointers are intentionally constrained to one local schema hop.  The
    operation identifies the root request schema, the context pointer proves
    its array item reference, and the primary pointer proves the child field.
    """
    property_segments = property_pointer.split("/")
    ref_segments = ref_pointer.split("/")
    if (
        len(property_segments) != 6
        or property_segments[0]
        or property_segments[1:3] != ["components", "schemas"]
        or property_segments[4] != "properties"
        or len(ref_segments) != 8
        or ref_segments[0]
        or ref_segments[1:3] != ["components", "schemas"]
        or ref_segments[4] != "properties"
        or ref_segments[6:] != ["items", "$ref"]
    ):
        return None
    item_schema = _decode_json_pointer_segment(property_segments[3])
    item_property = _decode_json_pointer_segment(property_segments[5])
    request_schema = _decode_json_pointer_segment(ref_segments[3])
    request_property = _decode_json_pointer_segment(ref_segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not item_schema
        or not item_property
        or not request_schema
        or not request_property
        or operation_value.get("request_schema_ref") != request_schema
        or _local_openapi_schema_name(source_ref) != item_schema
    ):
        return None
    suffix = "[]" if (
        isinstance(source_property, Mapping)
        and source_property.get("type") == "array"
    ) else ""
    return f"{request_property}[].{item_property}{suffix}"


def _openapi_request_body_ref_property_required_from_fragments(
    *,
    schema_pointer: str,
    ref_pointer: str,
    operation_value: Any,
    source_schema: Any,
    source_ref: Any,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a one-hop array item's required flag from linked fragments."""
    child_schema = _openapi_schema_name_from_pointer(schema_pointer)
    ref_segments = ref_pointer.split("/")
    if (
        child_schema is None
        or not isinstance(source_schema, Mapping)
        or len(ref_segments) != 8
        or ref_segments[0]
        or ref_segments[1:3] != ["components", "schemas"]
        or ref_segments[4] != "properties"
        or ref_segments[6:] != ["items", "$ref"]
    ):
        return None
    request_schema = _decode_json_pointer_segment(ref_segments[3])
    request_property = _decode_json_pointer_segment(ref_segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not request_schema
        or not request_property
        or operation_value.get("request_schema_ref") != request_schema
        or _local_openapi_schema_name(source_ref) != child_schema
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[:2] != ["parameters", "body"]
        or parts[3] != "required"
    ):
        return None
    field_name = _decode_json_pointer_segment(parts[2])
    if not field_name or field_name.count(".") != 1:
        return None
    outer_name, child_name = field_name.split(".", 1)
    if not outer_name.endswith("[]") or outer_name.removesuffix("[]") != request_property:
        return None
    property_name = child_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if child_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_schema_ref_property_from_fragments(
    *,
    property_pointer: str,
    ref_pointer: str,
    source_property: Any,
    source_ref: Any,
    claim_identity: str,
) -> tuple[str, str | None] | None:
    """Map one local component ``$ref`` to a nested schema field.

    The primary fragment must be the complete property object in the referenced
    component.  The context fragment must be the root schema's direct property
    or array item's local ``$ref``.  No ref is followed implicitly: both source
    values are supplied as exact fragments and re-checked here.
    """
    property_parts = property_pointer.split("/")
    ref_parts = ref_pointer.split("/")
    if (
        len(property_parts) != 6
        or property_parts[0]
        or property_parts[1:3] != ["components", "schemas"]
        or property_parts[4] != "properties"
        or not isinstance(source_property, Mapping)
    ):
        return None
    item_schema = _decode_json_pointer_segment(property_parts[3])
    item_property = _decode_json_pointer_segment(property_parts[5])
    if not item_schema or not item_property:
        return None

    is_array_item = (
        len(ref_parts) == 8
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6:] == ["items", "$ref"]
    )
    is_direct_property = (
        len(ref_parts) == 7
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6] == "$ref"
    )
    if not (is_array_item or is_direct_property):
        return None
    root_schema = _decode_json_pointer_segment(ref_parts[3])
    root_property = _decode_json_pointer_segment(ref_parts[5])
    if (
        not root_schema
        or not root_property
        or _schema_name_from_claim_identity(claim_identity) != root_schema
        or _local_openapi_schema_name(source_ref) != item_schema
    ):
        return None
    source_type = source_property.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    prefix = f"{root_property}[]" if is_array_item else root_property
    suffix = "[]" if source_type == "array" else ""
    return f"{prefix}.{item_property}{suffix}", source_type


def _openapi_schema_ref_property_required_from_fragments(
    *,
    schema_pointer: str,
    ref_pointer: str,
    source_schema: Any,
    source_ref: Any,
    claim_identity: str,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a one-hop referenced schema field's required flag."""
    child_schema = _openapi_schema_name_from_pointer(schema_pointer)
    ref_parts = ref_pointer.split("/")
    is_array_item = (
        len(ref_parts) == 8
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6:] == ["items", "$ref"]
    )
    is_direct_property = (
        len(ref_parts) == 7
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6] == "$ref"
    )
    if (
        child_schema is None
        or not isinstance(source_schema, Mapping)
        or not (is_array_item or is_direct_property)
    ):
        return None
    root_schema = _decode_json_pointer_segment(ref_parts[3])
    root_property = _decode_json_pointer_segment(ref_parts[5])
    if (
        not root_schema
        or not root_property
        or _schema_name_from_claim_identity(claim_identity) != root_schema
        or _local_openapi_schema_name(source_ref) != child_schema
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] != "required":
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    if not field_name or field_name.count(".") != 1:
        return None
    prefix, child_name = field_name.split(".", 1)
    expected_prefix = f"{root_property}[]" if is_array_item else root_property
    if prefix != expected_prefix:
        return None
    property_name = child_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if child_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_schema_two_hop_ref_property_from_fragments(
    *,
    primary_pointer: str, primary_value: Any,
    first_ref_pointer: str, first_ref: Any,
    second_ref_pointer: str, second_ref: Any,
    claim_identity: str, claim_path: str, required: bool,
) -> tuple[str, Any] | None:
    """Verify exactly two ordered ``items.$ref`` hops for a schema field."""
    def ref_parts(pointer: str) -> tuple[str, str] | None:
        parts = pointer.split("/")
        if not (len(parts) == 8 and not parts[0] and parts[1:3] == ["components", "schemas"] and parts[4] == "properties" and parts[6:] == ["items", "$ref"]):
            return None
        parent = _decode_json_pointer_segment(parts[3])
        prop = _decode_json_pointer_segment(parts[5])
        return (parent, prop) if parent and prop else None
    first = ref_parts(first_ref_pointer)
    second = ref_parts(second_ref_pointer)
    if first is None or second is None or _schema_name_from_claim_identity(claim_identity) != first[0] or _local_openapi_schema_name(first_ref) != second[0]:
        return None
    child_schema = _local_openapi_schema_name(second_ref)
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] not in {"name", "type", "required"}:
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    prefix = f"{first[1]}[].{second[1]}[]"
    if not field_name or not field_name.startswith(f"{prefix}."):
        return None
    property_name = field_name.removeprefix(f"{prefix}.").removesuffix("[]")
    if required:
        if _openapi_schema_name_from_pointer(primary_pointer) != child_schema or not isinstance(primary_value, Mapping):
            return None
        properties = primary_value.get("properties")
        source_property = (
            properties.get(property_name) if isinstance(properties, Mapping) else None
        )
        required_names = primary_value.get("required", ())
        if not isinstance(source_property, Mapping) or not isinstance(required_names, (list, tuple)) or not all(isinstance(name, str) for name in required_names):
            return None
        if field_name.endswith("[]") != (source_property.get("type") == "array"):
            return None
        return claim_path, property_name in required_names
    pointer_parts = primary_pointer.split("/")
    if not (len(pointer_parts) == 6 and not pointer_parts[0] and pointer_parts[1:3] == ["components", "schemas"] and pointer_parts[4] == "properties" and _decode_json_pointer_segment(pointer_parts[3]) == child_schema and isinstance(primary_value, Mapping)):
        return None
    if _decode_json_pointer_segment(pointer_parts[5]) != property_name:
        return None
    source_type = primary_value.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    expected_field = f"{prefix}.{property_name}{'[]' if source_type == 'array' else ''}"
    if field_name != expected_field:
        return None
    return claim_path, (field_name if parts[2] == "name" else source_type)


def _openapi_schema_name_from_pointer(pointer: str) -> str | None:
    """Return the name of one direct ``components.schemas`` member."""
    segments = pointer.split("/")
    if (
        len(segments) != 4
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
    ):
        return None
    return _decode_json_pointer_segment(segments[3])


def _schema_name_from_claim_identity(claim_identity: str) -> str | None:
    prefix = "claim:schema:"
    suffix = ":definition"
    if not claim_identity.startswith(prefix) or not claim_identity.endswith(suffix):
        return None
    name = claim_identity[len(prefix) : -len(suffix)]
    return name or None


def _openapi_schema_property_from_pointer(
    pointer: str,
    source_property: Any,
) -> tuple[str, str, str | None] | None:
    """Return one inline schema property and its source-stated type.

    The source pointer must select the complete property object.  Every inline
    ``items`` segment contributes an array marker; no ``$ref`` is followed.
    This keeps the structural relationship reproducible from the exact pointer
    and prevents a property from an unrelated component schema being attached
    to the claim.
    """
    segments = pointer.split("/")
    if (
        len(segments) < 6
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
        or segments[4] != "properties"
        or not isinstance(source_property, Mapping)
    ):
        return None
    schema_name = _decode_json_pointer_segment(segments[3])
    property_name = _decode_json_pointer_segment(segments[5])
    if not schema_name or not property_name:
        return None
    source_type = source_property.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    field_name = property_name
    index = 6
    while index < len(segments):
        segment = segments[index]
        if segment == "items":
            field_name = f"{field_name}[]"
            index += 1
            continue
        if segment != "properties" or index + 1 >= len(segments):
            return None
        nested_name = _decode_json_pointer_segment(segments[index + 1])
        if not nested_name:
            return None
        field_name = f"{field_name}.{nested_name}"
        index += 2
    if source_type == "array":
        field_name = f"{field_name}[]"
    return schema_name, field_name, source_type


def _openapi_schema_property_required_from_pointer(
    *,
    pointer: str,
    source_schema: Any,
    claim_identity: str,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a direct field's required flag from one complete schema object."""
    schema_name = _openapi_schema_name_from_pointer(pointer)
    if (
        schema_name is None
        or _schema_name_from_claim_identity(claim_identity) != schema_name
        or not isinstance(source_schema, Mapping)
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] != "required":
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    if not field_name:
        return None
    property_name = field_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = (
        properties.get(property_name) if isinstance(properties, Mapping) else None
    )
    if not isinstance(source_property, Mapping):
        return None
    if field_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _local_openapi_schema_name(source_ref: Any) -> str | None:
    prefix = "#/components/schemas/"
    if not isinstance(source_ref, str) or not source_ref.startswith(prefix):
        return None
    encoded_name = source_ref.removeprefix(prefix)
    if not encoded_name or "/" in encoded_name:
        return None
    return _decode_json_pointer_segment(encoded_name)


def _decode_json_pointer_segment(value: str) -> str | None:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
            return None
        decoded.append("~" if value[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)
