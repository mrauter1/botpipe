"""Behavioral coverage for the packaged, bounded workflow author."""

from __future__ import annotations

import importlib
import importlib.abc
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.policy import SandboxMode
from botpipe.providers import FakeProvider
from botpipe.workflows.workflow_author import Params, WorkflowAuthorResult, workflow_author
from botpipe.workflows.workflow_author.guidance import load_authoring_guidance


def _input(request):
    return json.JSONDecoder().raw_decode(request.prompt.split("\n\nInput:\n", 1)[1])[0]


def _brief(*, questions=()):
    return {
        "purpose": "Echo a text request to the caller.",
        "definitions": ["Text is the caller's supplied request."],
        "gates": ["Ask only if the input type is unclear."],
        "scenarios": ["Given text, when run, then return that text; replay preserves it."],
        "questions": list(questions),
    }


def _write_package(request, *, failing=False):
    name = _input(request)["parameters"]["package_name"]
    root = Path(request.workspace)
    package = root / ".botpipe" / "workflows" / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "flow.py").write_text(
        "from botpipe import workflow\n"
        f'@workflow(name="{name}")\n'
        "def GeneratedWorkflow(request: str = '') -> str:\n"
        "    return request\n",
        encoding="utf-8",
    )
    (package / "workflow.toml").write_text(
        f'name = "{name}"\nfunction = "GeneratedWorkflow"\n', encoding="utf-8"
    )
    test = root / "tests" / "runtime" / f"test_{name}.py"
    test.parent.mkdir(parents=True, exist_ok=True)
    expected = "incorrect outcome" if failing else "authored outcome"
    test.write_text(
        "from pathlib import Path\n"
        "from botpipe import Botpipe\n"
        "from botpipe.discovery import resolve_workflow\n"
        "from botpipe.providers import FakeProvider\n\n"
        "def test_outcome_and_replay(tmp_path):\n"
        f"    fn = resolve_workflow('.botpipe/workflows/{name}/flow.py:GeneratedWorkflow', Path.cwd())\n"
        "    with Botpipe(tmp_path, provider=FakeProvider([])) as client:\n"
        "        first = client.run(fn, request='authored outcome')\n"
        "        assert first.ok, first.error\n"
        f"        assert first.value == {expected!r}\n"
        "        resumed = client.resume(first.run_id, workflow=fn)\n"
        "        assert resumed.ok, resumed.error\n"
        "        assert resumed.value == first.value\n",
        encoding="utf-8",
    )
    return f".botpipe/workflows/{name}/flow.py:GeneratedWorkflow"


def _answer(request):
    if request.preset == "query":
        return {"ship": True, "findings": []}
    if "Write the brief" in request.prompt:
        return _brief()
    return {"reference": _write_package(request), "notes": "Echo and replay tested."}


def test_author_is_discoverable_without_labs_and_guides_match_sources(tmp_path):
    entries = discover_workflows(tmp_path, include_labs=False)
    assert any(entry.name == "workflow_author" for entry in entries)
    assert resolve_workflow("workflow-author", tmp_path) is workflow_author
    guidance = load_authoring_guidance.__wrapped__()
    for name in ("authoring.md", "prompting.md"):
        assert Path("docs", name).read_text(encoding="utf-8") in guidance


def test_author_runs_when_labs_cannot_be_imported(tmp_path):
    class BlockLabs(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "labs" or fullname.startswith("labs."):
                raise ModuleNotFoundError("labs disabled")

    loaded_labs = {name: module for name, module in sys.modules.items() if name.startswith("labs")}
    for name in loaded_labs:
        sys.modules.pop(name)
    blocker = BlockLabs()
    sys.meta_path.insert(0, blocker)
    try:
        run = Botpipe(tmp_path, provider=FakeProvider([_answer] * 4)).run(
            workflow_author, Params(package_name="without_labs"), request="Echo the request."
        )
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(loaded_labs)
    assert run.ok, run.error
    assert run.value.shipped and run.value.validation.success


def test_author_builds_in_project_copy_and_replays_without_model_calls(tmp_path):
    original = tmp_path / "README.md"
    original.write_text("Keep this project context.\n", encoding="utf-8")
    unrelated = tmp_path / "tests" / "runtime" / "test_previous.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("def test_unrelated(): assert False, 'unrelated failure'\n")
    provider = FakeProvider([_answer] * 4)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(workflow_author, Params(package_name="echo"), request="Echo the request.")
        assert run.ok, run.error
        result = run.value
        assert isinstance(result, WorkflowAuthorResult)
        assert result.shipped and result.rounds == 1 and result.findings == []
        assert result.reference == ".botpipe/workflows/echo/flow.py:GeneratedWorkflow"
        assert result.validation.success and result.validation.reference == result.reference
        assert "1 passed" in result.validation.output
        assert "unrelated failure" not in result.validation.output
        assert Path(result.validation.transcript).is_file()
        assert (Path(result.candidate_root) / "README.md").read_text() == original.read_text()
        assert (Path(result.candidate_root) / result.reference.split(":")[0]).is_file()
        assert original.read_text() == "Keep this project context.\n"
        assert unrelated.is_file() and not (tmp_path / result.reference.split(":")[0]).exists()
        assert WorkflowAuthorResult.model_validate_json(result.model_dump_json()) == result
        run_calls = [call for call in provider.calls if call.preset == "run"]
        review_calls = [call for call in provider.calls if call.preset == "query"]
        assert len(run_calls) == 2 and len(review_calls) == 1
        assert run_calls[0].session_key == run_calls[1].session_key
        assert review_calls[0].session_key != run_calls[0].session_key
        for call in provider.calls:
            assert call.instructions == load_authoring_guidance.__wrapped__()
            assert call.workspace == Path(result.candidate_root)
            if call.preset == "run":
                assert call.policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
        count = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        assert replayed.ok, replayed.error
        assert replayed.value == result and len(provider.calls) == count


def test_failed_generated_test_feeds_exact_failure_to_same_author_then_repairs(tmp_path):
    builds = []

    def answer(request):
        if request.preset == "query" or "Write the brief" in request.prompt:
            return _answer(request)
        builds.append(request)
        return {"reference": _write_package(request, failing=len(builds) == 1)}

    run = Botpipe(tmp_path, provider=FakeProvider([answer] * 6)).run(
        workflow_author, Params(package_name="repair", max_rounds=2), request="Echo the request."
    )
    assert run.ok, run.error
    assert run.value.shipped and run.value.rounds == 2
    assert len(builds) == 2 and builds[0].session_key == builds[1].session_key
    assert "generated test" in " ".join(_input(builds[1])["feedback"])
    assert "AssertionError" in " ".join(_input(builds[1])["feedback"])
    assert builds[0].workspace == builds[1].workspace == Path(run.value.candidate_root)


def test_interrupted_handoff_rejects_modified_cached_candidate(tmp_path, monkeypatch):
    module = importlib.import_module("botpipe.workflows.workflow_author.workflow")
    original_verify = module.verify_candidate
    count = 0

    def interrupt_once(root, validation):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("handoff interrupted")
        return original_verify(root, validation)

    monkeypatch.setattr(module, "verify_candidate", interrupt_once)
    provider = FakeProvider([_answer] * 4)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(workflow_author, Params(package_name="immutable"))
        assert run.status == "failed" and "handoff interrupted" in str(run.error)
        # Obtain the run-owned candidate from the provider handoff, without relying on run-folder names.
        candidate = Path(provider.calls[1].workspace)
        (candidate / ".botpipe/workflows/immutable/flow.py").write_text("# changed after validation\n")
        prior_calls = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        assert replayed.status == "failed"
        assert "changed since validation" in str(replayed.error)
        assert len(provider.calls) == prior_calls and count == 2


def test_parameter_boundaries_and_budget_persist_across_resume(tmp_path):
    params = Params(package_name="example", target_test_argv=[sys.executable, "-c", "pass"])
    assert Params.model_validate_json(params.model_dump_json()) == params
    for argv in ([], [""], ["python", " "]):
        with pytest.raises(ValidationError):
            Params(package_name="example", target_test_argv=argv)
    with pytest.raises(ValidationError):
        Params(package_name="../outside")
    provider = FakeProvider([_answer] * 3)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(workflow_author, Params(package_name="bounded", max_provider_turns=2))
        assert run.status == "budget_exceeded"
        count = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        assert replayed.status == "budget_exceeded" and len(provider.calls) == count
