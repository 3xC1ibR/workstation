"""Validate agent-defined questions and user-supplied response values."""
import math
import re


FIELD_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
FIELD_TYPES = {"text", "multiline", "number", "boolean", "choice"}


def validate_fields(fields):
    if not isinstance(fields, list) or len(fields) > 50:
        raise ValueError("response_fields must be a list of at most 50 fields")
    identifiers = set()
    for field in fields:
        if (not isinstance(field, dict) or not {"id", "label", "type"} <= field.keys()
                or field.keys() - {"id", "label", "type", "help", "required", "options"}):
            raise ValueError("Each response field requires id, label, type; optional: help, required, options")
        identifier = field["id"]
        if not isinstance(identifier, str) or not FIELD_ID.fullmatch(identifier) or identifier in identifiers:
            raise ValueError("Response field IDs must be unique lowercase identifiers of at most 64 characters")
        identifiers.add(identifier)
        if not isinstance(field["type"], str) or field["type"] not in FIELD_TYPES:
            raise ValueError(f"{identifier}: unsupported response field type")
        for key in ("label", "help"):
            if key in field and (not isinstance(field[key], str) or not field[key].strip() or len(field[key]) > 2000):
                raise ValueError(f"{identifier}.{key} must be nonempty text of at most 2000 characters")
        if "required" in field and type(field["required"]) is not bool:
            raise ValueError(f"{identifier}.required must be boolean")
        options = field.get("options")
        if field["type"] == "choice":
            if (not isinstance(options, list) or not 1 <= len(options) <= 100
                    or any(not isinstance(option, str) or not option.strip() or len(option) > 500 for option in options)
                    or len(set(options)) != len(options)):
                raise ValueError(f"{identifier}.options must contain 1–100 unique nonempty text choices")
        elif "options" in field:
            raise ValueError(f"{identifier}: options apply only to choice fields")


def validate_values(fields, values):
    validate_fields(fields)
    if not isinstance(values, dict) or values.keys() - {field["id"] for field in fields}:
        raise ValueError("Responses must be an object containing only this report's field IDs")
    result = {}
    for field in fields:
        identifier = field["id"]
        value = values.get(identifier)
        if value is None or (isinstance(value, str) and not value.strip()):
            if field.get("required"):
                raise ValueError(f"{field['label']}: a response is required")
            continue
        kind = field["type"]
        valid = ((kind in {"text", "multiline"} and isinstance(value, str) and len(value.encode("utf-8")) <= 20000)
                 or (kind == "number" and type(value) in {int, float} and abs(value) <= 9007199254740991
                     and math.isfinite(value))
                 or (kind == "boolean" and type(value) is bool)
                 or (kind == "choice" and isinstance(value, str) and value in field["options"]))
        if not valid:
            raise ValueError(f"{field['label']}: invalid {kind} response")
        result[identifier] = value
    return result
