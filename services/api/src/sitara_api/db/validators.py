"""`$jsonSchema` validators built from the §6.4 registry.

Two design choices worth stating, because both are load-bearing:

**Encrypted fields accept `binData` as well as their plaintext type.** Explicit
CSFLE stores a subtype-6 binary where a string used to be. One validator has to
hold in both modes, or every test would need a second schema and dev-without-a-
key-file would reject its own writes.

**`forbidden` fields are rejected outright.** §13/§33.1 say live-call audio is
never stored. A comment cannot enforce that; a validator can, and it keeps
holding after everyone who read the comment has moved on.

`validationLevel` is `moderate`: inserts and updates to conforming documents are
checked, but a pre-existing document that predates a field addition is not
retroactively rejected — which is exactly what the expand phase of an
expand→migrate→contract migration needs.
"""

from __future__ import annotations

from typing import Any

from sitara_api.db.registry import CollectionSpec


def _bson_type(declared: Any, *, encrypted: bool, optional: bool) -> list[str]:
    types = [declared] if isinstance(declared, str) else list(declared)
    if encrypted and "binData" not in types:
        types.append("binData")
    # An optional field may hold null. Writers routinely set an explicit null
    # for "not provided" rather than omitting the key — a phone-only signup
    # stores `email: None` — and a schema that rejects that is rejecting the
    # absence of data, which §6.4 never asks for. Required fields stay strict.
    if optional and "null" not in types:
        types.append("null")
    return types


def build_validator(spec: CollectionSpec) -> dict[str, Any]:
    """Return the `validator` document for one collection."""
    properties: dict[str, dict[str, Any]] = {}
    encrypted = spec.encrypted_paths
    required = set(spec.all_required)
    for name, declared in spec.all_fields.items():
        properties[name] = {
            "bsonType": _bson_type(
                declared, encrypted=name in encrypted, optional=name not in required
            )
        }

    schema: dict[str, Any] = {
        "bsonType": "object",
        "title": f"{spec.name} ({spec.spec_ref})",
        "required": list(spec.all_required),
        "properties": properties,
    }

    validator: dict[str, Any] = {"$jsonSchema": schema}
    if spec.forbidden:
        # $nor over $exists rather than a schema clause: it reads as the rule it
        # is ("none of these may be present") and survives field additions.
        validator = {
            "$and": [
                validator,
                {"$nor": [{name: {"$exists": True}} for name in spec.forbidden]},
            ]
        }
    return validator


def validator_options(spec: CollectionSpec) -> dict[str, Any]:
    return {
        "validator": build_validator(spec),
        "validationLevel": "moderate",
        "validationAction": "error",
    }
