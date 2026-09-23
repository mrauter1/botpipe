from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe, activity, ask_human, workflow
from botpipe.errors import ActivityFailed
from botpipe.providers import FakeProvider


def test_wait_input_lost_ack_keeps_authoritative_waiting_checkpoint(
    tmp_path, monkeypatch
):
    @workflow
    def approval():
        return ask_human("approve?", returns=bool)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        wait_input = client.journal.wait_input

        def lose_ack(operation_id, data):
            wait_input(operation_id, data)
            raise OSError("lost wait acknowledgement")

        monkeypatch.setattr(client.journal, "wait_input", lose_ack)
        paused = client.run(approval, run_id="wait-ack")
        operation = client.journal.operations(paused.run_id)[0]
        assert paused.status == "awaiting_input"
        assert operation["status"] == "waiting"
        assert operation["error"] is None

        monkeypatch.setattr(client.journal, "wait_input", wait_input)
        resumed = client.resume(paused.run_id, workflow=approval, answer=True)
        assert resumed.value is True


def test_builtin_oserror_replay_preserves_native_unset_state(tmp_path):
    calls = []

    @activity
    def fail():
        calls.append(1)
        raise OSError("disk broke")

    @workflow
    def job():
        try:
            fail()
        except OSError as error:
            ask_human("continue?")
            return str(error), error.args, error.filename

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job)
        resumed = client.resume(paused.run_id, workflow=job, answer="yes")
        assert resumed.value == ("disk broke", ("disk broke",), None)
        assert calls == [1]


def test_unsupported_exception_state_falls_back_on_initial_and_replay(tmp_path):
    calls = []

    class Unsupported(Exception):
        def __init__(self):
            calls.append(1)
            self.state = object()
            super().__init__("unsupported")

    @activity
    def fail():
        raise Unsupported()

    @workflow
    def job():
        try:
            fail()
        except ActivityFailed as error:
            ask_human("continue?")
            return str(error)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job)
        resumed = client.resume(paused.run_id, workflow=job, answer="yes")
        assert resumed.value.endswith("Unsupported: unsupported")
        assert calls == [1]


@pytest.mark.parametrize(
    "import_style",
    ["future_annotation", "module", "nested", "facade", "method_helper"],
)
def test_fresh_import_returns_completed_value_after_contract_source_edit(
    tmp_path, import_style
):
    package = tmp_path / "owned"
    package.mkdir()
    (package / "__init__.py").write_text("")
    contract = package / "contract.py"
    edited_source = contract
    if import_style == "nested":
        edited_source = package / "inner.py"
        edited_source.write_text(
            "from pydantic import BaseModel\n"
            "class Inner(BaseModel):\n"
            "    x: int\n"
            "    @property\n"
            "    def adjusted(self): return self.x + 1\n"
        )
        contract.write_text(
            "from pydantic import BaseModel\n"
            "from .inner import Inner\n"
            "class Value(BaseModel):\n"
            "    inner: Inner\n"
        )
        flow_source = (
            "from botpipe import workflow\n"
            "from .contract import Value\n"
            "@workflow\n"
            "def job(value: Value) -> int: return value.inner.adjusted\n"
        )
        invocation = "job, Value(inner=Inner(x=1))"
        contract_import = (
            "from owned.contract import Value\nfrom owned.inner import Inner\n"
        )
    elif import_style == "method_helper":
        edited_source = package / "helper.py"
        edited_source.write_text("def compute(x): return x + 1\n")
        contract.write_text(
            "from dataclasses import dataclass\n"
            "from . import helper\n"
            "@dataclass\n"
            "class Value:\n"
            "    x: int\n"
            "    @property\n"
            "    def adjusted(self): return helper.compute(self.x)\n"
        )
        flow_source = (
            "from botpipe import workflow\n"
            "from .contract import Value\n"
            "@workflow\n"
            "def job(value: Value) -> int: return value.adjusted\n"
        )
        invocation = "job, Value(x=1)"
        contract_import = "from owned.contract import Value\n"
    else:
        contract.write_text(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Value:\n"
            "    x: int\n"
            "    @property\n"
            "    def adjusted(self): return self.x + 1\n"
        )
    if import_style == "future_annotation":
        flow_source = (
            "from __future__ import annotations\n"
            "from botpipe import workflow\n"
            "from .contract import Value\n"
            "@workflow\n"
            "def job(value: Value) -> int: return value.adjusted\n"
        )
        invocation = "job, Value(x=1)"
        contract_import = "from owned.contract import Value\n"
    elif import_style in {"module", "facade"}:
        module_name = "contract"
        if import_style == "facade":
            (package / "facade.py").write_text("from .contract import Value\n")
            module_name = "facade"
        flow_source = (
            "from botpipe import workflow\n"
            f"from . import {module_name}\n"
            "@workflow\n"
            f"def job() -> int: return {module_name}.Value(x=1).adjusted\n"
        )
        invocation = "job"
        contract_import = ""
    (package / "workflow.py").write_text(flow_source)
    runner = tmp_path / "runner.py"
    runner.write_text(
        "from pathlib import Path\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        f"{contract_import}"
        "from owned.workflow import job\n"
        "root = Path(__file__).parent\n"
        "with Botpipe(root, provider=FakeProvider([])) as client:\n"
        f"    print(client.run({invocation}, run_id='source-edit').value)\n"
    )
    resume = tmp_path / "resume.py"
    resume.write_text(
        "from pathlib import Path\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "root = Path(__file__).parent\n"
        "with Botpipe(root, provider=FakeProvider([])) as client:\n"
        "    print(client.resume('source-edit', workflow=job).value)\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
        ),
    }
    first = subprocess.run(
        [sys.executable, str(runner)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "2"

    edited_source.write_text(edited_source.read_text().replace("x + 1", "x + 100"))
    second = subprocess.run(
        [sys.executable, str(resume)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "2"
