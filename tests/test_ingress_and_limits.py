"""Run boundaries validate external input; replay consumes committed values."""

import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import BaseModel, model_validator

from botpipe import Botpipe, Session, activity, ask, workflow
from botpipe.config import ConfigError, load_config
from botpipe.limits import RunLimits
from botpipe.providers import FakeProvider


def test_model_input_is_bound_once_and_internal_calls_do_not_revalidate(tmp_path):
    calls = []

    class Input(BaseModel):
        number: int

        @model_validator(mode="after")
        def normalize(self):
            calls.append(self.number)
            self.number += 1
            return self

    @activity
    def echo(value: Input):
        return value

    @workflow
    def child(value: Input):
        return echo(value)

    @workflow
    def root(value: Input):
        result = child(value)
        ask("continue?")
        return result

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(root, {"number": 1})
        assert paused.status == "awaiting_input", paused.error
        assert calls == [1]
        resumed = client.resume(paused.run_id, answer="yes", workflow=root)
        assert resumed.ok, resumed.error
        assert resumed.value.number == 2
        assert calls == [1]
        assert client.resume(paused.run_id, workflow=root).value.number == 2
        assert calls == [1]


def test_human_answer_checkpoint_skips_validation_after_commit_crash(
    tmp_path, monkeypatch
):
    calls = []

    class Answer(BaseModel):
        number: int

        @model_validator(mode="after")
        def normalize(self):
            calls.append(self.number)
            self.number += 1
            return self

    @workflow
    def approval():
        return ask("number?", returns=Answer)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(approval)
        finish = client.journal.finish

        def crash(operation, value):
            raise SystemExit("after normalized answer checkpoint")

        monkeypatch.setattr(client.journal, "finish", crash)
        with pytest.raises(SystemExit):
            client.resume(paused.run_id, workflow=approval, answer={"number": 1})
        assert calls == [1]
        monkeypatch.setattr(client.journal, "finish", finish)
        resumed = client.resume(paused.run_id, workflow=approval)
        assert resumed.ok, resumed.error
        assert resumed.value.number == 2
        assert calls == [1]


def test_cli_does_not_bind_model_input_twice(tmp_path):
    source = tmp_path / "flow.py"
    source.write_text(
        "from pydantic import BaseModel, model_validator\n"
        "from botpipe import workflow\n"
        "class Input(BaseModel):\n"
        "    number: int\n"
        "    @model_validator(mode='after')\n"
        "    def normalize(self):\n"
        "        self.number += 1\n"
        "        return self\n"
        "@workflow\n"
        "def echo(value: Input):\n"
        "    return value.number\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "botpipe.cli",
            "run",
            f"{source}:echo",
            "--arg",
            '{"number":1}',
            "--workspace",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert run.returncode == 0, run.stderr or run.stdout
    assert json.loads(run.stdout)["value"] == 2


@pytest.mark.parametrize("shape", ["generic", "nested_generic", "local", "root"])
def test_fresh_process_resume_registers_input_types_and_preserves_state(
    tmp_path, shape
):
    prefix = (
        "from typing import Generic, TypeVar\n"
        "from pydantic import BaseModel, RootModel\n"
        "from botpipe import workflow, ask\n"
        "T = TypeVar('T')\n"
        "class Box(BaseModel, Generic[T]):\n"
        "    item: T\n"
    )
    raw = {"item": 1}
    if shape == "local":
        body = (
            "def make():\n"
            "    class Input(BaseModel):\n"
            "        item: int\n"
            "    @workflow\n"
            "    def echo(value: Input):\n"
            "        ask('continue?')\n"
            "        return value\n"
            "    return echo\n"
            "echo = make()\n"
        )
    else:
        if shape == "root":
            prefix += "class Input(RootModel[list[int]]):\n    pass\n"
            annotation, raw = "Input", [1, 2]
        elif shape == "nested_generic":
            prefix += "class Input(BaseModel):\n    item: Box[int]\n"
            annotation, raw = "Input", {"item": {"item": 1}}
        else:
            annotation = "Box[int]"
        body = (
            "@workflow\n"
            f"def echo(value: {annotation}):\n"
            "    ask('continue?')\n"
            "    return value\n"
        )
    source = tmp_path / "flow.py"
    source.write_text(prefix + body)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    def cli(*arguments):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "botpipe.cli",
                *arguments,
                "--workspace",
                str(tmp_path),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)

    first = cli("run", f"{source}:echo", "--arg", json.dumps(raw), "--run-id", "fresh")
    assert first["status"] == "awaiting_input"
    resumed = cli("resume", "fresh", "--workflow", f"{source}:echo", "--answer", "yes")
    assert resumed["status"] == "completed"
    assert resumed["value"] == raw
    replayed = cli("resume", "fresh", "--workflow", f"{source}:echo")
    assert replayed["value"] == raw


def test_resumed_limits_are_run_owned_and_inherited_by_children(tmp_path):
    @workflow
    def child():
        return Session().run("answer").value

    @workflow
    def parent():
        ask("continue?")
        return child()

    @workflow
    def simple():
        return "done"

    provider = FakeProvider(["answer"])
    with Botpipe(tmp_path, provider=provider, max_operations=1, timeout=10) as client:
        paused = client.run(parent)
        resumed = client.resume(
            paused.run_id, workflow=parent, answer="yes", max_operations=7, timeout=99
        )
        assert resumed.ok, resumed.error
        assert provider.calls[0].timeout == 99
        assert (client.max_operations, client.timeout) == (1, 10)
        new = client.run(simple)
        record = client.journal.run(new.run_id)
        assert (record["max_operations"], record["timeout"]) == (1, 10)
        assert RunLimits.from_record(client.journal.run(paused.run_id)) == RunLimits(
            7, 99
        )


@pytest.mark.parametrize("value", [True, False, 1.9, 1.0, "2", 0, -1])
def test_operation_limit_validation_is_shared(tmp_path, value):
    with pytest.raises(ValueError, match="positive integer"):
        Botpipe(tmp_path, provider=FakeProvider([]), max_operations=value)
    path = tmp_path / "botpipe.json"
    path.write_text(json.dumps({"max_operations": value}))
    with pytest.raises(ConfigError, match="positive integer"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "value", [True, False, "2", 0, -1, float("inf"), float("nan"), 10**1000]
)
def test_timeout_validation_is_shared(tmp_path, value):
    with pytest.raises(ValueError, match="finite positive"):
        Botpipe(tmp_path, provider=FakeProvider([]), timeout=value)
    path = tmp_path / "botpipe.json"
    path.write_text(json.dumps({"timeout": value}))
    with pytest.raises(ConfigError, match="finite positive"):
        load_config(tmp_path)


def test_invalid_resume_limits_leave_record_and_client_unchanged(tmp_path):
    @workflow
    def approval():
        return ask("continue?")

    with Botpipe(
        tmp_path, provider=FakeProvider([]), max_operations=3, timeout=10
    ) as client:
        paused = client.run(approval)
        before = client.journal.run(paused.run_id)
        for overrides in (
            {"max_operations": True},
            {"timeout": float("nan")},
            {"timeout": True},
        ):
            with pytest.raises(ValueError):
                client.resume(paused.run_id, workflow=approval, **overrides)
            assert client.journal.run(paused.run_id) == before
            assert client.limits == RunLimits(3, 10)


def test_run_limits_are_immutable_and_reject_non_builtin_numeric_values():
    limits = RunLimits(3, 2)
    assert limits.timeout == 2.0
    with pytest.raises(FrozenInstanceError):
        limits.timeout = 4

    with pytest.raises(ValueError, match="positive integer"):
        RunLimits(Fraction(3, 1), 2)
    with pytest.raises(ValueError, match="finite positive"):
        RunLimits(3, Fraction(1, 2))
    with pytest.raises(ValueError, match="finite positive"):
        RunLimits.from_record({"max_operations": 3, "timeout": float("-inf")})


@pytest.mark.parametrize("native_base", [Exception, OSError])
def test_exception_replay_preserves_slots_without_running_user_init(
    tmp_path, native_base
):
    calls = []

    class Failure(native_base):
        __slots__ = ("code",)

        def __init__(self, code):
            calls.append(code)
            self.code = code
            if native_base is OSError:
                super().__init__(2, "missing", "/missing/file")
            else:
                super().__init__("failed")

    @activity
    def fail():
        raise Failure(7)

    @workflow
    def job():
        try:
            fail()
        except Failure as error:
            ask("continue?")
            return error.code, getattr(error, "filename", None)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job)
        assert paused.status == "awaiting_input", paused.error
        resumed = client.resume(paused.run_id, workflow=job, answer="yes")
        assert resumed.ok, resumed.error
        assert resumed.value == (7, "/missing/file" if native_base is OSError else None)
        assert calls == [7]


def test_unresolved_annotation_cannot_silently_disable_input_validation(tmp_path):
    @workflow
    def invalid(value: "int", missing: "UndefinedContract" = None):  # noqa: F821
        return type(value).__name__

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(ValueError, match="Cannot resolve workflow annotations"):
            client.run(invalid, "1")
        assert client.runs() == []


def test_invalid_cli_input_is_a_usage_error(tmp_path):
    source = tmp_path / "flow.py"
    source.write_text(
        "from botpipe import workflow\n@workflow\ndef echo(value: int): return value\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "botpipe.cli",
            "run",
            f"{source}:echo",
            "invalid",
            "--workspace",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2, result.stderr
    assert "Invalid workflow input" in result.stderr
