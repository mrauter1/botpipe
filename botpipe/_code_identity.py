"""Canonical executable code evidence, independent of source paths and line numbers."""

from __future__ import annotations

import json
from types import CodeType
from typing import Any


def code_identity(code: CodeType) -> dict[str, Any]:
    """Describe executable instructions, calling convention, and compiler constants."""

    return {
        "name": code.co_name,
        "qualname": code.co_qualname,
        "bytes": code.co_code.hex(),
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "exceptions": code.co_exceptiontable.hex(),
        "constants": [_constant(value) for value in code.co_consts],
    }


def _constant(value: Any) -> Any:
    if isinstance(value, CodeType):
        return {"code": code_identity(value)}
    if value is None or type(value) in (str, int, bool):
        return value
    if value is Ellipsis:
        return {"ellipsis": True}
    if type(value) is float:
        # Hex preserves signed zero and represents nonfinite compiler literals
        # without putting non-JSON numbers into the fingerprint.
        return {"float": value.hex()}
    if type(value) is complex:
        return {"complex": [value.real.hex(), value.imag.hex()]}
    if type(value) is bytes:
        return {"bytes": value.hex()}
    if type(value) is tuple:
        return {"tuple": [_constant(item) for item in value]}
    if type(value) is frozenset:
        items = [_constant(item) for item in value]
        items.sort(
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
        )
        return {"frozenset": items}
    raise TypeError(
        "Unsupported executable code constant: "
        f"{type(value).__module__}:{type(value).__qualname__}"
    )
