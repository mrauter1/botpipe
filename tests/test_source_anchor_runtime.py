"""Runtime integration coverage for independent source ownership anchors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def _run(script: Path, workspace: Path, state: Path):
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=workspace,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(workspace), str(SDK_ROOT))),
            "BOTPIPE_TEST_STATE": str(state),
        },
        capture_output=True,
        text=True,
        check=False,
    )


_SYNTHETIC_ROOT = (
    "from botpipe import workflow\n"
    "def make_root():\n"
    "    namespace = {'__name__': 'synthetic_root'}\n"
    "    source = (\n"
    "        'def job():\\n'\n"
    "        '    from childpkg.workflow import child\\n'\n"
    "        '    return child()\\n'\n"
    "    )\n"
    "    exec(compile(source, '<source-free-root>', 'exec'), namespace)\n"
    "    return workflow(namespace['job'])\n"
)


def test_source_free_root_anchors_full_child_ownership_across_relocation(tmp_path):
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    state = tmp_path / "state"
    original.mkdir()
    state.mkdir()
    _write(original / "childpkg" / "__init__.py", "")
    _write(
        original / "childpkg" / "workflow.py",
        "from botpipe import activity, workflow\n"
        "from helperpkg.helper import worker\n"
        "from helperpkg.model import Reconciled\n"
        "@activity\n"
        "def unsafe() -> Reconciled:\n"
        "    raise KeyboardInterrupt\n"
        "@workflow\n"
        "def child(callback=worker) -> Reconciled:\n"
        "    callback()\n"
        "    return unsafe()\n",
    )
    _write(original / "helperpkg" / "__init__.py", "")
    _write(
        original / "helperpkg" / "helper.py",
        "def worker():\n    return 'helper'\n",
    )
    _write(
        original / "helperpkg" / "model.py",
        "from pydantic import BaseModel\n"
        "class Reconciled(BaseModel):\n"
        "    value: str\n",
    )

    start = _write(
        original / "start.py",
        _SYNTHETIC_ROOT + "import json, os\n"
        "from pathlib import Path\n"
        "from botpipe import Botpipe, codec\n"
        "from botpipe.providers import FakeProvider\n"
        "from helperpkg.model import Reconciled\n"
        "workspace = Path.cwd().resolve()\n"
        "job = make_root()\n"
        "assert job.fn.__module__ == 'synthetic_root'\n"
        "assert job.fn.__qualname__ == 'job'\n"
        "assert job._source_context.origin_source is None\n"
        "assert job._source_context.owned_boundaries == ()\n"
        "assert job._source_context.ownership_anchor is None\n"
        "with Botpipe(\n"
        "    workspace,\n"
        "    state_dir=os.environ['BOTPIPE_TEST_STATE'],\n"
        "    provider=FakeProvider([]),\n"
        ") as client:\n"
        "    result = client.run(job, run_id='source-anchor')\n"
        "    assert result.status == 'interrupted', result.error\n"
        "    metadata = client.journal.run(result.run_id)\n"
        "    assert metadata['source_file'] is None\n"
        "    assert Path(metadata['source_anchor']) == workspace\n"
        "    operations = client.journal.operations(result.run_id)\n"
        "    assert [item['kind'] for item in operations] == ['child', 'activity']\n"
        "    expected = (workspace / 'childpkg', workspace / 'helperpkg')\n"
        "    expected_locators = [\n"
        "        {'kind': 'directory', 'relative': 'childpkg'},\n"
        "        {'kind': 'directory', 'relative': 'helperpkg'},\n"
        "    ]\n"
        "    for operation in operations:\n"
        "        owners = operation['inputs']['owners']\n"
        "        assert owners == {\n"
        "            'schema': 'botpipe.source-owners.v2',\n"
        "            'anchor_kind': 'directory',\n"
        "            'boundaries': expected_locators,\n"
        "        }, owners\n"
        "        actual = codec.recorded_source_boundaries(\n"
        "            operation['inputs'], root_boundary=workspace\n"
        "        )\n"
        "        assert actual == expected, actual\n"
        "        assert workspace not in actual\n"
        "    Path('owner-inputs.json').write_text(json.dumps(\n"
        "        [item['inputs'] for item in operations], sort_keys=True\n"
        "    ))\n",
    )
    resolve = _write(
        original / "resolve.py",
        "import os\n"
        "from pathlib import Path\n"
        "from botpipe import Botpipe, codec\n"
        "from botpipe.providers import FakeProvider\n"
        "from helperpkg.model import Reconciled\n"
        "workspace = Path.cwd().resolve()\n"
        "with Botpipe(\n"
        "    workspace,\n"
        "    state_dir=os.environ['BOTPIPE_TEST_STATE'],\n"
        "    provider=FakeProvider([]),\n"
        ") as client:\n"
        "    operations = client.journal.operations('source-anchor')\n"
        "    activity = next(item for item in operations if item['kind'] == 'activity')\n"
        "    assert codec.recorded_source_boundaries(\n"
        "        activity['inputs'], root_boundary=workspace\n"
        "    ) == (workspace / 'childpkg', workspace / 'helperpkg')\n"
        "    client.resolve(\n"
        "        'source-anchor', activity['id'],\n"
        "        response=Reconciled(value='reconciled'),\n"
        "    )\n"
        "    completed = client.journal.get(activity['id'])\n"
        "    assert completed['status'] == 'completed'\n"
        "    assert 'helperpkg.model:Reconciled' in completed['result']['sources']\n",
    )
    resume_source = (
        _SYNTHETIC_ROOT + "import json, os\n"
        "from pathlib import Path\n"
        "from botpipe import Botpipe, codec\n"
        "from botpipe.providers import FakeProvider\n"
        "from helperpkg.model import Reconciled\n"
        "workspace = Path.cwd().resolve()\n"
        "before = json.loads(Path('owner-inputs.json').read_text())\n"
        "with Botpipe(\n"
        "    workspace,\n"
        "    state_dir=os.environ['BOTPIPE_TEST_STATE'],\n"
        "    provider=FakeProvider([]),\n"
        ") as client:\n"
        "    result = client.resume('source-anchor', workflow=make_root())\n"
        "    assert result.status == 'completed', result.error\n"
        "    assert result.value == Reconciled(value='reconciled')\n"
        "    operations = client.journal.operations('source-anchor')\n"
        "    assert [item['inputs'] for item in operations] == before\n"
        "    expected = (workspace / 'childpkg', workspace / 'helperpkg')\n"
        "    for operation in operations:\n"
        "        assert codec.recorded_source_boundaries(\n"
        "            operation['inputs'], root_boundary=workspace\n"
        "        ) == expected\n"
    )

    first = _run(start, original, state)
    assert first.returncode == 0, first.stdout + first.stderr
    reconciled = _run(resolve, original, state)
    assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr

    shutil.copytree(original, relocated)
    shutil.rmtree(original)
    resume = _write(relocated / "resume.py", resume_source)
    replayed = _run(resume, relocated, state)
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
