from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from botpipe import codec


def _run(script: Path, source_root: Path, workspace: Path):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(source_root), str(Path(__file__).resolve().parents[1]))
        ),
        "BOTPIPE_TEST_WORKSPACE": str(workspace),
    }
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_operation_owners_relocate_with_explicit_workflow(tmp_path):
    code1, code2, workspace = tmp_path / "code1", tmp_path / "code2", tmp_path / "state"
    workspace.mkdir()
    package = code1 / "owned"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "workflow.py").write_text(
        "from botpipe import ask, workflow\n"
        "@workflow\n"
        "def job():\n"
        "    ask('continue?')\n"
        "    return 'done'\n"
    )
    script = code1 / "run.py"
    script.write_text(
        "import os, sys\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe(os.environ['BOTPIPE_TEST_WORKSPACE'], provider=FakeProvider([])) as client:\n"
        "    if sys.argv[-1:] == ['resume']:\n"
        "        result = client.resume('move', workflow=job, answer='yes')\n"
        "    else:\n"
        "        result = client.run(job, run_id='move')\n"
        "    print(result.status, result.value)\n"
    )
    first = _run(script, code1, workspace)
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "awaiting_input None"

    shutil.copytree(code1, code2)
    shutil.rmtree(code1)
    relocated_script = code2 / "run.py"
    resumed = subprocess.run(
        [sys.executable, str(relocated_script), "resume"],
        cwd=code2,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(code2), str(Path(__file__).resolve().parents[1]))
            ),
            "BOTPIPE_TEST_WORKSPACE": str(workspace),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.strip() == "completed done"


def test_relocated_nested_activity_can_be_manually_resolved(tmp_path):
    code1, code2 = tmp_path / "code1", tmp_path / "code2"
    workspace = tmp_path / "state"
    workspace.mkdir()
    package = code1 / "owned"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "workflow.py").write_text(
        "from botpipe import activity, workflow\n"
        "@activity\n"
        "def effect(): raise KeyboardInterrupt\n"
        "@workflow\n"
        "def child(): return effect()\n"
        "@workflow\n"
        "def job(): return child()\n"
    )
    script = code1 / "run.py"
    script.write_text(
        "import os, sys\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "mode = sys.argv[1]\n"
        "with Botpipe(os.environ['BOTPIPE_TEST_WORKSPACE'], provider=FakeProvider([])) as client:\n"
        "    if mode == 'start': result = client.run(job, run_id='nested')\n"
        "    elif mode == 'resolve':\n"
        "        operation = next(r for r in client.inspect('nested')['operations'] if r['kind'] == 'activity')\n"
        "        client.resolve('nested', operation['id'], response='reconciled')\n"
        "        print('resolved')\n"
        "        raise SystemExit\n"
        "    else: result = client.resume('nested', workflow=job)\n"
        "    print(result.status, result.value)\n"
    )
    first = _run_with_args(script, code1, workspace, "start")
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "interrupted None"

    shutil.copytree(code1, code2)
    shutil.rmtree(code1)
    relocated = code2 / "run.py"
    resolved = _run_with_args(relocated, code2, workspace, "resolve")
    assert resolved.returncode == 0, resolved.stderr
    assert resolved.stdout.strip() == "resolved"
    resumed = _run_with_args(relocated, code2, workspace, "resume")
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.strip() == "completed reconciled"


def _run_with_args(script, source_root, workspace, *args):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(source_root), str(Path(__file__).resolve().parents[1]))
        ),
        "BOTPIPE_TEST_WORKSPACE": str(workspace),
    }
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=script.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_owner_locator_requires_current_root_and_legacy_is_same_location_only(tmp_path):
    root = tmp_path / "workflow.py"
    root.write_text("# workflow\n")
    with codec.source_identity(root):
        encoded = codec.encode({"plain": 1}, record_owners=True)
    assert encoded["owners"]["schema"] == "botpipe.source-owners.v2"
    assert codec.semantic_encoding(encoded) == codec.encode({"plain": 1})
    with pytest.raises(TypeError, match="requires the current source anchor"):
        codec.recorded_source_boundaries(encoded)
    assert codec.recorded_source_boundaries(encoded, root_boundary=root) == (root,)

    legacy = {**encoded, "owners": [str(root)]}
    assert codec.recorded_source_boundaries(legacy) == (root,)
    root.unlink()
    with pytest.raises(FileNotFoundError):
        codec.recorded_source_boundaries(legacy)


def test_malformed_owner_locator_fails_closed(tmp_path):
    root = tmp_path / "workflow.py"
    root.write_text("# workflow\n")
    malformed = {
        "$botpipe": "capsule",
        "version": 1,
        "sources": {},
        "owners": {
            "schema": "botpipe.source-owners.v2",
            "anchor_kind": "file",
            "boundaries": [{"kind": "file", "relative": "workflow.py"}],
        },
        "value": {"$botpipe": "dict", "value": {"$botpipe": "still user data"}},
    }
    with pytest.raises(TypeError, match="current source anchor"):
        codec.recorded_source_boundaries(malformed)

    # Source-free mappings that resemble codec tags remain ordinary user data.
    assert codec.decode(codec.encode({"$botpipe": "type", "type": "not-a-type"})) == {
        "$botpipe": "type",
        "type": "not-a-type",
    }

    with codec.source_identity(()):
        assert codec.encode({"plain": 1}, record_owners=True) == codec.encode(
            {"plain": 1}
        )


@pytest.mark.parametrize(
    "relative", ["C:\\owned.py", "C:owned.py", "\\\\host\\owned.py", "a/../b.py"]
)
def test_nonportable_or_noncanonical_owner_paths_are_rejected(tmp_path, relative):
    root = tmp_path / "workflow.py"
    root.write_text("# workflow\n")
    encoded = {
        "$botpipe": "capsule",
        "version": 1,
        "sources": {},
        "owners": {
            "schema": "botpipe.source-owners.v2",
            "anchor_kind": "file",
            "boundaries": [
                {"kind": "file", "relative": relative},
            ],
        },
        "value": None,
    }
    with pytest.raises(TypeError, match="source owner"):
        codec.recorded_source_boundaries(encoded, root_boundary=root)
