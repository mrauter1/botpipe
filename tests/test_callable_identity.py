"""Callable normalization and parallel source identity regressions."""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from pathlib import Path

import botpipe
import pytest

from botpipe import Botpipe, Policy, Session, parallel, workflow
from botpipe._callables import describe_callable
from botpipe.providers import FakeProvider
from botpipe.runtime import _function_version


SDK_ROOT = Path(botpipe.__file__).resolve().parents[1]


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(
                None,
                (str(SDK_ROOT), str(path.parent), os.environ.get("PYTHONPATH")),
            )
        ),
    }
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=path.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def test_partial_binding_arrangement_is_canonical_and_distinct():
    def add(left, right=0):
        return left + right

    positional = functools.partial(add, 1, 2)
    keyword = functools.partial(add, 1, right=2)
    reordered_a = functools.partial(add, left=1, right=2)
    reordered_b = functools.partial(add, right=2, left=1)

    assert _function_version(positional) != _function_version(keyword)
    assert _function_version(reordered_a) != _function_version(reordered_b)

    def observe(**kwargs):
        return list(kwargs)

    first = functools.partial(observe, left=1, right=2)
    second = functools.partial(observe, right=2, left=1)
    assert first() != second()
    assert _function_version(first) != _function_version(second)


def test_builtin_callable_identities_do_not_collide():
    groups = (
        ([].append, [].extend, {}.get),
        (str.upper, str.lower),
        (len, print),
    )
    for callables in groups:
        identities = {_function_version(item) for item in callables}
        assert len(identities) == len(callables)


def test_partial_callable_bindings_contribute_source_targets():
    def execute(callback):
        return callback()

    def callback():
        return 1

    descriptor = describe_callable(functools.partial(execute, callback))
    assert execute in descriptor.source_targets
    assert callback in descriptor.source_targets
    assert callback in descriptor.boundary_targets


def test_partial_rejects_unsupported_explicit_values_without_repr_addresses():
    def use(value):
        return value

    with pytest.raises(
        TypeError, match="Unsupported explicit partial argument 0"
    ) as caught:
        _function_version(functools.partial(use, object()))
    assert "0x" not in str(caught.value)


def test_partial_helper_edit_changes_identity_in_a_fresh_process(tmp_path):
    helper = _write(
        tmp_path / "helper.py",
        "def add(left, right): return left + right\n",
    )
    inspect_identity = _write(
        tmp_path / "identity.py",
        "from functools import partial\n"
        "from botpipe.runtime import _function_version\n"
        "from helper import add\n"
        "print(_function_version(partial(add, 1, right=2)))\n",
    )

    before = _run(inspect_identity)
    assert before.returncode == 0, before.stderr
    helper.write_text(helper.read_text().replace("left + right", "left * right"))
    after = _run(inspect_identity)
    assert after.returncode == 0, after.stderr
    assert before.stdout != after.stdout


def test_parallel_supports_lambda_wrapped_method_and_callable_instance(tmp_path):
    class Calls:
        def method(self):
            return "method"

        def __call__(self):
            return "instance"

    def original():
        return "wrapped"

    @functools.wraps(original)
    def wrapped():
        return original()

    calls = Calls()

    @workflow
    def job():
        return parallel(
            lambda: "lambda",
            wrapped,
            functools.partial(calls.method),
            calls,
        )

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job)
        replay = client.resume(first.run_id, workflow=job)

    assert first.value == ["lambda", "wrapped", "method", "instance"]
    assert replay.value == first.value


def test_partial_live_session_method_does_not_serialize_receiver(tmp_path):
    @workflow
    def job():
        session = Session()
        turn = functools.partial(
            session.run,
            "review",
            policy=Policy(sandbox_mode="read_only"),
        )
        return parallel(turn)[0].value

    with Botpipe(tmp_path, provider=FakeProvider(["approved"])) as client:
        result = client.run(job)

    assert result.value == "approved"


@pytest.mark.parametrize("field", ["name", "version", "policy"])
@pytest.mark.parametrize("partial", [False, True])
def test_completed_parallel_pins_workflow_metadata(tmp_path, field, partial):
    executions = []

    @workflow(name="branch", version="1", policy=Policy(sandbox_mode="read_only"))
    def branch():
        executions.append("once")
        return "done"

    # Runtime selection is deliberately opaque to the root's static identity.
    # The parallel operation must pin the selected definition itself.
    choices = [functools.partial(branch) if partial else branch]

    @workflow
    def job():
        return parallel(choices[0])

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job)
        assert first.ok, first.error
        assert client.resume(first.run_id, workflow=job).ok
        before = client.journal.operations(first.run_id)
        root_identity = job.fingerprint
        setattr(
            branch,
            field,
            Policy(sandbox_mode="workspace_write") if field == "policy" else "changed",
        )
        assert job.fingerprint == root_identity

        replay = client.resume(first.run_id, workflow=job)

        assert replay.status == "failed"
        assert "ReplayMismatch" in replay.error
        assert client.journal.operations(first.run_id) == before
        assert executions == ["once"]


def test_raw_paused_branch_rejects_cross_package_model_helper_edit(tmp_path):
    _write(tmp_path / "branchpkg/__init__.py", "")
    model = _write(
        tmp_path / "branchpkg/model.py",
        "class Config:\n    @property\n    def label(self): return 'old'\n",
    )
    _write(
        tmp_path / "branchpkg/branch.py",
        "from botpipe import ask\n"
        "from .model import Config\n"
        "def wait():\n"
        "    answer = ask('continue?')\n"
        "    return Config().label, answer\n",
    )
    _write(tmp_path / "rootpkg/__init__.py", "")
    _write(
        tmp_path / "rootpkg/workflow.py",
        "from botpipe import parallel, workflow\n"
        "from branchpkg.branch import wait\n"
        "@workflow\n"
        "def job(): return parallel(wait)\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='paused')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert len(client.journal.operations('paused')) == 2\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('paused', workflow=job, answer='yes')\n"
        "    assert result.status == 'failed', result.error\n"
        "    assert 'ReplayMismatch' in result.error, result.error\n"
        "    assert len(client.journal.operations('paused')) == 2\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stderr
    model.write_text(model.read_text().replace("'old'", "'new'"))
    rejected = _run(resume)
    assert rejected.returncode == 0, rejected.stderr


def test_parallel_result_owns_cross_package_type_and_replays_unchanged(tmp_path):
    _write(tmp_path / "branchpkg/__init__.py", "")
    model = _write(
        tmp_path / "branchpkg/model.py",
        "from pydantic import BaseModel\n"
        "class Value(BaseModel):\n"
        "    amount: int\n"
        "    @property\n"
        "    def adjusted(self): return self.amount + 1\n",
    )
    _write(
        tmp_path / "branchpkg/branch.py",
        "from .model import Value\ndef produce(): return Value(amount=3)\n",
    )
    _write(tmp_path / "rootpkg/__init__.py", "")
    _write(
        tmp_path / "rootpkg/workflow.py",
        "from botpipe import ask, parallel, workflow\n"
        "from branchpkg.branch import produce\n"
        "@workflow\n"
        "def job():\n"
        "    values = parallel(produce)\n"
        "    ask('continue?')\n"
        "    return values\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='typed')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert len(client.journal.operations('typed')) == 2\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('typed', workflow=job, answer='yes')\n"
        "    assert result.ok, result.error\n"
        "    assert result.value[0].amount == 3\n"
        "    assert len(client.journal.operations('typed')) == 2\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stderr
    valid = _run(resume)
    assert valid.returncode == 0, valid.stderr

    # A second paused run proves the recorded aggregate value owns branchpkg,
    # so hydration rejects a model implementation edit before replay.
    start_source = start.read_text().replace("'typed'", "'typed-drift'")
    start.write_text(start_source)
    second = _run(start)
    assert second.returncode == 0, second.stderr
    model.write_text(model.read_text().replace("amount + 1", "amount + 100"))
    drift_resume = resume.read_text().replace("'typed'", "'typed-drift'")
    resume.write_text(drift_resume)
    rejected = _run(resume)
    assert rejected.returncode != 0
    assert "Source for durable type branchpkg.model:Value changed" in rejected.stderr
