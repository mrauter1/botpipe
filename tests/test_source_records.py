"""Fresh-process storage-contract coverage for durable typed values."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

from botpipe import codec


class ContractValue(BaseModel):
    value: int


def _run(script: Path, *, input: str | None = None):
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
        ),
    }
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=env,
        input=input,
        capture_output=True,
        text=True,
        check=False,
    )


def test_user_mapping_keys_that_resemble_codec_tags_round_trip():
    value = {"$botpipe": "type", "type": "not_a_type"}
    assert codec.decode(codec.encode(value)) == value


def test_contract_is_memoized_per_encode(monkeypatch):
    calls = 0
    original = codec._Contracts.for_type

    def counted(self, cls, path, depth=0):
        nonlocal calls
        if cls is ContractValue and cls not in self.memo:
            calls += 1
        return original(self, cls, path, depth)

    monkeypatch.setattr(codec._Contracts, "for_type", counted)
    encoded = codec.encode([ContractValue(value=index) for index in range(20)])

    assert calls == 1
    assert codec.decode(encoded) == [ContractValue(value=index) for index in range(20)]


def test_same_file_method_edit_preserves_storage_compatibility(tmp_path):
    module = tmp_path / "state.py"
    module.write_text(
        "from pydantic import BaseModel\n"
        "class Value(BaseModel):\n"
        "    item: int\n"
        "    @property\n"
        "    def adjusted(self): return self.item + 1\n"
    )
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import codec\n"
        "from state import Value\n"
        "print(codec.dumps(Value(item=4)))\n"
    )
    encoded = _run(create)
    assert encoded.returncode == 0, encoded.stderr

    module.write_text(module.read_text().replace("self.item + 1", "self.item + 100"))
    resume = tmp_path / "resume.py"
    resume.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Value\n"
        "value = codec.decode(json.loads(sys.stdin.read()))\n"
        "assert type(value) is Value\n"
        "assert value.item == 4\n"
        "assert value.adjusted == 104\n"
    )
    restored = _run(resume, input=encoded.stdout)
    assert restored.returncode == 0, restored.stderr


def test_field_type_and_layout_edits_are_rejected_before_hydration(tmp_path):
    module = tmp_path / "state.py"
    module.write_text(
        "from pydantic import BaseModel\nclass Value(BaseModel):\n    item: int\n"
    )
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import codec\n"
        "from state import Value\n"
        "print(codec.dumps(Value(item=4)))\n"
    )
    encoded = _run(create)
    assert encoded.returncode == 0, encoded.stderr

    resume = tmp_path / "resume.py"
    resume.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Value\n"
        "codec.verify_contracts(json.loads(sys.stdin.read()))\n"
    )
    for changed in (
        "from pydantic import BaseModel\nclass Value(BaseModel):\n    item: str | None\n",
        "from pydantic import BaseModel\nclass Value(BaseModel):\n    item: int\n    label: str\n",
    ):
        module.write_text(changed)
        rejected = _run(resume, input=encoded.stdout)
        assert rejected.returncode != 0
        assert "storage contract for state:Value changed" in rejected.stderr


def test_enum_member_storage_and_flag_layout_edits_are_rejected(tmp_path):
    module = tmp_path / "state.py"
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import codec\n"
        "from state import Choice\n"
        "print(codec.dumps(Choice.READY))\n"
    )
    resume = tmp_path / "resume.py"
    resume.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Choice\n"
        "codec.verify_contracts(json.loads(sys.stdin.read()))\n"
    )
    declarations = (
        (
            "from enum import Enum\nclass Choice(Enum):\n    READY = 1\n",
            "from enum import IntEnum\nclass Choice(IntEnum):\n    READY = 1\n",
        ),
        (
            "from enum import Enum\nclass Choice(Enum):\n    READY = 1\n",
            "from enum import Flag\nclass Choice(Flag):\n    READY = 1\n",
        ),
        (
            "from enum import IntEnum\nclass Choice(IntEnum):\n    READY = 1\n",
            "from enum import IntFlag\nclass Choice(IntFlag):\n    READY = 1\n",
        ),
        (
            "from enum import Enum\nclass Choice(str, Enum):\n    READY = 'ready'\n",
            "from enum import Enum\nclass Choice(Enum):\n    READY = 'ready'\n",
        ),
    )

    for before, after in declarations:
        module.write_text(before)
        encoded = _run(create)
        assert encoded.returncode == 0, encoded.stderr
        module.write_text(after)
        rejected = _run(resume, input=encoded.stdout)
        assert rejected.returncode != 0
        assert "storage contract for state:Choice changed" in rejected.stderr


def test_enum_method_edit_preserves_storage_compatibility(tmp_path):
    module = tmp_path / "state.py"
    module.write_text(
        "from enum import Enum\n"
        "class Choice(Enum):\n"
        "    READY = 1\n"
        "    def label(self): return 'old'\n"
    )
    create = tmp_path / "create.py"
    create.write_text(
        "from botpipe import codec\n"
        "from state import Choice\n"
        "print(codec.dumps(Choice.READY))\n"
    )
    encoded = _run(create)
    assert encoded.returncode == 0, encoded.stderr

    module.write_text(module.read_text().replace("return 'old'", "return 'updated'"))
    resume = tmp_path / "resume.py"
    resume.write_text(
        "import json, sys\n"
        "from botpipe import codec\n"
        "from state import Choice\n"
        "value = codec.decode(json.loads(sys.stdin.read()))\n"
        "assert value is Choice.READY\n"
        "assert value.label() == 'updated'\n"
    )
    restored = _run(resume, input=encoded.stdout)
    assert restored.returncode == 0, restored.stderr
