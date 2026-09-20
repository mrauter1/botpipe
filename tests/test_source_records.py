from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, ask, codec, workflow
from botpipe.providers import FakeProvider


class CapsuleValue(BaseModel):
    value: int


def test_resume_does_not_treat_user_mapping_keys_as_codec_tags(tmp_path):
    @workflow
    def job(payload: dict):
        ask("continue?")
        return payload

    payload = {"$botpipe": "type", "type": "not_a_type"}
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, payload, run_id="reserved-keys")
        resumed = client.resume(paused.run_id, workflow=job, answer="yes")
    assert resumed.value == payload


def test_source_capsule_is_deduplicated_and_old_typed_state_fails_closed(
    monkeypatch,
):
    from botpipe import provenance

    boundary = Path(__file__).resolve()
    captures = 0
    original_capture = provenance.capture_type_source

    def counted_capture(*args, **kwargs):
        nonlocal captures
        captures += 1
        return original_capture(*args, **kwargs)

    monkeypatch.setattr(provenance, "capture_type_source", counted_capture)
    with codec.source_identity(boundary):
        encoded = codec.encode([CapsuleValue(value=index) for index in range(20)])
    assert encoded["$botpipe"] == "capsule"
    assert list(encoded["sources"]) == [codec.type_name(CapsuleValue)]
    assert captures == 1
    with codec.source_identity(boundary):
        restored = codec.decode(encoded)
    assert restored == [CapsuleValue(value=index) for index in range(20)]

    historical = codec.encode(CapsuleValue(value=1))
    with (
        codec.source_identity(boundary),
        pytest.raises(TypeError, match="has no source identity"),
    ):
        codec.decode(historical)

    plain = codec.encode({"plain": 1})
    with codec.source_identity(boundary):
        assert codec.encode({"plain": 1}) == plain


def _run(script: Path):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(Path(__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", ""))
        ),
    }
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("callable_kind", ["instance", "bound", "partial"])
def test_fresh_resume_rejects_imported_callable_source_edit(tmp_path, callable_kind):
    package = tmp_path / "owned"
    package.mkdir()
    (package / "__init__.py").write_text("")
    helper = package / "helper.py"
    if callable_kind == "partial":
        helper.write_text(
            "from functools import partial\n"
            "def implementation(x): return x + 1\n"
            "adjust = partial(implementation)\n"
        )
    else:
        suffix = "" if callable_kind == "instance" else ".__call__"
        helper.write_text(
            "class BaseAdjuster:\n"
            "    def __call__(self, x): return x + 1\n"
            "class Adjuster(BaseAdjuster): pass\n"
            "owner = Adjuster()\n"
            f"adjust = owner{suffix}\n"
        )
    (package / "workflow.py").write_text(
        "from botpipe import ask, workflow\n"
        "from .helper import adjust\n"
        "@workflow\n"
        "def job(x: int):\n"
        "    value = adjust(x)\n"
        "    ask('continue?')\n"
        "    return value\n"
    )
    (tmp_path / "start.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    print(client.run(job, 1, run_id='source').status)\n"
    )
    (tmp_path / "resume.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    client.resume('source', workflow=job, answer='yes')\n"
    )
    first = _run(tmp_path / "start.py")
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "awaiting_input"
    helper.write_text(helper.read_text().replace("x + 1", "x + 100"))
    resumed = _run(tmp_path / "resume.py")
    assert resumed.returncode != 0
    assert "WorkflowChanged" in resumed.stderr


def test_runtime_concrete_subtype_source_is_verified_before_answer_write(tmp_path):
    package = tmp_path / "owned"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "base.py").write_text(
        "from pydantic import BaseModel\nclass BaseValue(BaseModel): value: int\n"
    )
    derived = package / "derived.py"
    derived.write_text(
        "from .base import BaseValue\n"
        "class DerivedValue(BaseValue):\n"
        "    @property\n"
        "    def adjusted(self): return self.value + 1\n"
    )
    (package / "workflow.py").write_text(
        "from botpipe import ask, workflow\n"
        "from .base import BaseValue\n"
        "@workflow\n"
        "def job(value: BaseValue):\n"
        "    ask('continue?')\n"
        "    return value.adjusted\n"
    )
    (tmp_path / "start.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.derived import DerivedValue\n"
        "from owned.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    print(client.run(job, DerivedValue(value=1), run_id='source').status)\n"
    )
    (tmp_path / "resume.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    client.resume('source', workflow=job, answer='yes')\n"
    )
    first = _run(tmp_path / "start.py")
    assert first.returncode == 0, first.stderr
    derived.write_text(derived.read_text().replace("value + 1", "value + 100"))
    resumed = _run(tmp_path / "resume.py")
    assert resumed.returncode != 0
    assert (
        "Source for durable type owned.derived:DerivedValue changed" in resumed.stderr
    )

    # Source verification runs before the pending answer checkpoint mutates.
    db = sqlite3.connect(tmp_path / ".botpipe" / "state.sqlite3")
    response = db.execute(
        "SELECT response FROM operations WHERE run_id='source' AND kind='input'"
    ).fetchone()[0]
    db.close()
    assert "answer" not in json.loads(response)


@pytest.mark.parametrize("dependency_kind", ["mro", "helper"])
def test_runtime_type_tracks_owned_dependencies_across_workflow_roots(
    tmp_path, dependency_kind
):
    root = tmp_path / "rootpkg"
    child = tmp_path / "childpkg"
    root.mkdir()
    child.mkdir()
    (root / "__init__.py").write_text("")
    (child / "__init__.py").write_text("")
    dependency = root / "base.py"
    if dependency_kind == "mro":
        dependency.write_text(
            "from pydantic import BaseModel\n"
            "class BaseValue(BaseModel):\n"
            "    value: int\n"
            "    @property\n"
            "    def adjusted(self): return self.value + 1\n"
        )
        derived_source = (
            "from rootpkg.base import BaseValue\nclass DerivedValue(BaseValue): pass\n"
        )
    else:
        dependency.write_text("def adjust(value): return value + 1\n")
        derived_source = (
            "from pydantic import BaseModel\n"
            "from rootpkg import base\n"
            "class DerivedValue(BaseModel):\n"
            "    value: int\n"
            "    @property\n"
            "    def adjusted(self): return base.adjust(self.value)\n"
        )
    (child / "derived.py").write_text(derived_source)
    (child / "workflow.py").write_text(
        "from botpipe import workflow\n@workflow\ndef echo(value): return value\n"
    )
    (root / "workflow.py").write_text(
        "from botpipe import ask, workflow\n"
        "from childpkg.workflow import echo\n"
        "@workflow\n"
        "def job(value):\n"
        "    result = echo(value)\n"
        "    ask('continue?')\n"
        "    return result.adjusted\n"
    )
    (tmp_path / "start.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from childpkg.derived import DerivedValue\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    print(client.run(job, DerivedValue(value=1), run_id='union').status)\n"
    )
    (tmp_path / "resume.py").write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    client.resume('union', workflow=job, answer='yes')\n"
    )
    first = _run(tmp_path / "start.py")
    assert first.returncode == 0, first.stderr
    dependency.write_text(dependency.read_text().replace("value + 1", "value + 100"))
    resumed = _run(tmp_path / "resume.py")
    assert resumed.returncode != 0
    assert "Source for durable type childpkg.derived:DerivedValue changed" in (
        resumed.stderr
    )
