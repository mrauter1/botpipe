"""Exercise the packaged author through real materialization, tests and replay."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.policy import SandboxMode
from botpipe.providers import FakeProvider
from botpipe.workflows.workflow_author import (
    Params,
    WorkflowAuthorResult,
    workflow_author,
)
from labs.workflows.workflow_idea_to_workflow_package.guidance import (
    load_authoring_guidance,
)
from tests.test_labs import _successful_provider


def _input(request):
    return json.JSONDecoder().raw_decode(request.prompt.split("\n\nInput:\n", 1)[1])[0]


def _answer(request, *, broken_test=False):
    result = _successful_provider(request)
    if "workflow_package_manifest" in request.artifacts:
        manifest_path = request.artifacts["workflow_package_manifest"]
        manifest = json.loads(manifest_path.read_text())
        name = manifest["package_name"]
        expected = "wrong" if broken_test else "authored outcome"
        manifest["files"].append(
            {
                "path": f"tests/runtime/test_{name}.py",
                "content": (
                    "from pathlib import Path\n"
                    "from botpipe import Botpipe\n"
                    "from botpipe.discovery import resolve_workflow\n"
                    "from botpipe.providers import FakeProvider\n\n"
                    "def test_outcome_and_replay(tmp_path):\n"
                    f"    fn = resolve_workflow({manifest['workflow_reference']!r}, Path.cwd())\n"
                    "    with Botpipe(tmp_path, provider=FakeProvider([])) as client:\n"
                    "        first = client.run(fn, request='authored outcome')\n"
                    "        assert first.ok, first.error\n"
                    f"        assert first.value == {expected!r}\n"
                    "        resumed = client.resume(first.run_id, workflow=fn)\n"
                    "        assert resumed.ok, resumed.error\n"
                    "        assert resumed.value == first.value\n"
                ),
            }
        )
        manifest_path.write_text(json.dumps(manifest))
    return result


def test_author_is_discoverable_without_labs_and_guides_match_sources(tmp_path):
    entries = discover_workflows(tmp_path, include_labs=False)
    assert any(entry.name == "workflow_author" for entry in entries)
    assert resolve_workflow("workflow-author", tmp_path) is workflow_author
    guidance = load_authoring_guidance.__wrapped__()
    for name in ("authoring.md", "prompting.md"):
        source = Path("docs", name).read_text(encoding="utf-8")
        assert source in guidance


def test_author_builds_tests_and_returns_runtime_evidence_from_empty_workspace(
    tmp_path,
):
    provider = FakeProvider([_answer] * 6)
    expected_guidance = load_authoring_guidance.__wrapped__()
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            workflow_author, Params(package_name="echo"), request="Echo the request."
        )
        assert run.ok, run.error
        result = run.value
        assert isinstance(result, WorkflowAuthorResult)
        assert result.workflow_name == "workflow_author"
        assert result.package_name == "echo"
        assert result.surface_boundary["editable_paths"] == []
        assert Path(result.package_path, "flow.py").is_file()
        assert result.validation.success
        assert [check.phase for check in result.validation.checks] == [
            "compile",
            "test",
        ]
        test = result.validation.checks[-1]
        assert test.exit_code == 0
        assert "1 passed" in test.stdout
        assert test.result["python_exit_code"] == 0
        assert (
            result.workflow_reference
            == ".botpipe/workflows/echo/flow.py:GeneratedWorkflow"
        )
        assert result.validation.validated_root == result.candidate_root
        for file in result.files:
            data = (Path(result.candidate_root) / file.path).read_bytes()
            assert hashlib.sha256(data).hexdigest() == file.sha256
            assert len(data) == file.size_bytes
        assert (
            WorkflowAuthorResult.model_validate_json(result.model_dump_json()) == result
        )
        assert not list(tmp_path.iterdir()), (
            "Authoring must not modify the source workspace"
        )
        for call in provider.calls:
            assert call.instructions == expected_guidance
            if call.preset == "run":
                assert call.policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
                assert call.workspace != tmp_path
            else:
                assert call.preset == "query"
                assert call.session_key is None
                assert not call.artifacts
        count = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        assert replayed.ok, replayed.error
        assert replayed.value == result
        assert len(provider.calls) == count


def test_failed_generated_test_returns_exact_feedback_and_repairs(tmp_path):
    builds = []

    def answer(request):
        payload = _input(request)
        if "workflow_package_manifest" in request.artifacts:
            builds.append(payload)
        return _answer(request, broken_test=len(builds) == 1)

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 7)).run(
        workflow_author, Params(package_name="repair"), request="Echo the request."
    )
    assert result.ok, result.error
    assert len(builds) == 2
    rejected = builds[1]["runtime_validation_feedback"]
    assert rejected["candidate_evaluation"]["success"] is False
    assert rejected["candidate_evaluation"]["checks"][-1]["exit_code"] != 0
    assert "AssertionError" in rejected["candidate_evaluation"]["checks"][-1]["stdout"]
    assert rejected["generated_candidate"]["root"] != result.value.candidate_root
    assert result.value.validation.success


def test_author_preserves_existing_runtime_tests_and_runs_only_generated_test(tmp_path):
    existing = tmp_path / "tests/runtime/test_previous_workflow.py"
    existing.parent.mkdir(parents=True)
    original = "def test_existing_failure():\n    assert False, 'unrelated failure'\n"
    existing.write_text(original)
    result = Botpipe(tmp_path, provider=FakeProvider([_answer] * 6)).run(
        workflow_author, Params(package_name="focused")
    )
    assert result.ok, result.error
    check = result.value.validation.checks[-1]
    assert check.phase == "test"
    assert "1 passed" in check.stdout
    assert "unrelated failure" not in check.stdout
    assert existing.read_text() == original
    assert not (existing.parent / "test_focused.py").exists()


@pytest.mark.parametrize("change", [None, "edit", "delete", "add", "anchor"])
def test_interrupted_handoff_rechecks_cached_candidate(tmp_path, monkeypatch, change):
    module = importlib.import_module("botpipe.workflows.workflow_author.workflow")
    derive = module.derive_surface_manifest
    roots = []

    def interrupt_once(root, **kwargs):
        roots.append(root)
        if len(roots) == 1:
            raise RuntimeError("Handoff interrupted after the child completed")
        return derive(root, **kwargs)

    monkeypatch.setattr(module, "derive_surface_manifest", interrupt_once)
    (tmp_path / "README.md").write_text("Original project.\n")
    provider = FakeProvider([_answer] * 6)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(workflow_author, Params(package_name="immutable"))
        assert run.status == "failed"
        assert "Handoff interrupted" in str(run.error)
        [root] = roots
        entry = root / ".botpipe/workflows/immutable/flow.py"
        if change == "edit":
            entry.write_text(entry.read_text() + "\n# changed after review\n")
        elif change == "delete":
            entry.unlink()
        elif change == "add":
            (entry.parent / "unreviewed.py").write_text("UNREVIEWED = True\n")
        elif change == "anchor":
            (root / "README.md").write_text("Changed candidate anchor.\n")
        calls = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        if change is None:
            assert replayed.ok, replayed.error
            assert replayed.value.validation.success
        else:
            assert replayed.status == "failed"
            assert "changed after validation" in str(replayed.error)
        assert len(roots) == 2
        assert len(provider.calls) == calls
        assert (tmp_path / "README.md").read_text() == "Original project.\n"


def test_independent_reviews_rework_design_and_rebuild_source(tmp_path):
    designs = []
    evaluations = []

    def answer(request):
        payload = _input(request)
        phase = payload["phase"]
        if request.artifacts and phase == "design_workflow":
            designs.append(payload)
        if request.artifacts and phase == "evaluate_package":
            evaluations.append(payload)
        result = _answer(request)
        if (
            request.preset == "query"
            and phase == "design_workflow"
            and len(designs) == 1
        ):
            result.update(
                outcome="needs_rework",
                summary="Make the human-input boundary explicit.",
            )
        if (
            request.preset == "query"
            and phase == "evaluate_package"
            and len(evaluations) == 1
        ):
            result.update(
                outcome="needs_replan", summary="The prompt omits required evidence."
            )
        return result

    provider = FakeProvider([answer] * 13)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            workflow_author, Params(package_name="reviewed"), request="Echo."
        )
        assert run.ok, run.error
        assert len(designs) == 3
        assert "human-input boundary" in designs[1]["rework_feedback"]["summary"]
        assert len(evaluations) == 2
        rejected = designs[2]["rejected_candidate_evidence"]
        assert rejected["generated_candidate"] == evaluations[0]["generated_candidate"]
        assert run.value.candidate_root != rejected["generated_candidate"]["root"]
        count = len(provider.calls)
        replayed = client.resume(run.run_id, workflow=workflow_author)
        assert replayed.ok, replayed.error
        assert replayed.value == run.value
        assert len(provider.calls) == count


def test_author_can_pause_before_artifacts_and_resume(tmp_path):
    def question(request):
        assert not list(tmp_path.iterdir())
        return {
            "outcome": "question",
            "summary": "What input should the workflow accept?",
        }

    framing = []

    def answer(request):
        payload = _input(request)
        if payload["phase"] == "frame_request":
            framing.append(payload)
        return _answer(request)

    provider = FakeProvider([question] + [answer] * 6)
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(workflow_author, Params(package_name="clarified"))
        assert paused.status == "awaiting_input"
        resumed = client.resume(paused.run_id, answer="Accept and echo a text request.")
        assert resumed.ok, resumed.error
        assert (
            framing[0]["rework_feedback"]["input_answer"]
            == "Accept and echo a text request."
        )
        assert resumed.value.validation.success


def test_author_budget_covers_the_child_and_stays_exhausted_on_resume(tmp_path):
    provider = FakeProvider([_answer] * 2)
    with Botpipe(tmp_path, provider=provider) as client:
        run = client.run(
            workflow_author, Params(package_name="bounded", max_provider_turns=2)
        )
        assert run.status == "budget_exceeded"
        count = len(provider.calls)
        resumed = client.resume(run.run_id, workflow=workflow_author)
        assert resumed.status == "budget_exceeded"
        assert len(provider.calls) == count


def test_author_test_arguments_are_unambiguous():
    params = Params(package_name="example", target_test_argv=["python", "-m", "pytest"])
    assert Params.model_validate_json(params.model_dump_json()) == params
    default = Params(package_name="example")
    assert Params.model_validate_json(default.model_dump_json()) == default
    assert default.target_test_command is None
    for argv in ([], [""], ["python", " "]):
        with pytest.raises(ValidationError):
            Params(package_name="example", target_test_argv=argv)
    with pytest.raises(ValidationError, match="not both"):
        Params(
            package_name="example",
            target_test_command="pytest",
            target_test_argv=["pytest"],
        )
