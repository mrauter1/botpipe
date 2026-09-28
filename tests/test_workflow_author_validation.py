"""Candidate validation, subprocess feedback, and replay evidence integrity."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe, current_run, workflow
from botpipe.workflows.workflow_author.validation import (
    Validation, prepare_candidate, validate_candidate, verify_candidate,
)


def _project(root: Path, name: str = "demo") -> str:
    package = root / ".botpipe" / "workflows" / name
    package.mkdir(parents=True)
    (package / "workflow.toml").write_text(f'name = "{name}"\nfunction = "echo"\n')
    (package / "flow.py").write_text(
        "from botpipe import workflow\n@workflow\ndef echo(request: str) -> str:\n    return request\n"
    )
    test = root / "tests" / "runtime" / f"test_{name}.py"
    test.parent.mkdir(parents=True)
    test.write_text(
        "from pathlib import Path\n"
        "from botpipe import Botpipe\n"
        "from botpipe.discovery import resolve_workflow\n"
        "from botpipe.providers import FakeProvider\n"
        "def test_real_run(tmp_path):\n"
        f"    fn = resolve_workflow('.botpipe/workflows/{name}/flow.py:echo', Path.cwd())\n"
        "    with Botpipe(tmp_path, provider=FakeProvider([])) as client:\n"
        "        result = client.run(fn, request='hello')\n"
        "        assert result.ok, result.error\n"
        "        assert result.value == 'hello'\n"
    )
    return f".botpipe/workflows/{name}/flow.py:echo"


def _check(root: Path, reference: str, *, name="demo") -> Validation:
    return validate_candidate.__wrapped__(str(root), name, reference, str(root.parent / "test transcript.md"))


def test_real_run_transcript_and_mutation_rejection(tmp_path):
    root = tmp_path / "candidate with spaces"
    reference = _project(root)
    (root / "unrelated_fixture.py").write_text("not valid Python ")
    result = _check(root, reference)
    assert result.success, result.errors
    assert "## tests/runtime/test_demo.py" in Path(result.transcript).read_text()
    assert "hello" in result.output or "1 passed" in result.output
    verify_candidate(str(root), result)
    (root / ".botpipe/workflows/demo/flow.py").write_text("def echo(): return 42\n")
    with pytest.raises(ValueError, match="changed"):
        verify_candidate(str(root), result)


@pytest.mark.parametrize("mutation", ["deleted", "added", "transcript"])
def test_fresh_evidence_detects_deleted_added_and_rewritten_files(tmp_path, mutation):
    root = tmp_path / "candidate"
    reference = _project(root)
    result = _check(root, reference)
    assert result.success, result.errors
    if mutation == "deleted":
        (root / "tests/runtime/test_demo.py").unlink()
    elif mutation == "added":
        (root / ".botpipe/workflows/demo/extra.py").write_text("x = 1\n")
    else:
        Path(result.transcript).write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        verify_candidate(str(root), result)


def test_bad_catalog_reference_import_and_empty_failure(tmp_path):
    root = tmp_path / "candidate"
    reference = _project(root)
    (root / ".botpipe/workflows/demo/workflow.toml").write_text("broken = [")
    result = _check(root, reference)
    assert not result.success and "workflow.toml" in " ".join(result.errors)
    (root / ".botpipe/workflows/demo/workflow.toml").write_text('name = "demo"\nfunction = "echo"\n')
    result = _check(root, ".botpipe/workflows/other/flow.py:echo")
    assert not result.success and "reference" in " ".join(result.errors)
    (root / ".botpipe/workflows/demo/flow.py").write_text("raise RuntimeError('broken import')\n")
    result = _check(root, reference)
    assert not result.success and "broken import" in " ".join(result.errors)


def test_plain_callable_cannot_ship_as_workflow(tmp_path):
    root = tmp_path / "candidate"
    reference = _project(root)
    (root / ".botpipe/workflows/demo/flow.py").write_text("def echo(request): return request\n")
    result = _check(root, reference)
    assert not result.success
    assert "not a Botpipe @workflow" in " ".join(result.errors)


def test_process_timeout_and_nonzero_empty_output_are_failures(tmp_path, monkeypatch):
    root = tmp_path / "candidate"
    reference = _project(root)
    from botpipe.workflows.workflow_author import validation as module
    real = module._run

    def failure(argv, cwd, env, timeout):
        result = real(argv, cwd, env, timeout)
        return result.__class__(result.argv, 7, False, False, result.elapsed_seconds, "", "", False, False)

    monkeypatch.setattr(module, "_run", failure)
    result = _check(root, reference)
    assert not result.success and "exited 7" in " ".join(result.errors)
    monkeypatch.setattr(module, "_run", lambda argv, cwd, env, timeout: real([sys.executable, "-c", "import time; time.sleep(.1)"], cwd, env, .01))
    result = _check(root, reference)
    assert not result.success and "timed out" in " ".join(result.errors)


def test_test_mutating_source_invalidates_its_own_evidence(tmp_path):
    root = tmp_path / "candidate"
    reference = _project(root)
    test = root / "tests/runtime/test_demo.py"
    test.write_text(test.read_text() + "\ndef test_mutation():\n    from pathlib import Path\n    Path('side_effect.py').write_text('changed')\n")
    result = _check(root, reference)
    assert not result.success
    assert "changed during validation" in " ".join(result.errors)


def test_prepare_copies_project_and_refuses_existing_target(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "settings.py").write_text("VALUE = 1\n")
    (source / ".git").mkdir()
    (source / ".git" / "secret").write_text("internal")
    other = source / ".botpipe" / "workflows" / "existing"
    other.mkdir(parents=True)
    (other / "flow.py").write_text("def existing(): pass\n")

    @workflow
    def prepare():
        return prepare_candidate(str(source), str(current_run().folder / "candidate"), "new")

    (tmp_path / "runtime").mkdir()
    with Botpipe(tmp_path / "runtime") as client:
        run = client.run(prepare)
    assert run.ok, run.error
    candidate = Path(run.value)
    assert (candidate / "settings.py").read_text() == "VALUE = 1\n"
    assert (candidate / ".botpipe/workflows/existing/flow.py").is_file()
    assert not (candidate / ".git").exists()
    (candidate / "settings.py").write_text("VALUE = 2\n")
    assert (source / "settings.py").read_text() == "VALUE = 1\n"
    _project(source, "new")
    (tmp_path / "another").mkdir()
    with Botpipe(tmp_path / "another") as client:
        collision = client.run(prepare)
    assert not collision.ok and "already exists" in str(collision.error)


def test_prepare_recovers_partial_run_owned_copy_and_excludes_worktree_git_file(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").write_text("gitdir: /some/external/worktree\n")
    (source / "runs").mkdir()
    (source / "runs" / "application.py").write_text("VALUE = 1\n")

    @workflow
    def prepare():
        target = current_run().folder / "candidate"
        target.mkdir()
        (target / "partial").write_text("from interrupted copy")
        return prepare_candidate(str(source), str(target), "new")

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with Botpipe(runtime) as client:
        result = client.run(prepare)
    assert result.ok, result.error
    copied = Path(result.value)
    assert not (copied / "partial").exists()
    assert not (copied / ".git").exists()
    assert (copied / "runs" / "application.py").read_text() == "VALUE = 1\n"


def test_cli_arguments_with_spaces(tmp_path):
    root = tmp_path / "candidate with spaces"
    _project(root)
    transcript = tmp_path / "evidence with spaces.md"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run([sys.executable, "-m", "botpipe.workflows.workflow_author.validation", "demo", "--transcript", str(transcript)], cwd=root, env=env, text=True, capture_output=True, timeout=150)
    assert process.returncode == 0, process.stderr + process.stdout
    assert "## tests/runtime/test_demo.py" in transcript.read_text()


def test_cli_internal_run_transcript_and_source_path_guard(tmp_path):
    root = tmp_path / "candidate"
    _project(root)
    transcript = root / ".botpipe" / "transcripts" / "round-1.md"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run([sys.executable, "-m", "botpipe.workflows.workflow_author.validation", "demo", "--transcript", str(transcript)], cwd=root, env=env, text=True, capture_output=True, timeout=150)
    assert process.returncode == 0, process.stderr + process.stdout
    assert "## tests/runtime/test_demo.py" in transcript.read_text()
    with pytest.raises(ValueError, match="internal transcript"):
        validate_candidate.__wrapped__(str(root), "demo", ".botpipe/workflows/demo/flow.py:echo", str(root / ".botpipe/workflows/demo/flow.py"))
