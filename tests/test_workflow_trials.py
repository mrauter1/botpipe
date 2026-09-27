from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Artifact, Provider, workflow
from botpipe.providers import ProviderPolicyError, ProviderRequest, ProviderResponse
from botpipe.recovery import Stopped, Unknown
from botpipe_optimizer.processes import ProcessResult
from botpipe_optimizer.trial_models import TrialCase, TrialSettings
from botpipe_optimizer.trials import run_trial


class TimedTrialProvider:
    name = "trial-fake"
    supports_timeout = True
    supports_safe_read_retry = True

    def __init__(self, config):
        self.config = dict(config)

    def run(self, request: ProviderRequest) -> ProviderResponse:
        calls = request.workspace / "provider-calls.txt"
        count = int(calls.read_text() if calls.exists() else "0") + 1
        calls.write_text(str(count))
        if self.config.get("unknown_forever"):
            raise RuntimeError("simulated provider with unknown effects")
        if self.config.get("policy_failure"):
            raise ProviderPolicyError("simulated provider policy failure")
        if self.config.get("interrupt_once"):
            marker = request.workspace / "interrupted-once"
            if not marker.exists():
                marker.write_text(str(request.workspace))
                raise RuntimeError("simulated uncertain provider exit")
        if self.config.get("edit_fixture"):
            source = request.workspace / "input.txt"
            source.write_text(source.read_text() + " edited")
        for destination in request.artifacts.values():
            destination.write_text(f"report from call {count}")
        return ProviderResponse(
            f"answer-{count}",
            usage={
                "input_tokens": count,
                "output_tokens": 2,
                "total_tokens": count + 2,
            },
        )

    def recover(self, request: ProviderRequest):
        if self.config.get("unknown_forever"):
            return Unknown("provider outcome remains unknown")
        return Stopped("the injected provider process exited")


def make_trial_provider(config):
    return TimedTrialProvider(config)


@workflow
def fixture_trial():
    before = Path("input.txt").read_text()
    response = Provider().run(
        "produce the report",
        writes=[Artifact.text(Path.cwd() / "report.txt", name="report")],
    )
    return {
        "before": before,
        "after": Path("input.txt").read_text(),
        "answer": response.value,
    }


@workflow
def two_turn_trial():
    return [Provider().run("first").value, Provider().run("second").value]


class TypedInput(BaseModel):
    value: int


@workflow
def typed_trial(payload: TypedInput):
    return {"value": payload.value, "type": type(payload).__name__}


def _run(
    tmp_path: Path,
    case: TrialCase,
    *,
    settings: TrialSettings | None = None,
    provider_config: dict | None = None,
    output_name: str = "output",
    process_runner=None,
):
    root = tmp_path / "frozen-code"
    root.mkdir(exist_ok=True)
    source = root / "test_workflow_trials.py"
    if not source.exists():
        shutil.copy2(__file__, source)
    target = (
        "two_turn_trial"
        if case.case_id == "budget"
        else "typed_trial"
        if case.case_id == "typed"
        else "fixture_trial"
    )
    return run_trial(
        code_root=root,
        workflow_reference=f"test_workflow_trials.py:{target}",
        case=case,
        fixture_root=tmp_path / "fixture" if (tmp_path / "fixture").exists() else None,
        output_root=tmp_path / output_name,
        settings=settings or TrialSettings(timeout_seconds=10, max_elapsed_seconds=30),
        provider_config=provider_config or {},
        provider_factory="test_workflow_trials.py:make_trial_provider",
        process_runner=process_runner,
    )


def test_real_trial_copies_fixture_captures_evidence_and_reuses_completion(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "input.txt").write_text("original")
    (fixture / "input.txt").chmod(0o444)
    case = TrialCase(
        case_id="fixture",
        description="read and edit a fixture",
        workspace="fixture",
        output_paths=["input.txt", "missing.txt"],
    )

    first = _run(tmp_path, case, provider_config={"edit_fixture": True})
    second = _run(tmp_path, case, provider_config={"edit_fixture": True})

    assert first.execution == "complete"
    assert first.outcome == "completed"
    assert first.value == {
        "before": "original",
        "after": "original edited",
        "answer": "answer-1",
    }
    assert first.usage == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
    assert first.provider_budget["used_turns"] == 1
    assert (
        next(
            item["content"]
            for item in first.artifacts
            if item.get("kind") == "text" and item.get("name") == "report"
        )
        == "report from call 1"
    )
    workspace_output = next(
        item for item in first.artifacts if item.get("workspace_path") == "input.txt"
    )
    assert workspace_output["status"] == "modified"
    assert workspace_output["content"] == "original edited"
    assert "-original" in workspace_output["diff"]
    assert "+original edited" in workspace_output["diff"]
    missing_output = next(
        item for item in first.artifacts if item.get("workspace_path") == "missing.txt"
    )
    assert missing_output == {
        "key": "workspace:missing.txt",
        "kind": "workspace_output",
        "workspace_path": "missing.txt",
        "status": "missing",
        "content_missing": True,
    }
    assert any(item["kind"] == "provider" for item in first.operations)
    assert (fixture / "input.txt").read_text() == "original"
    assert (tmp_path / "output/workspace/input.txt").stat().st_mode & stat.S_IWUSR
    assert (tmp_path / "output/workspace/provider-calls.txt").read_text() == "1"
    assert second.run_id == first.run_id
    assert second.value == first.value
    assert second.elapsed_seconds == first.elapsed_seconds


def test_interrupted_trial_resumes_same_workspace_and_provider_operation(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "input.txt").write_text("resume")
    case = TrialCase(
        case_id="resume",
        description="resume an uncertain provider operation",
        workspace="fixture",
    )

    interrupted = _run(tmp_path, case, provider_config={"interrupt_once": True})
    resumed = _run(tmp_path, case, provider_config={"interrupt_once": True})

    assert interrupted.execution == "interrupted"
    assert interrupted.outcome == "interrupted"
    assert resumed.execution == "complete"
    assert resumed.outcome == "completed"
    assert resumed.run_id == interrupted.run_id
    assert resumed.value["answer"] == "answer-2"
    workspace = tmp_path / "output/workspace"
    assert (workspace / "interrupted-once").read_text() == str(workspace)
    assert (workspace / "provider-calls.txt").read_text() == "2"


def test_own_provider_cap_is_complete_behavioral_evidence(tmp_path):
    case = TrialCase(case_id="budget", description="exceed the common provider cap")

    result = _run(
        tmp_path,
        case,
        settings=TrialSettings(
            max_provider_turns=1, timeout_seconds=10, max_elapsed_seconds=30
        ),
    )

    assert result.execution == "complete"
    assert result.outcome == "budget_exceeded"
    assert result.provider_budget["used_turns"] == 1
    assert (tmp_path / "output/workspace/provider-calls.txt").read_text() == "1"


def test_trial_binds_and_coerces_target_inputs_before_nested_invocation(tmp_path):
    case = TrialCase(
        case_id="typed",
        description="coerce a typed input",
        kwargs={"payload": {"value": "7"}},
    )

    result = _run(tmp_path, case)

    assert result.execution == "complete"
    assert result.outcome == "completed"
    assert result.value == {"value": 7, "type": "TypedInput"}
    assert result.provider_budget["used_turns"] == 0


def test_unknown_recovery_remains_interrupted_without_redispatch(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "input.txt").write_text("unknown")
    case = TrialCase(
        case_id="unknown",
        description="do not repeat an unresolved provider effect",
        workspace="fixture",
    )

    first = _run(tmp_path, case, provider_config={"unknown_forever": True})
    second = _run(tmp_path, case, provider_config={"unknown_forever": True})
    third = _run(tmp_path, case, provider_config={"unknown_forever": True})

    assert [first.execution, second.execution, third.execution] == [
        "interrupted",
        "interrupted",
        "interrupted",
    ]
    assert first.run_id == second.run_id == third.run_id
    assert (tmp_path / "output/workspace/provider-calls.txt").read_text() == "1"


def test_provider_policy_failure_is_infrastructure_not_behavioral_evidence(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "input.txt").write_text("policy")
    case = TrialCase(
        case_id="policy",
        description="provider policy setup fails",
        workspace="fixture",
    )

    result = _run(tmp_path, case, provider_config={"policy_failure": True})

    assert result.execution == "infrastructure_error"
    assert result.outcome == "failed"
    assert "ProviderPolicyError" in result.error
    assert (tmp_path / "output/workspace/provider-calls.txt").read_text() == "1"


def test_trial_worker_loads_runtime_when_frozen_code_root_only_has_subject(tmp_path):
    code_root = tmp_path / "frozen-code"
    code_root.mkdir()
    (code_root / "subject.py").write_text(
        "from botpipe import Provider, workflow\n"
        "@workflow\n"
        "def standalone_trial(value: int):\n"
        "    return {'value': value, 'answer': Provider().run('standalone').value}\n"
    )
    result = run_trial(
        code_root=code_root,
        workflow_reference="subject.py:standalone_trial",
        case=TrialCase(
            case_id="standalone",
            description="run from a minimal frozen source root",
            kwargs={"value": "9"},
        ),
        fixture_root=None,
        output_root=tmp_path / "standalone-output",
        settings=TrialSettings(timeout_seconds=10, max_elapsed_seconds=30),
        provider_config={},
        provider_factory=f"{Path(__file__).resolve()}:make_trial_provider",
    )

    assert result.execution == "complete"
    assert result.outcome == "completed"
    assert result.value == {"value": 9, "answer": "answer-1"}


def test_candidate_signature_change_is_complete_failure_without_provider_dispatch(
    tmp_path,
):
    code_root = tmp_path / "candidate-code"
    code_root.mkdir()
    (code_root / "subject.py").write_text(
        "from botpipe import Provider, workflow\n"
        "@workflow\n"
        "def standalone_trial(other: int):\n"
        "    return Provider().run('must not dispatch').value\n"
    )

    result = run_trial(
        code_root=code_root,
        workflow_reference="subject.py:standalone_trial",
        case=TrialCase(
            case_id="signature-change",
            description="candidate removed the frozen input parameter",
            kwargs={"value": 1},
        ),
        fixture_root=None,
        output_root=tmp_path / "signature-output",
        settings=TrialSettings(timeout_seconds=10, max_elapsed_seconds=30),
        provider_config={},
        provider_factory=f"{Path(__file__).resolve()}:make_trial_provider",
    )

    assert result.execution == "complete"
    assert result.outcome == "failed"
    assert "missing a required argument: 'other'" in result.error
    assert result.provider_budget == {}
    assert not (tmp_path / "signature-output/workspace/provider-calls.txt").exists()


def test_interrupted_initialization_never_publishes_a_partial_trial(
    tmp_path, monkeypatch
):
    from botpipe_optimizer import trials

    output = tmp_path / "output"
    case = TrialCase(
        case_id="typed",
        description="recover initialization",
        kwargs={"payload": {"value": 4}},
    )

    original_write = trials._atomic_write

    def interrupt(path, content):
        original_write(path, content)
        if path.name == "trial.json":
            raise KeyboardInterrupt("crash before publishing the complete trial root")

    with monkeypatch.context() as patch:
        patch.setattr(trials, "_atomic_write", interrupt)
        with pytest.raises(KeyboardInterrupt):
            _run(tmp_path, case)
    assert not output.exists()
    result = _run(tmp_path, case)

    assert result.execution == "complete"
    assert result.outcome == "completed"
    assert result.value == {"value": 4, "type": "TypedInput"}
    assert (output / "trial.json").is_file()


def test_missing_manifest_does_not_authorize_deleting_an_existing_workspace(tmp_path):
    output = tmp_path / "output"
    (output / "workspace").mkdir(parents=True)
    valuable = output / "workspace/valuable.txt"
    valuable.write_text("user data")
    (output / "state").mkdir()
    with pytest.raises(RuntimeError, match="unowned uncommitted data"):
        _run(
            tmp_path,
            TrialCase(
                case_id="typed",
                description="unowned output",
                kwargs={"payload": {"value": 4}},
            ),
        )
    assert valuable.read_text() == "user data"


def test_worker_result_must_match_durable_case_and_run_identity(tmp_path):
    case = TrialCase(case_id="protocol", description="reject mismatched output")

    def mismatched(argv, **kwargs):
        Path(argv[-1]).write_text(
            json.dumps(
                {
                    "case_id": "someone-else",
                    "execution": "complete",
                    "outcome": "completed",
                    "run_id": "trial-wrong",
                }
            )
        )
        return ProcessResult(tuple(argv), 0, False, False, 0.1, "", "", False, False)

    result = _run(tmp_path, case, process_runner=mismatched)

    assert result.execution == "infrastructure_error"
    assert result.outcome == "invalid_worker_result"
    assert "identity does not match" in result.error


def test_wall_timeout_is_terminal_only_after_trial_ledger_exists(tmp_path):
    case = TrialCase(case_id="timeout", description="wall timeout classification")
    calls = 0

    def timed_out(argv, **kwargs):
        nonlocal calls
        calls += 1
        config = json.loads(Path(argv[-2]).read_text())
        ledger = (
            Path(config["state_dir"])
            / "tasks"
            / config["task_id"]
            / "runs"
            / config["run_id"]
            / "ledger.jsonl"
        )
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("created")
        return ProcessResult(tuple(argv), None, True, False, 3.0, "", "", False, False)

    first = _run(tmp_path, case, process_runner=timed_out)
    second = _run(tmp_path, case, process_runner=timed_out)

    assert first.execution == "complete"
    assert first.outcome == "timeout"
    assert second == first
    assert calls == 1

    def bootstrap_timeout(argv, **kwargs):
        return ProcessResult(tuple(argv), None, True, False, 1.0, "", "", False, False)

    failed = _run(
        tmp_path,
        case.model_copy(update={"case_id": "bootstrap"}),
        output_name="bootstrap-output",
        process_runner=bootstrap_timeout,
    )
    assert failed.execution == "infrastructure_error"
    assert failed.outcome == "bootstrap_timeout"
