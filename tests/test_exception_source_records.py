"""Enum and exception storage contracts are structural and source-free."""

from __future__ import annotations

import os
import subprocess
import sys
from enum import Enum, Flag, IntFlag
from pathlib import Path

import pytest

from botpipe import codec


def _run(script: Path, *args: str, input: str | None = None):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
        ),
    }
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=script.parent,
        env=env,
        input=input,
        capture_output=True,
        text=True,
        check=False,
    )


class Choice(Enum):
    ONE = 1


class Permission(Flag):
    READ = 1
    WRITE = 2


class IntPermission(IntFlag):
    READ = 1
    WRITE = 2


class BaseFailure(Exception):
    __slots__ = ("code",)


class Failure(BaseFailure):
    init_calls = 0

    def __init__(self, code):
        type(self).init_calls += 1
        self.code = code
        super().__init__("failed")


def test_enum_contract_records_members_values_and_restores_without_lookup_hooks():
    encoded = codec.encode(Choice.ONE)

    assert encoded["contract"] == {
        "kind": "enum",
        "type": codec.type_name(Choice),
        "member_type": codec.type_name(object),
        "flag": False,
        "members": [["ONE", 1]],
    }
    assert codec.decode(encoded) is Choice.ONE

    encoded["contract"]["members"][0][1] = True
    with pytest.raises(TypeError, match="storage contract"):
        codec.verify_contracts(encoded)


@pytest.mark.parametrize("cls", [Permission, IntPermission])
def test_standard_flag_composites_restore_without_application_constructors(cls):
    value = cls.READ | cls.WRITE
    encoded = codec.encode(value)
    cls._value2member_map_.pop(3, None)

    restored = codec.decode(encoded)

    assert type(restored) is cls
    assert restored.value == 3
    assert encoded["member"] == "READ|WRITE"


@pytest.mark.parametrize(
    "value",
    [Permission(0), IntPermission(0), IntPermission(4), IntPermission.READ | 4],
)
def test_standard_flag_pseudo_members_round_trip_without_missing_hook(value):
    encoded = codec.encode(value)
    type(value)._value2member_map_.pop(value.value, None)

    restored = codec.decode(encoded)

    assert type(restored) is type(value)
    assert restored.value == value.value
    assert restored.name == value.name


def test_exception_type_contract_covers_native_family_and_inherited_slots():
    encoded = codec.encode(Failure)
    contract = encoded["contract"]

    assert contract["kind"] == "exception"
    assert contract["native_family"] == codec.type_name(Exception)
    assert [codec.type_name(BaseFailure), "code"] in contract["slots"]
    before = Failure.init_calls
    assert codec.decode(encoded) is Failure
    assert Failure.init_calls == before


@pytest.mark.parametrize("record_index", [0, 1])
def test_fresh_process_enum_and_exception_layout_changes_are_rejected(
    tmp_path, record_index
):
    module = tmp_path / "state.py"
    module.write_text(
        "from enum import Enum\n"
        "class Choice(Enum):\n"
        "    READY = 1\n"
        "class Failure(Exception):\n"
        "    __slots__ = ('code',)\n"
    )
    create = tmp_path / "create.py"
    create.write_text(
        "import json\n"
        "from botpipe import codec\n"
        "from state import Choice, Failure\n"
        "print(json.dumps([codec.encode(Choice.READY), codec.encode(Failure)]))\n"
    )
    recorded = _run(create)
    assert recorded.returncode == 0, recorded.stderr

    verify = tmp_path / "verify.py"
    verify.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Choice, Failure\n"
        "values = json.loads(sys.stdin.read())\n"
        "codec.verify_contracts(values[int(sys.argv[1])])\n"
    )
    module.write_text(
        "from enum import Enum\n"
        "class Choice(Enum):\n"
        "    READY = True\n"
        "class Failure(OSError):\n"
        "    __slots__ = ('detail',)\n"
    )
    rejected = _run(verify, str(record_index), input=recorded.stdout)
    assert rejected.returncode != 0
    assert "storage contract" in rejected.stderr
