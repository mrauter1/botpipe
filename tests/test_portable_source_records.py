from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


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
        "from botpipe import ask_human, workflow\n"
        "@workflow\n"
        "def job():\n"
        "    ask_human('continue?')\n"
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
        "@activity(retry_safe=False)\n"
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
