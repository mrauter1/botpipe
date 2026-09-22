"""Fresh-process coverage for mutable code and structural state contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import botpipe

SDK_ROOT = Path(botpipe.__file__).resolve().parents[1]


def _package(root: Path, name: str, files: dict[str, str]) -> Path:
    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text("")
    for filename, source in files.items():
        (package / filename).write_text(source)
    return package


def _script(root: Path, name: str, source: str) -> Path:
    path = root / name
    path.write_text(source)
    return path


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(SDK_ROOT), os.environ.get("PYTHONPATH")))
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


def test_pure_nested_workflow_accepts_runtime_subtype_method_edit(tmp_path):
    _package(
        tmp_path,
        "rootpkg",
        {
            "workflow.py": (
                "from pathlib import Path\n"
                "from botpipe import activity, ask_human, workflow\n"
                "from childpkg.workflow import echo\n"
                "@activity\n"
                "def effect():\n"
                "    with Path('effects.log').open('a') as stream:\n"
                "        stream.write('once\\n')\n"
                "@workflow\n"
                "def job(value):\n"
                "    effect()\n"
                "    result = echo(value)\n"
                "    ask_human('continue?')\n"
                "    return result\n"
            )
        },
    )
    child_package = _package(
        tmp_path,
        "childpkg",
        {
            "base.py": (
                "from pydantic import BaseModel\n"
                "class BaseValue(BaseModel): value: int\n"
            ),
            "derived.py": (
                "from .base import BaseValue\n"
                "class DerivedValue(BaseValue):\n"
                "    @property\n"
                "    def adjusted(self): return self.value + 1\n"
            ),
            "workflow.py": (
                "from botpipe import workflow\n"
                "from .base import BaseValue\n"
                "@workflow\n"
                "def echo(value: BaseValue) -> BaseValue:\n"
                "    return value\n"
            ),
        },
    )
    start = _script(
        tmp_path,
        "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from childpkg.derived import DerivedValue\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, DerivedValue(value=3), run_id='nested')\n"
        "    assert result.status == 'awaiting_input', result.error\n",
    )
    resume = _script(
        tmp_path,
        "resume.py",
        'from botpipe import Botpipe\nfrom botpipe.providers import FakeProvider\nfrom rootpkg.workflow import job\nwith Botpipe(\'.\', provider=FakeProvider([])) as client:\n    client.resume(\'nested\', workflow=job, answers={client.pending(\'nested\')[0]["operation_id"]: \'yes\'})\n',
    )
    inspect_completed = _script(
        tmp_path,
        "inspect_pending.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    record = client.inspect('nested')\n"
        "    request = next(\n"
        "        op for op in record['operations'] if op['kind'] == 'input'\n"
        "    )\n"
        "    assert record['run']['status'] == 'completed'\n"
        "    assert request['status'] == 'completed'\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stderr
    derived = child_package / "derived.py"
    derived.write_text(derived.read_text().replace("value + 1", "value + 1000"))

    resumed = _run(resume)
    assert resumed.returncode == 0, resumed.stderr
    inspected = _run(inspect_completed)
    assert inspected.returncode == 0, inspected.stderr
    assert (tmp_path / "effects.log").read_text().splitlines() == ["once"]


def test_nested_runtime_subtype_in_activity_result_accepts_method_edit(
    tmp_path,
):
    package = _package(
        tmp_path,
        "owned",
        {
            "models.py": (
                "from dataclasses import dataclass\n"
                "from pydantic import BaseModel\n"
                "class BaseValue(BaseModel): value: int\n"
                "@dataclass\n"
                "class Envelope:\n"
                "    items: list[BaseValue]\n"
            ),
            "derived.py": (
                "from .models import BaseValue\n"
                "class DerivedValue(BaseValue):\n"
                "    @property\n"
                "    def adjusted(self): return self.value + 1\n"
            ),
            "workflow.py": (
                "import importlib\n"
                "from pathlib import Path\n"
                "from botpipe import activity, ask_human, workflow\n"
                "from .models import Envelope\n"
                "@activity\n"
                "def produce() -> Envelope:\n"
                "    with Path('effects.log').open('a') as stream:\n"
                "        stream.write('produce\\n')\n"
                "    derived = importlib.import_module('owned.derived').DerivedValue\n"
                "    return Envelope(items=[derived(value=4)])\n"
                "@workflow\n"
                "def job():\n"
                "    result = produce()\n"
                "    ask_human('continue?')\n"
                "    return result\n"
            ),
        },
    )
    start = _script(
        tmp_path,
        "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='activity-result')\n"
        "    assert result.status == 'awaiting_input', result.error\n",
    )
    resume = _script(
        tmp_path,
        "resume.py",
        'from botpipe import Botpipe\nfrom botpipe.providers import FakeProvider\nfrom owned.workflow import job\nwith Botpipe(\'.\', provider=FakeProvider([])) as client:\n    client.resume(\'activity-result\', workflow=job, answers={client.pending(\'activity-result\')[0]["operation_id"]: \'yes\'})\n',
    )

    first = _run(start)
    assert first.returncode == 0, first.stderr
    derived = package / "derived.py"
    derived.write_text(derived.read_text().replace("value + 1", "value + 2000"))

    resumed = _run(resume)
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "effects.log").read_text().splitlines() == ["produce"]


@pytest.mark.parametrize("return_annotation", [" -> BaseValue", ""])
def test_manual_typed_activity_resolution_accepts_runtime_subtype_method_edit(
    tmp_path, return_annotation
):
    _package(
        tmp_path,
        "rootpkg",
        {
            "workflow.py": (
                "from botpipe import workflow\n"
                "from childpkg.workflow import recover\n"
                "@workflow\n"
                "def job(): return recover()\n"
            )
        },
    )
    child = _package(
        tmp_path,
        "childpkg",
        {
            "base.py": (
                "from pydantic import BaseModel\n"
                "class BaseValue(BaseModel): value: int\n"
            ),
            "derived.py": (
                "from .base import BaseValue\n"
                "class DerivedValue(BaseValue):\n"
                "    @property\n"
                "    def adjusted(self): return self.value + 1\n"
            ),
            "workflow.py": (
                "from pathlib import Path\n"
                "from botpipe import activity, workflow\n"
                "from .base import BaseValue\n"
                "@activity(retry_safe=False)\n"
                f"def unsafe(){return_annotation}:\n"
                "    with Path('effects.log').open('a') as stream:\n"
                "        stream.write('unsafe\\n')\n"
                "    raise KeyboardInterrupt\n"
                "@workflow\n"
                "def recover(): return unsafe()\n"
            ),
        },
    )
    start = _script(
        tmp_path,
        "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='resolved')\n"
        "    assert result.status == 'interrupted', result.error\n",
    )
    resolve = _script(
        tmp_path,
        "resolve.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from childpkg.derived import DerivedValue\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    record = client.inspect('resolved')\n"
        "    operation = next(\n"
        "        op for op in record['operations'] if op['kind'] == 'activity'\n"
        "    )\n"
        "    client.resolve(\n"
        "        'resolved', operation['id'], response=DerivedValue(value=9)\n"
        "    )\n",
    )
    resume = _script(
        tmp_path,
        "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    client.resume('resolved', workflow=job)\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stderr
    reconciled = _run(resolve)
    assert reconciled.returncode == 0, reconciled.stderr

    derived = child / "derived.py"
    derived.write_text(derived.read_text().replace("value + 1", "value + 3000"))
    resumed = _run(resume)
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "effects.log").read_text().splitlines() == ["unsafe"]


def test_inspection_reads_artifacts_when_owned_result_module_is_unavailable(tmp_path):
    package = _package(
        tmp_path,
        "owned",
        {
            "models.py": (
                "from pydantic import BaseModel\nclass Report(BaseModel): title: str\n"
            ),
            "workflow.py": (
                "from botpipe import Artifact, Provider, workflow\n"
                "from .models import Report\n"
                "@workflow\n"
                "def job():\n"
                "    turn = Provider().run(\n"
                "        'report',\n"
                "        writes=(Artifact.text('report.txt', required=True),),\n"
                "        returns=Report,\n"
                "    )\n"
                "    return turn.value.title\n"
            ),
        },
    )
    start = _script(
        tmp_path,
        "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "def respond(request):\n"
        "    request.artifacts['report'].write_text('artifact body')\n"
        '    return \'{"title": "ready"}\'\n'
        "with Botpipe('.', provider=FakeProvider([respond])) as client:\n"
        "    result = client.run(job, run_id='inspect')\n"
        "    assert result.ok, result.error\n",
    )
    inspect = _script(
        tmp_path,
        "inspect_record.py",
        "import json\n"
        "from botpipe import Botpipe\n"
        "from botpipe.inspection import inspect_run\n"
        "from botpipe.providers import FakeProvider\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    record = inspect_run(client, 'inspect')\n"
        "    assert record['run']['status'] == 'completed'\n"
        "    assert len(record['artifacts']) == 1\n"
        "    artifact = next(iter(record['artifacts'].values()))\n"
        "    assert artifact['name'] == 'report'\n"
        "    assert artifact['digest']\n"
        "    assert record['observed_graph']['nodes']\n"
        "    print(json.dumps(record['artifacts'], sort_keys=True))\n",
    )

    completed = _run(start)
    assert completed.returncode == 0, completed.stderr
    package.rename(tmp_path / "unavailable_owned")

    inspected = _run(inspect)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)
