"""Enum and exception storage contracts are structural and source-free."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum, Flag, IntFlag
from pathlib import Path
from typing import Literal

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
    assert restored is type(value)(value.value)


def test_enum_records_and_literal_contracts_ignore_public_presentations():
    class PresentedPermission(Flag):
        READ = 1
        WRITE = 2

        @property
        def name(self):
            return f"display:{object.__getattribute__(self, '_name_')}"

        @property
        def value(self):
            return object.__getattribute__(self, "_value_") + 100

    @dataclass
    class Request:
        permission: object

    literal = Literal[PresentedPermission.READ]
    Request.__annotations__["permission"] = literal
    Request.__dataclass_fields__["permission"].type = literal

    named = codec.encode(PresentedPermission.READ)
    assert named["member"] == "READ"
    assert named["value"] == 1
    assert named["contract"]["members"] == [["READ", 1], ["WRITE", 2]]
    assert codec.decode(named) is PresentedPermission.READ

    composite_record = codec.encode(PresentedPermission(3))
    for _ in range(3):
        restored = codec.decode(composite_record)
        assert restored.name == "display:READ|WRITE"
        assert restored.value == 103
        composite_record = codec.encode(restored)
        assert composite_record["member"] == "READ|WRITE"
        assert composite_record["value"] == 3

    literal_contract = codec.encode(Request)["contract"]
    assert literal_contract["fields"][0][1] == {
        "kind": "literal",
        "values": [
            {
                "enum": codec.type_name(PresentedPermission),
                "member": "READ",
            }
        ],
    }

    PresentedPermission.name = property(
        lambda self: f"shown:{object.__getattribute__(self, '_name_')}"
    )
    PresentedPermission.value = property(
        lambda self: object.__getattribute__(self, "_value_") + 200
    )
    assert codec.encode(Request)["contract"] == literal_contract


def test_fresh_process_enum_presentations_do_not_change_storage(tmp_path):
    module = tmp_path / "state.py"
    initial_source = (
        "from enum import Flag\n"
        "from pathlib import Path\n"
        "from botpipe import activity, ask_human, workflow\n"
        "class Permission(Flag):\n"
        "    READ = 1\n"
        "    WRITE = 2\n"
        "    @property\n"
        "    def name(self):\n"
        "        return f'display:{self._name_}'\n"
        "    @property\n"
        "    def value(self):\n"
        "        return self._value_ + 100\n"
        "@activity\n"
        "def produce():\n"
        "    with Path('effects.log').open('a') as stream:\n"
        "        stream.write('produce\\n')\n"
        "    return Permission(3)\n"
        "@workflow\n"
        "def job():\n"
        "    result = produce()\n"
        "    ask_human('continue?')\n"
        "    return result\n"
    )
    module.write_text(initial_source)
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from state import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='enum-presentation')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
    )
    recorded = _run(create)
    assert recorded.returncode == 0, recorded.stderr

    module.write_text(initial_source.replace("+ 100", "+ 2_000"))
    resume = tmp_path / "resume.py"
    resume.write_text(
        'from botpipe import Botpipe\nfrom botpipe.providers import FakeProvider\nfrom state import job\nwith Botpipe(\'.\', provider=FakeProvider([])) as client:\n    result = client.resume(\n        \'enum-presentation\', workflow=job, answers={client.pending(\'enum-presentation\')[0]["operation_id"]: \'yes\'}\n    )\n    assert result.ok, result.error\n    restored = result.value\n    assert restored.name == \'display:READ|WRITE\'\n    assert restored.value == 2003\n    operation = next(\n        row for row in client.journal.operations(\'enum-presentation\')\n        if row[\'kind\'] == \'activity\'\n    )\n    assert operation[\'result\'][\'member\'] == \'READ|WRITE\'\n    assert operation[\'result\'][\'value\'] == 3\n    assert operation[\'result\'][\'contract\'][\'members\'] == [\n        [\'READ\', 1], [\'WRITE\', 2]\n    ]\n'
    )
    resumed = _run(resume)
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "effects.log").read_text().splitlines() == ["produce"]


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
