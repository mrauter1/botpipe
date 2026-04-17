from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from pydantic import BaseModel

from autoloop_v3.runtime import cli as cli_module
from autoloop_v3.runtime.config import (
    ClaudeProviderConfig,
    CodexProviderConfig,
    ConfigError,
    ProviderConfig,
    RuntimeConfig,
    discover_config_file,
    resolve_runtime_config,
)
from autoloop_v3.runtime.events import append_clarification, parse_decisions_headers
from autoloop_v3.runtime.loader import load_compiled_workflow, load_workflow_class
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.runtime.stores import FilesystemCheckpointStore, FilesystemSessionStore
from autoloop_v3.runtime.stores.filesystem import load_session_payload
from autoloop_v3.runtime.workspace import (
    PHASE_MODE_SINGLE,
    PhasePlanCriterion,
    PhasePlanPhase,
    ResolvedPhaseSelection,
    build_implicit_phase_plan,
    create_run,
    ensure_phase_plan_scaffold,
    ensure_workspace,
    load_phase_selection,
    phase_session_path,
    plan_session_path,
    resolve_resume_state_root,
    save_phase_selection,
)
from autoloop_v3.workflow.compiler import compile_workflow
from autoloop_v3.workflow.errors import WorkflowExecutionError
from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider
from autoloop_v3.workflow.stores.protocols import CheckpointPayload, SessionBinding, SessionSnapshot


REPO_ROOT = Path(__file__).resolve().parents[3]


def _install_fake_yaml(monkeypatch, module):
    class FakeYaml:
        @staticmethod
        def safe_load(text: str):
            return json.loads(text)

        @staticmethod
        def safe_dump(payload: object, sort_keys: bool = False, allow_unicode: bool = True):
            return json.dumps(payload, indent=2) + "\n"

    monkeypatch.setattr(module, "yaml", FakeYaml)


def _write_cli_smoke_provider_module(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import json

from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider


def factory(*, config, args):
    return ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw\\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("implementation notes\\n"),
                "implement raw\\n",
            )[1],
            lambda request: (
                request.artifacts.test_strat.write_text("test strategy\\n"),
                "test raw\\n",
            )[1],
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok\\n", tag="plan_ready"),
            Outcome(raw_output="implement ok\\n", tag="implemented"),
            Outcome(raw_output="test ok\\n", tag="phase_passed"),
        ],
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_cli_smoke_ralph_provider_module(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider


def factory(*, config, args):
    return ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.scratchpad.write_text("understanding\\n"),
                Outcome(raw_output="u raw\\n", tag="understood"),
            )[1],
            Outcome(
                raw_output="plan raw\\n",
                tag="action_planned",
                payload={"type": "shell", "command": "echo hi"},
            ),
            lambda request: (
                request.artifacts.scratchpad.write_text("reflection\\n"),
                Outcome(raw_output="reflect raw\\n", tag="goal_met"),
            )[1],
        ]
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _cli_smoke_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_entries = [str(tmp_path), str(REPO_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg-config")
    return env


def test_autoloop_v1_imports_through_root_workflow_shim_and_legacy_loader_handles_ralph():
    sys.modules.pop("autoloop_v1", None)
    imported = importlib.import_module("autoloop_v1")
    compiled_autoloop = compile_workflow(imported.AutoloopV1)
    assert compiled_autoloop.entry_step_name == "plan"
    assert sorted(compiled_autoloop.steps) == ["activate_next_phase", "implement", "plan", "test"]

    ralph_cls = load_workflow_class(REPO_ROOT / "Ralph_loop.py")
    compiled_ralph = compile_workflow(ralph_cls)
    assert compiled_ralph.entry_step_name == "understand"
    assert sorted(compiled_ralph.steps) == ["execute", "plan_action", "reflect", "understand"]


def test_filesystem_session_store_uses_compatibility_paths_and_loads_legacy_thread_id(tmp_path: Path):
    run_dir = tmp_path / "run"
    store = FilesystemSessionStore(run_dir)

    plan_binding = store.open("plan_session")
    phase_binding = store.open("phase_session", scope="Phase One")

    assert plan_session_path(run_dir) == run_dir / "sessions" / "plan.json"
    assert phase_session_path(run_dir, "Phase One") == run_dir / "sessions" / "phases" / "_pid-5068617365204f6e65.json"
    assert plan_binding.session_id.startswith("plan_session:global:")
    assert phase_binding.session_id.startswith("phase_session:Phase One:")

    legacy_plan = run_dir / "sessions" / "plan.json"
    legacy_plan.write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-123", "provider_metadata": {"source": "legacy"}}),
        encoding="utf-8",
    )
    legacy_store = FilesystemSessionStore(run_dir)
    loaded = legacy_store.get("plan_session")
    assert loaded is not None
    assert loaded.session_id == "thread-123"
    assert loaded.metadata["provider"] == "codex"


def test_filesystem_session_store_sparse_writes_preserve_existing_legacy_metadata(tmp_path: Path):
    run_dir = tmp_path / "run"
    session_file = run_dir / "sessions" / "plan.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        json.dumps(
            {
                "mode": "persistent",
                "thread_id": "thread-123",
                "provider_metadata": {"source": "legacy"},
                "pending_clarification_note": "Question:\nShip this?\n\nAnswer:\nYes",
                "created_at": "2026-04-17T00:00:00+00:00",
                "last_used_at": "2026-04-17T00:05:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    restored_store = FilesystemSessionStore(run_dir)
    restored_store.restore(
        SessionSnapshot(
            bindings=(SessionBinding(ref_name="plan_session", scope=None, session_id="thread-456"),),
            active_scopes={"plan_session": None},
        )
    )
    restored_payload = load_session_payload(session_file, "persistent", "codex")

    assert restored_payload["session_id"] == "thread-456"
    assert restored_payload["metadata"]["provider_metadata"] == {"source": "legacy"}
    assert restored_payload["metadata"]["pending_clarification_note"] == "Question:\nShip this?\n\nAnswer:\nYes"
    assert restored_payload["metadata"]["created_at"] == "2026-04-17T00:00:00+00:00"
    assert restored_payload["metadata"]["last_used_at"] == "2026-04-17T00:05:00+00:00"

    upsert_store = FilesystemSessionStore(run_dir)
    upsert_store.upsert(SessionBinding(ref_name="plan_session", scope=None, session_id="thread-789"))
    upsert_payload = load_session_payload(session_file, "persistent", "codex")

    assert upsert_payload["session_id"] == "thread-789"
    assert upsert_payload["metadata"]["provider_metadata"] == {"source": "legacy"}
    assert upsert_payload["metadata"]["pending_clarification_note"] == "Question:\nShip this?\n\nAnswer:\nYes"
    assert upsert_payload["metadata"]["created_at"] == "2026-04-17T00:00:00+00:00"
    assert upsert_payload["metadata"]["last_used_at"] == "2026-04-17T00:05:00+00:00"


def test_filesystem_checkpoint_store_round_trip(tmp_path: Path):
    class State(BaseModel):
        value: str = ""

    store = FilesystemCheckpointStore(tmp_path / "checkpoint.json", State)
    checkpoint = CheckpointPayload(
        stage="plan",
        state=State(value="saved"),
        session_bindings=SessionSnapshot(
            bindings=(SessionBinding(ref_name="plan_session", scope=None, session_id="plan:1"),),
            active_scopes={"plan_session": None},
        ),
        pending_question="Need approval?",
        pending_answer=None,
    )

    store.save(checkpoint)
    loaded = store.load()

    assert loaded is not None
    assert loaded.stage == "plan"
    assert loaded.state.value == "saved"
    assert loaded.pending_question == "Need approval?"
    assert loaded.session_bindings.bindings[0].session_id == "plan:1"


def test_workspace_phase_selection_and_resume_root_compatibility(tmp_path: Path, monkeypatch):
    from autoloop_v3.runtime import workspace as workspace_module

    _install_fake_yaml(monkeypatch, workspace_module)
    workspace = ensure_workspace(tmp_path, "task-1", "Initial request")
    run = create_run(workspace, run_id="run-1", request_text="Initial request")

    scaffold = ensure_phase_plan_scaffold(workspace, run.request_file)
    scaffold_payload = json.loads(scaffold.read_text(encoding="utf-8"))
    assert scaffold_payload["task_id"] == "task-1"

    implicit = build_implicit_phase_plan("task-1", run.request_file)
    assert implicit.explicit is False
    assert implicit.phases[0].phase_id == "implicit-phase"

    phase = PhasePlanPhase(
        phase_id="phase-a",
        title="Phase A",
        objective="Do phase A",
        in_scope=("a",),
        out_of_scope=(),
        dependencies=(),
        acceptance_criteria=(PhasePlanCriterion(id="AC-1", text="done"),),
        deliverables=("code",),
        risks=(),
        rollback=(),
    )
    selection = ResolvedPhaseSelection(
        phase_mode=PHASE_MODE_SINGLE,
        phase_ids=("phase-a",),
        phases=(phase,),
        explicit=True,
    )
    save_phase_selection(run.phase_selection_file, selection)
    restored = load_phase_selection(
        run.phase_selection_file,
        implicit.__class__(
            version=1,
            task_id="task-1",
            request_snapshot_ref=str(run.request_file),
            phases=(phase,),
            explicit=True,
        ),
    )
    assert restored is not None
    assert restored.phase_ids == ("phase-a",)

    legacy_run = tmp_path / ".superloop" / "tasks" / "legacy-task" / "runs" / "legacy-run"
    legacy_run.mkdir(parents=True)
    assert resolve_resume_state_root(tmp_path, task_id="legacy-task") == tmp_path / ".superloop"
    assert resolve_resume_state_root(tmp_path, run_id="legacy-run") == tmp_path / ".superloop"


def test_append_clarification_updates_raw_logs_decisions_and_session_note(tmp_path: Path):
    task_raw = tmp_path / "task_raw_phase_log.md"
    run_raw = tmp_path / "run_raw_phase_log.md"
    decisions = tmp_path / "decisions.txt"
    session_file = tmp_path / "session.json"
    task_raw.write_text("# Task Raw\n", encoding="utf-8")
    run_raw.write_text("# Run Raw\n", encoding="utf-8")
    decisions.write_text("", encoding="utf-8")

    append_clarification(
        run_raw,
        task_raw,
        decisions,
        session_file,
        pair="implement",
        phase_id="phase-a",
        phase="producer",
        cycle=1,
        attempt=2,
        question="Ship this change?",
        answer="Yes, ship it.",
        run_id="run-1",
    )

    blocks = parse_decisions_headers(decisions.read_text(encoding="utf-8"))
    session_payload = json.loads(session_file.read_text(encoding="utf-8"))

    assert [block.attrs["entry"] for block in blocks] == ["questions", "answers"]
    assert blocks[0].body == "Ship this change?\n"
    assert blocks[1].body == "Yes, ship it.\n"
    assert session_payload["pending_clarification_note"] == "Question:\nShip this change?\n\nAnswer:\nYes, ship it."
    assert "Question:\nShip this change?" in run_raw.read_text(encoding="utf-8")
    assert "Answer:\nYes, ship it." in task_raw.read_text(encoding="utf-8")


def test_resolve_runtime_config_merges_global_local_and_cli(monkeypatch, tmp_path: Path):
    from autoloop_v3.runtime import config as config_module

    _install_fake_yaml(monkeypatch, config_module)
    global_dir = tmp_path / "global"
    workspace_root = tmp_path / "workspace"
    global_dir.mkdir()
    workspace_root.mkdir()
    monkeypatch.setattr(config_module, "user_config_dir", lambda: global_dir)

    (global_dir / "autoloop.yaml").write_text(
        json.dumps(
            {
                "provider": {"model": "gpt-global", "model_effort": "medium"},
                "runtime": {"max_iterations": 9, "phase_mode": "up-to", "no_git": True},
            }
        ),
        encoding="utf-8",
    )
    (workspace_root / "autoloop.config").write_text(
        json.dumps(
            {
                "provider": {"name": "claude", "codex": {"model": "gpt-local"}},
                "runtime": {"max_iterations": 3, "track_autoloop_artifacts": False},
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_runtime_config(
        workspace_root,
        Namespace(
            model="gpt-cli",
            model_effort="high",
            pairs=None,
            max_iterations=None,
            phase_mode=None,
            intent_mode=None,
            full_auto_answers=None,
            no_git=None,
            track_autoloop_artifacts=None,
        ),
    )

    assert resolved.provider == ProviderConfig(
        name="claude",
        codex=CodexProviderConfig(model="gpt-cli", model_effort="high"),
        claude=ClaudeProviderConfig(),
    )
    assert resolved.runtime == RuntimeConfig(
        pairs="plan,implement,test",
        max_iterations=3,
        phase_mode="up-to",
        intent_mode="preserve",
        full_auto_answers=False,
        no_git=True,
        track_autoloop_artifacts=False,
    )

    (workspace_root / "autoloop.yaml").write_text("{}", encoding="utf-8")
    with __import__("pytest").raises(ConfigError, match="multiple configuration files"):
        discover_config_file(workspace_root)


def test_runner_rejects_non_default_compatibility_options_instead_of_ignoring_them(tmp_path: Path):
    import pytest

    provider = ScriptedLLMProvider()
    with pytest.raises(
        ConfigError,
        match="does not support --pairs, --max-iterations, --phase-id, --phase-mode, --full-auto-answers, --no-git, --track-autoloop-artifacts",
    ):
        run_workflow(
            REPO_ROOT / "autoloop_v1.py",
            provider=provider,
            options=RunnerOptions(
                root=tmp_path,
                task_id="task-1",
                request_text="Ship it",
                pairs="plan",
                max_iterations=3,
                phase_mode="up-to",
                phase_id="phase-a",
                full_auto_answers=True,
                no_git=True,
                track_autoloop_artifacts=False,
            ),
        )


def test_runner_resume_without_checkpoint_but_with_legacy_state_fails_with_targeted_message(tmp_path: Path):
    import pytest

    workspace = ensure_workspace(tmp_path, "task-1", "Initial request")
    run = create_run(workspace, run_id="run-1", request_text="Initial request")
    (run.sessions_dir / "plan.json").write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-123"}) + "\n",
        encoding="utf-8",
    )
    run.events_file.write_text(json.dumps({"seq": 1, "event_type": "run_started"}) + "\n", encoding="utf-8")
    original_events = run.events_file.read_text(encoding="utf-8")

    with pytest.raises(  # targeted compatibility gate, not the generic missing-checkpoint failure
        Exception,
        match="without autoloop_v3 checkpoint.json",
    ):
        run_workflow(
            REPO_ROOT / "autoloop_v1.py",
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="task-1", run_id="run-1", resume=True),
        )
    assert run.events_file.read_text(encoding="utf-8") == original_events


def test_runner_rejects_legacy_resume_without_scaffolding_workspace_or_run_files(tmp_path: Path):
    import pytest

    legacy_task = tmp_path / ".superloop" / "tasks" / "legacy-task"
    legacy_run = legacy_task / "runs" / "legacy-run"
    legacy_run.mkdir(parents=True)
    sessions_dir = legacy_run / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "plan.json").write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-123"}) + "\n",
        encoding="utf-8",
    )
    events_file = legacy_run / "events.jsonl"
    events_file.write_text(json.dumps({"seq": 1, "event_type": "run_started"}) + "\n", encoding="utf-8")

    with pytest.raises(Exception, match="without autoloop_v3 checkpoint.json"):
        run_workflow(
            REPO_ROOT / "autoloop_v1.py",
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="legacy-task", run_id="legacy-run", resume=True),
        )

    assert not (legacy_task / "task.json").exists()
    assert not (legacy_task / "request.md").exists()
    assert not (legacy_task / "raw_phase_log.md").exists()
    assert not (legacy_task / "decisions.txt").exists()
    assert not (legacy_run / "request.md").exists()
    assert not (legacy_run / "raw_phase_log.md").exists()
    assert events_file.read_text(encoding="utf-8") == json.dumps({"seq": 1, "event_type": "run_started"}) + "\n"


def test_cli_main_threads_runtime_options_into_runner_options(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_resolve_runtime_config(root: Path, args: Namespace):
        assert root == tmp_path
        assert args.phase_id == "phase-a"
        return Namespace(
            runtime=Namespace(
                intent_mode="replace",
                pairs="plan,implement",
                max_iterations=7,
                phase_mode="single",
                full_auto_answers=False,
                no_git=False,
                track_autoloop_artifacts=True,
            )
        )

    def fake_load_provider_factory(spec: str):
        assert spec == "fake:factory"

        def factory(*, config: object, args: Namespace):
            captured["factory_config"] = config
            captured["factory_args"] = args
            return object()

        return factory

    def fake_run_workflow(workflow_target: str, *, provider: object, options: RunnerOptions):
        captured["workflow_target"] = workflow_target
        captured["provider"] = provider
        captured["options"] = options
        return object()

    monkeypatch.setattr(cli_module, "resolve_runtime_config", fake_resolve_runtime_config)
    monkeypatch.setattr(cli_module, "load_provider_factory", fake_load_provider_factory)
    monkeypatch.setattr(cli_module, "run_workflow", fake_run_workflow)

    exit_code = cli_module.main(
        [
            "autoloop_v1.py",
            "--task-id",
            "task-1",
            "--provider-factory",
            "fake:factory",
            "--root",
            str(tmp_path),
            "--run-id",
            "run-1",
            "--resume",
            "--answer",
            "approved",
            "--request-text",
            "Ship it",
            "--class-name",
            "AutoloopV1",
            "--phase-id",
            "phase-a",
        ]
    )

    assert exit_code == 0
    assert captured["workflow_target"] == "autoloop_v1.py"
    options = captured["options"]
    assert isinstance(options, RunnerOptions)
    assert options.root == tmp_path
    assert options.task_id == "task-1"
    assert options.run_id == "run-1"
    assert options.resume is True
    assert options.answer == "approved"
    assert options.request_text == "Ship it"
    assert options.class_name == "AutoloopV1"
    assert options.intent_mode == "replace"
    assert options.pairs == "plan,implement"
    assert options.max_iterations == 7
    assert options.phase_mode == "single"
    assert options.phase_id == "phase-a"
    assert options.full_auto_answers is False
    assert options.no_git is False
    assert options.track_autoloop_artifacts is True


def test_cli_main_turns_config_errors_into_parser_exit(monkeypatch, capsys, tmp_path: Path):
    import pytest

    monkeypatch.setattr(cli_module, "resolve_runtime_config", lambda root, args: (_ for _ in ()).throw(ConfigError("bad config")))

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main(
            [
                "autoloop_v1.py",
                "--task-id",
                "task-1",
                "--provider-factory",
                "fake:factory",
                "--root",
                str(tmp_path),
            ]
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "bad config" in captured.err
    assert "usage:" in captured.err


def test_cli_main_turns_workflow_execution_errors_into_clean_exit(monkeypatch, capsys, tmp_path: Path):
    import pytest

    monkeypatch.setattr(
        cli_module,
        "resolve_runtime_config",
        lambda root, args: Namespace(
            runtime=Namespace(
                intent_mode="preserve",
                pairs="plan,implement,test",
                max_iterations=15,
                phase_mode="single",
                full_auto_answers=False,
                no_git=False,
                track_autoloop_artifacts=True,
            )
        ),
    )
    monkeypatch.setattr(cli_module, "load_provider_factory", lambda spec: (lambda *, config, args: object()))
    monkeypatch.setattr(
        cli_module,
        "run_workflow",
        lambda workflow_target, *, provider, options: (_ for _ in ()).throw(WorkflowExecutionError("cannot resume")),
    )

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main(
            [
                "autoloop_v1.py",
                "--task-id",
                "task-1",
                "--provider-factory",
                "fake:factory",
                "--root",
                str(tmp_path),
            ]
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.err == "cannot resume\n"
    assert "usage:" not in captured.err


def test_cli_module_smoke_executes_autoloop_v1_end_to_end(tmp_path: Path):
    provider_module = tmp_path / "smoke_provider.py"
    _write_cli_smoke_provider_module(provider_module)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autoloop_v3.runtime.cli",
            str(REPO_ROOT / "autoloop_v1.py"),
            "--task-id",
            "task-1",
            "--provider-factory",
            "smoke_provider:factory",
            "--root",
            str(tmp_path),
            "--request-text",
            "Ship it",
        ],
        cwd=REPO_ROOT,
        env=_cli_smoke_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-1"
    run_dir = next((task_dir / "runs").iterdir())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert (task_dir / "plan" / "phase_plan.yaml").exists()
    assert (task_dir / "phases" / "phase-a" / "implement" / "implementation_notes.md").read_text(encoding="utf-8") == (
        "implementation notes\n"
    )
    assert (task_dir / "phases" / "phase-a" / "test" / "test_strategy.md").read_text(encoding="utf-8") == (
        "test strategy\n"
    )
    assert (run_dir / "request.md").read_text(encoding="utf-8") == "Ship it\n"
    assert (run_dir / "sessions" / "plan.json").exists()
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"


def test_cli_module_smoke_executes_ralph_loop_end_to_end(tmp_path: Path):
    provider_module = tmp_path / "smoke_provider_ralph.py"
    _write_cli_smoke_ralph_provider_module(provider_module)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autoloop_v3.runtime.cli",
            str(REPO_ROOT / "Ralph_loop.py"),
            "--task-id",
            "ralph-task",
            "--provider-factory",
            "smoke_provider_ralph:factory",
            "--root",
            str(tmp_path),
            "--request-text",
            "Do it",
        ],
        cwd=REPO_ROOT,
        env=_cli_smoke_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    task_dir = tmp_path / ".autoloop" / "tasks" / "ralph-task"
    run_dir = next((task_dir / "runs").iterdir())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert (task_dir / "action_log.md").read_text(encoding="utf-8") == "u raw\nplan raw\nreflect raw\n"
    assert (run_dir / "sessions" / "main_session.json").exists()
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"


def test_runner_executes_autoloop_v1_and_writes_runtime_artifacts(tmp_path: Path):
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.phase_plan.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "task_id": request.context.task_id,
                            "request_snapshot_ref": "request.md",
                            "phases": [{"phase_id": "phase-a"}],
                        }
                    )
                ),
                "plan raw\n",
            )[1],
            lambda request: (
                request.artifacts.impl_notes.write_text("implementation notes\n"),
                "implement raw\n",
            )[1],
            "test raw\n",
        ],
        verifier_turns=[
            Outcome(raw_output="plan ok", tag="plan_ready"),
            Outcome(raw_output="implement ok", tag="implemented"),
            Outcome(raw_output="test ok", tag="phase_passed"),
        ],
    )

    result = run_workflow(
        REPO_ROOT / "autoloop_v1.py",
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="Ship it"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "task-1"
    runs_dir = task_dir / "runs"
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]

    assert result.terminal == "SUCCESS"
    assert result.state.phase.id == "phase-a"
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (task_dir / "raw_phase_log.md").read_text(encoding="utf-8").count("raw") >= 2
    assert (run_dir / "raw_phase_log.md").read_text(encoding="utf-8").count("raw") >= 2
    assert (run_dir / "sessions" / "plan.json").exists()
    assert (run_dir / "sessions" / "phases" / "phase-a.json").exists()
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events][0] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert provider.calls[0].prompt_path.endswith("autoloop/src/autoloop/templates/plan_producer.md")
