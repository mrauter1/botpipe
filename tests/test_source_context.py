"""End-to-end regressions for application source-context selection."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]


def test_source_context_resolves_shared_source_once_per_calculation(monkeypatch):
    from botpipe import provenance
    from botpipe._callables import describe_callable

    def leaf():
        return 1

    current = leaf
    for _ in range(16):

        def branch(left=current, right=current):
            return left() + right()

        current = branch
    graph = describe_callable(current)
    resolved = []
    canonical = provenance._canonical_source_path

    def counted(path, **kwargs):
        resolved.append(path)
        return canonical(path, **kwargs)

    monkeypatch.setattr(provenance, "_canonical_source_path", counted)
    context = provenance.source_context(current, graph=graph)
    assert context.origin_source == Path(__file__).resolve()
    assert len(context.owned_boundaries) == 1
    assert len(resolved) == 1
    assert provenance.source_context(current, graph=graph) == context
    assert len(resolved) == 2


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def _package(root: Path, name: str) -> Path:
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    return package


def _run(
    script: Path,
    *,
    source_root: Path | None = None,
    workspace: Path | None = None,
    args: tuple[str, ...] = (),
    sdk_root: Path = SDK_ROOT,
) -> subprocess.CompletedProcess[str]:
    source_root = source_root or script.parent
    entries = (str(sdk_root), str(source_root), os.environ.get("PYTHONPATH", ""))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, entries))}
    if workspace is not None:
        env["BOTPIPE_TEST_WORKSPACE"] = str(workspace)
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=source_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("default_kind", ["positional", "keyword"])
def test_owned_callable_default_uses_current_dependency_after_answer(
    tmp_path: Path, default_kind: str
) -> None:
    branch = _package(tmp_path, "branchpkg")
    _write(
        branch / "model.py",
        "class Config:\n    def value(self): return 'old'\n",
    )
    _write(
        branch / "helper.py",
        "from dataclasses import dataclass\n"
        "from .model import Config\n"
        "@dataclass\n"
        "class Helper:\n"
        "    label: str = 'unchanged state'\n"
        "    def __call__(self): return Config().value()\n",
    )
    root = _package(tmp_path, "rootpkg")
    declaration = (
        "def job(callback=Helper()):\n"
        if default_kind == "positional"
        else "def job(*, callback=Helper()):\n"
    )
    _write(
        root / "workflow.py",
        "from botpipe import ask, workflow\n"
        "from branchpkg.helper import Helper\n"
        "@workflow\n"
        f"{declaration}"
        "    before = callback()\n"
        "    answer = ask('continue?')\n"
        "    return before, answer\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='owned-default')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert len(client.journal.operations(result.run_id)) == 1\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('owned-default', workflow=job, answer='yes')\n"
        "    assert result.ok and result.value == ('changed', 'yes'), result.error\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stdout + first.stderr
    model = branch / "model.py"
    model.write_text(model.read_text().replace("'old'", "'changed'"))
    rejected = _run(resume)
    assert rejected.returncode == 0, rejected.stdout + rejected.stderr


def test_raw_partial_branch_keeps_application_manifest_and_rejects_model_edit(
    tmp_path: Path,
) -> None:
    application = _package(tmp_path, "application")
    model = _write(
        application / "model.py",
        "class Config:\n    def value(self): return 'old'\n",
    )
    _write(
        application / "branch.py",
        "from functools import partial\n"
        "from _io import FileIO\n"
        "from .model import Config\n"
        "class Runner:\n"
        "    def run(self, callback): return Config().value(), callback.__name__\n"
        "branch = partial(Runner().run, FileIO)\n",
    )
    root = _package(tmp_path, "rootpkg")
    _write(
        root / "workflow.py",
        "from botpipe import ask, parallel, workflow\n"
        "from application.branch import branch\n"
        "@workflow\n"
        "def job():\n"
        "    result = parallel(branch)\n"
        "    ask('continue?')\n"
        "    return result\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from botpipe.runtime import Workflow\n"
        "from application.branch import branch\n"
        "from rootpkg.workflow import job\n"
        "manifest = Workflow(branch)._orchestration_sources_at_definition\n"
        "assert manifest is not None, manifest\n"
        "assert set(manifest['files']) == {'branch.py', 'model.py'}, manifest\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.run(job, run_id='raw-partial')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert len(client.journal.operations(result.run_id)) == 2\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from rootpkg.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('raw-partial', workflow=job, answer='yes')\n"
        "    assert result.ok and result.value == [('old', 'FileIO')], result.error\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stdout + first.stderr
    model.write_text(model.read_text().replace("'old'", "'changed'"))
    rejected = _run(resume)
    assert rejected.returncode == 0, rejected.stdout + rejected.stderr


def test_imported_wraps_uses_application_prompt_and_wrapper_source_is_verified(
    tmp_path: Path,
) -> None:
    helper = _package(tmp_path, "helperpkg")
    decorator = _write(
        helper / "decorators.py",
        "from functools import wraps\n"
        "def traced(fn):\n"
        "    @wraps(fn)\n"
        "    def wrapped(*args, **kwargs):\n"
        "        return fn(*args, **kwargs)\n"
        "    return wrapped\n",
    )
    (helper / "prompt.md").write_text("wrong helper prompt")
    application = _package(tmp_path, "application")
    (application / "prompt.md").write_text("application prompt")
    _write(
        application / "workflow.py",
        "from botpipe import Policy, Prompt, Session, ask, workflow\n"
        "from helperpkg.decorators import traced\n"
        "@workflow\n"
        "@traced\n"
        "def job():\n"
        "    value = Session().run(\n"
        "        Prompt.file('prompt.md'),\n"
        "        policy=Policy(sandbox_mode='read_only'),\n"
        "    ).value\n"
        "    ask('continue?')\n"
        "    return value\n",
    )
    start = _write(
        tmp_path / "start.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        "manifest = job._orchestration_sources_at_definition\n"
        "assert manifest is not None, manifest\n"
        "assert set(manifest['files']) >= {\n"
        "    'application/workflow.py', 'helperpkg/decorators.py'\n"
        "}, manifest\n"
        "provider = FakeProvider(['done'])\n"
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job, run_id='wrapped')\n"
        "    assert result.status == 'awaiting_input', result.error\n"
        "    assert provider.calls[0].prompt == 'application prompt'\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        "with Botpipe('.', provider=FakeProvider([])) as client:\n"
        "    result = client.resume('wrapped', workflow=job, answer='yes')\n"
        "    assert result.ok and result.value == 'done', result.error\n",
    )

    first = _run(start)
    assert first.returncode == 0, first.stdout + first.stderr
    decorator.write_text(
        decorator.read_text().replace(
            "        return fn(*args, **kwargs)\n",
            "        result = fn(*args, **kwargs)\n        return result\n",
        )
    )
    rejected = _run(resume)
    assert rejected.returncode == 0, rejected.stdout + rejected.stderr


def test_sdk_activity_wrapper_retains_application_activity_source(
    tmp_path: Path,
) -> None:
    activities = _package(tmp_path, "activitypkg")
    _write(
        activities / "tasks.py",
        "from botpipe import activity\n@activity\ndef answer(): return 'done'\n",
    )
    application = _package(tmp_path, "application")
    _write(
        application / "workflow.py",
        "from botpipe import workflow\n"
        "from activitypkg.tasks import answer\n"
        "@workflow\n"
        "def job(): return answer()\n",
    )
    check = _write(
        tmp_path / "check.py",
        "from application.workflow import job\n"
        "manifest = job._orchestration_sources_at_definition\n"
        "assert manifest is not None, manifest\n"
        "assert set(manifest['files']) >= {\n"
        "    'application/workflow.py', 'activitypkg/tasks.py'\n"
        "}, manifest\n",
    )

    completed = _run(check)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_missing_loaded_helper_does_not_erase_application_resource_origin(
    tmp_path: Path,
) -> None:
    helper = _package(tmp_path, "helperpkg")
    helper_source = _write(
        helper / "tasks.py",
        "def loaded_helper(): return 'loaded'\n",
    )
    application = _package(tmp_path, "application")
    (application / "prompt.md").write_text("application prompt")
    _write(
        application / "workflow.py",
        "from botpipe import Policy, Prompt, Session\n"
        "from helperpkg.tasks import loaded_helper\n"
        "def job():\n"
        "    loaded_helper()\n"
        "    return Session().run(\n"
        "        Prompt.file('prompt.md'),\n"
        "        policy=Policy(sandbox_mode='read_only'),\n"
        "    ).value\n",
    )
    run = _write(
        tmp_path / "missing-helper.py",
        "from pathlib import Path\n"
        "from botpipe import Botpipe, workflow\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job as function\n"
        f"Path({str(helper_source)!r}).unlink()\n"
        "job = workflow(function)\n"
        "assert job._source_context.origin_source == (\n"
        "    Path('application/workflow.py').resolve()\n"
        ")\n"
        "assert job._orchestration_sources_at_definition is None\n"
        "provider = FakeProvider(['done'])\n"
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job)\n"
        "    assert result.ok and result.value == 'done', result.error\n"
        "    assert provider.calls[0].prompt == 'application prompt'\n",
    )

    completed = _run(run)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_wrapped_application_with_owned_default_relocates(tmp_path: Path) -> None:
    first_root = tmp_path / "code-one"
    second_root = tmp_path / "code-two"
    workspace = tmp_path / "state"
    workspace.mkdir()

    helper = _package(first_root, "helperpkg")
    _write(
        helper / "decorators.py",
        "from functools import wraps\n"
        "def traced(fn):\n"
        "    @wraps(fn)\n"
        "    def wrapped(*args, **kwargs): return fn(*args, **kwargs)\n"
        "    return wrapped\n",
    )
    branch = _package(first_root, "branchpkg")
    _write(
        branch / "helper.py",
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Helper:\n"
        "    label: str = 'owned'\n"
        "    def __call__(self): return self.label\n",
    )
    application = _package(first_root, "application")
    _write(
        application / "workflow.py",
        "from botpipe import ask, workflow\n"
        "from branchpkg.helper import Helper\n"
        "from helperpkg.decorators import traced\n"
        "@workflow\n"
        "@traced\n"
        "def job(callback=Helper()):\n"
        "    ask('continue?')\n"
        "    return callback()\n",
    )
    script = _write(
        first_root / "run.py",
        "import os, sys\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        "with Botpipe(os.environ['BOTPIPE_TEST_WORKSPACE'], provider=FakeProvider([])) as client:\n"
        "    if sys.argv[-1:] == ['resume']:\n"
        "        result = client.resume('relocated', workflow=job, answer='yes')\n"
        "        assert result.ok and result.value == 'owned', result.error\n"
        "    else:\n"
        "        result = client.run(job, run_id='relocated')\n"
        "        assert result.status == 'awaiting_input', result.error\n",
    )

    first = _run(script, source_root=first_root, workspace=workspace)
    assert first.returncode == 0, first.stdout + first.stderr
    shutil.copytree(first_root, second_root)
    shutil.rmtree(first_root)
    relocated = _run(
        second_root / "run.py",
        source_root=second_root,
        workspace=workspace,
        args=("resume",),
    )
    assert relocated.returncode == 0, relocated.stdout + relocated.stderr


def test_sdk_partial_branch_inherits_application_prompt(tmp_path: Path) -> None:
    application = _package(tmp_path, "application")
    (application / "prompt.md").write_text("application prompt")
    (tmp_path / "prompt.md").write_text("wrong workspace prompt")
    _write(
        application / "workflow.py",
        "from functools import partial\n"
        "from botpipe import Policy, Prompt, Session, parallel, workflow\n"
        "@workflow\n"
        "def job():\n"
        "    callback = partial(\n"
        "        Session().run,\n"
        "        Prompt.file('prompt.md'),\n"
        "        policy=Policy(sandbox_mode='read_only'),\n"
        "    )\n"
        "    return parallel(callback)[0].value\n",
    )
    run = _write(
        tmp_path / "run.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        "provider = FakeProvider(['done'])\n"
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job, run_id='sdk-partial')\n"
        "    assert result.ok and result.value == 'done', result.error\n"
        "    assert provider.calls[0].prompt == 'application prompt'\n"
        "    replay = client.resume(result.run_id, workflow=job)\n"
        "    assert replay.ok and replay.value == 'done', replay.error\n"
        "    assert len(provider.calls) == 1\n",
    )

    completed = _run(run)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_symlinked_sdk_partial_branch_inherits_application_prompt(
    tmp_path: Path,
) -> None:
    sdk_link = tmp_path / "sdk-link"
    try:
        sdk_link.symlink_to(SDK_ROOT, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    application = _package(tmp_path, "application")
    (application / "prompt.md").write_text("application prompt")
    _write(
        application / "workflow.py",
        "from functools import partial\n"
        "from botpipe import Policy, Prompt, Session, parallel, workflow\n"
        "@workflow\n"
        "def job():\n"
        "    callback = partial(\n"
        "        Session().run,\n"
        "        Prompt.file('prompt.md'),\n"
        "        policy=Policy(sandbox_mode='read_only'),\n"
        "    )\n"
        "    return parallel(callback)[0].value\n",
    )
    run = _write(
        tmp_path / "run-symlinked.py",
        "from pathlib import Path\n"
        "import botpipe\n"
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        f"sdk_link = Path({str(sdk_link)!r}).absolute()\n"
        "assert Path(botpipe.__file__).absolute().is_relative_to(sdk_link)\n"
        "provider = FakeProvider(['done'])\n"
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job, run_id='symlinked-sdk')\n"
        "    assert result.ok and result.value == 'done', result.error\n"
        "    assert provider.calls[0].prompt == 'application prompt'\n",
    )

    completed = _run(run, sdk_root=sdk_link)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_sdk_partial_application_contract_adds_owner_without_stealing_prompt_origin(
    tmp_path: Path,
) -> None:
    contract = _package(tmp_path, "contractpkg")
    _write(
        contract / "model.py",
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Answer:\n"
        "    value: str\n",
    )
    (contract / "prompt.md").write_text("wrong contract prompt")
    application = _package(tmp_path, "application")
    (application / "prompt.md").write_text("application prompt")
    (tmp_path / "prompt.md").write_text("wrong workspace prompt")
    _write(
        application / "workflow.py",
        "from functools import partial\n"
        "from pathlib import Path\n"
        "from botpipe import Policy, Prompt, Session, parallel, workflow\n"
        "from botpipe.runtime import Workflow\n"
        "from contractpkg.model import Answer\n"
        "@workflow\n"
        "def job():\n"
        "    callback = partial(\n"
        "        Session().run,\n"
        "        Prompt.file('prompt.md'),\n"
        "        returns=Answer,\n"
        "        policy=Policy(sandbox_mode='read_only'),\n"
        "    )\n"
        "    context = Workflow(callback)._source_context\n"
        "    assert context.origin_source is None, context\n"
        "    assert context.origin_boundary is None, context\n"
        "    expected_owner = Path(__file__).resolve().parents[1] / 'contractpkg'\n"
        "    assert expected_owner in context.owned_boundaries, context\n"
        "    return parallel(callback)[0].value\n",
    )
    run = _write(
        tmp_path / "run.py",
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        'provider = FakeProvider([\'{"value": "done"}\'])\n'
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job, run_id='sdk-partial-contract')\n"
        "    assert result.ok, result.error\n"
        "    assert result.value.value == 'done'\n"
        "    assert type(result.value).__module__ == 'contractpkg.model'\n"
        "    prompt = provider.calls[0].prompt\n"
        "    assert prompt.startswith(\n"
        "        'application prompt\\n\\nReturn only JSON matching this schema:'\n"
        "    ), prompt\n"
        "    assert 'wrong contract prompt' not in prompt, prompt\n"
        "    assert 'wrong workspace prompt' not in prompt, prompt\n"
        "    replay = client.resume(result.run_id, workflow=job)\n"
        "    assert replay.ok, replay.error\n"
        "    assert replay.value.value == 'done'\n"
        "    assert type(replay.value).__module__ == 'contractpkg.model'\n"
        "    assert len(provider.calls) == 1\n",
    )

    completed = _run(run)
    assert completed.returncode == 0, completed.stdout + completed.stderr
