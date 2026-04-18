from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
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
from autoloop_v3.runtime.loader import load_workflow_class, load_workflow_module
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow
from autoloop_v3.runtime.stores import (
    FilesystemCheckpointStore,
    FilesystemSessionStore,
    ensure_session_payload_placeholder,
    scope_key,
    write_session_payload,
)
from autoloop_v3.runtime.stores.filesystem import load_session_payload
from autoloop_v3.runtime.workspace import create_run, ensure_workspace, resolve_resume_state_root
from autoloop_v3.workflow.compiler import compile_workflow
from autoloop_v3.workflow.errors import WorkflowExecutionError
from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider
from autoloop_v3.workflow.stores.protocols import CheckpointPayload, SessionBinding, SessionSnapshot


REPO_ROOT = Path(__file__).resolve().parents[3]
TOY_WORKFLOW = REPO_ROOT / "autoloop_v3" / "tests" / "fixtures" / "toy_runtime_workflow.py"


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

from autoloop_v3.workflow.primitives import Outcome
from autoloop_v3.workflow.providers.fake import ScriptedLLMProvider


def factory(*, config, args):
    return ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.notes.write_text("nebula notes\\n"),
                Outcome(raw_output="survey raw\\n", tag="surveyed"),
            )[1]
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


def test_workspace_workflows_compile_through_the_strict_loader_surface():
    sys.modules.pop("autoloop_v1", None)
    imported = importlib.import_module("autoloop_v1")
    compiled_autoloop = compile_workflow(imported.AutoloopV1)
    assert compiled_autoloop.entry_step_name == "plan"
    assert sorted(compiled_autoloop.steps) == ["activate_next_phase", "implement", "plan", "test"]

    ralph_cls = load_workflow_class(REPO_ROOT / "Ralph_loop.py")
    compiled_ralph = compile_workflow(ralph_cls)
    assert compiled_ralph.entry_step_name == "understand"
    assert sorted(compiled_ralph.steps) == ["execute", "plan_action", "reflect", "understand"]


def test_loader_does_not_inject_canonical_symbols(tmp_path: Path):
    workflow_file = tmp_path / "needs_imports.py"
    workflow_file.write_text(
        """
from pydantic import BaseModel

from workflow import LLMStep, SUCCESS, Workflow


class NeedsImports(Workflow):
    class State(BaseModel):
        pass

    ask = LLMStep(name="ask", producer="ask.md")
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(NameError, match="Outcome"):
        load_workflow_module(workflow_file)


def test_filesystem_session_store_uses_generic_paths_and_loads_legacy_thread_id(tmp_path: Path):
    run_dir = tmp_path / "run"
    store = FilesystemSessionStore(run_dir)

    main_binding = store.open("main")
    orbit_binding = store.open("orbit", scope="Nebula One")

    assert store.path_for("main") == run_dir / "sessions" / "main.json"
    assert store.path_for("orbit", "Nebula One") == run_dir / "sessions" / "scopes" / scope_key("Nebula One") / "orbit.json"
    assert main_binding.session_id.startswith("main:global:")
    assert orbit_binding.session_id.startswith("orbit:Nebula One:")

    legacy_main = run_dir / "sessions" / "main.json"
    legacy_main.write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-123", "provider_metadata": {"source": "legacy"}}),
        encoding="utf-8",
    )
    legacy_store = FilesystemSessionStore(run_dir)
    loaded = legacy_store.get("main")
    assert loaded is not None
    assert loaded.session_id == "thread-123"
    assert loaded.metadata["provider"] == "codex"


def test_runtime_store_placeholder_helper_creates_generic_session_payload(tmp_path: Path):
    session_file = tmp_path / "arbitrary" / "session.json"

    ensure_session_payload_placeholder(session_file, default_mode="ephemeral", default_provider="claude")

    raw_payload = json.loads(session_file.read_text(encoding="utf-8"))
    loaded_payload = load_session_payload(session_file, "ephemeral", "claude")

    assert raw_payload["mode"] == "ephemeral"
    assert raw_payload["provider"] == "claude"
    assert raw_payload["session_id"] is None
    assert raw_payload["thread_id"] is None
    assert loaded_payload["session_id"] is None
    assert loaded_payload["metadata"]["mode"] == "ephemeral"
    assert loaded_payload["metadata"]["provider"] == "claude"
    assert isinstance(loaded_payload["metadata"]["created_at"], str)


def test_runtime_store_write_helper_preserves_sparse_metadata_and_non_codex_thread_id(tmp_path: Path):
    session_file = tmp_path / "sessions" / "assistant.json"

    write_session_payload(
        session_file,
        "session-456",
        {
            "provider": "claude",
            "mode": "persistent",
            "provider_metadata": {"source": "legacy"},
            "thread_id": "thread-123",
            "pending_clarification_note": "Question:\nShip this?\n\nAnswer:\nYes",
            "created_at": "2026-04-17T00:00:00+00:00",
            "last_used_at": "2026-04-17T00:05:00+00:00",
        },
        default_mode="persistent",
        default_provider="codex",
    )

    raw_payload = json.loads(session_file.read_text(encoding="utf-8"))
    loaded_payload = load_session_payload(session_file, "persistent", "codex")

    assert raw_payload["provider"] == "claude"
    assert raw_payload["session_id"] == "session-456"
    assert raw_payload["thread_id"] == "thread-123"
    assert raw_payload["provider_metadata"] == {"source": "legacy"}
    assert loaded_payload["session_id"] == "session-456"
    assert loaded_payload["metadata"]["provider"] == "claude"
    assert loaded_payload["metadata"]["provider_metadata"] == {"source": "legacy"}
    assert loaded_payload["metadata"]["thread_id"] == "thread-123"
    assert loaded_payload["metadata"]["pending_clarification_note"] == "Question:\nShip this?\n\nAnswer:\nYes"
    assert loaded_payload["metadata"]["created_at"] == "2026-04-17T00:00:00+00:00"
    assert loaded_payload["metadata"]["last_used_at"] == "2026-04-17T00:05:00+00:00"


def test_runtime_store_write_helper_mirrors_codex_session_id_into_thread_id(tmp_path: Path):
    session_file = tmp_path / "sessions" / "main.json"

    write_session_payload(
        session_file,
        "thread-999",
        {"provider_metadata": {"source": "runtime"}},
        default_mode="persistent",
        default_provider="codex",
    )

    raw_payload = json.loads(session_file.read_text(encoding="utf-8"))
    loaded_payload = load_session_payload(session_file, "persistent", "codex")

    assert raw_payload["provider"] == "codex"
    assert raw_payload["session_id"] == "thread-999"
    assert raw_payload["thread_id"] == "thread-999"
    assert loaded_payload["session_id"] == "thread-999"
    assert loaded_payload["metadata"]["provider"] == "codex"
    assert loaded_payload["metadata"]["thread_id"] == "thread-999"
    assert loaded_payload["metadata"]["provider_metadata"] == {"source": "runtime"}


def test_autoloop_v1_source_inlines_phase_parsing_and_explicit_artifact_templates():
    source = (REPO_ROOT / "autoloop_v1.py").read_text(encoding="utf-8")

    assert "def parse_phase_ids(" in source
    assert "phase_artifact_template" not in source
    assert "autoloop_v1_support" not in source
    assert 'Artifact("{task_folder}/implement/phases/{state.phase.dir_key}/criteria.md")' in source
    assert 'Artifact("{task_folder}/implement/phases/{state.phase.dir_key}/implementation_notes.md")' in source
    assert 'Artifact("{task_folder}/test/phases/{state.phase.dir_key}/criteria.md")' in source
    assert 'Artifact("{task_folder}/test/phases/{state.phase.dir_key}/test_strategy.md")' in source


def test_autoloop_v1_parity_modules_delegate_session_payload_writes_to_runtime_store_helpers():
    runtime_store_source = (REPO_ROOT / "autoloop_v3" / "runtime" / "stores" / "filesystem.py").read_text(
        encoding="utf-8"
    )
    parity_path = REPO_ROOT / "autoloop_v3" / "workflows" / "autoloop_v1_parity.py"
    conventions_path = REPO_ROOT / "autoloop_v3" / "workflows" / "autoloop_v1_conventions.py"
    parity_source = parity_path.read_text(encoding="utf-8")
    conventions_source = conventions_path.read_text(encoding="utf-8")
    workflows_init = (REPO_ROOT / "autoloop_v3" / "workflows" / "__init__.py").read_text(encoding="utf-8")

    assert "def write_session_payload(" in runtime_store_source
    assert "def ensure_session_payload_placeholder(" in runtime_store_source
    assert not (REPO_ROOT / "autoloop_v3" / "workflows" / "autoloop_v1_support.py").exists()
    assert "ensure_session_payload_placeholder(plan_session_file)" in parity_source
    assert "set_pending_session_note(session_file, note)" in parity_source
    assert "ExecutionObserver" not in parity_source
    assert "class _AutoloopV1LoggingProvider" in parity_source
    assert "class _AutoloopV1Engine" not in parity_source
    assert "def autoloop_v1_session_path(" in conventions_source
    assert "from .autoloop_v1_parity import run_autoloop_v1" in workflows_init


def test_filesystem_session_store_supports_custom_path_resolver(tmp_path: Path):
    run_dir = tmp_path / "run"

    def resolver(base_dir: Path, ref_name: str, scope: str | None) -> Path:
        if scope is None:
            return base_dir / "custom-sessions" / f"{ref_name}.json"
        return base_dir / "custom-sessions" / scope_key(scope) / f"{ref_name}.json"

    store = FilesystemSessionStore(run_dir, path_resolver=resolver)
    binding = store.open("phase_session", scope="Phase One")
    expected_path = run_dir / "custom-sessions" / scope_key("Phase One") / "phase_session.json"

    assert expected_path.exists()
    assert store.path_for("phase_session", "Phase One") == expected_path

    reloaded = FilesystemSessionStore(run_dir, path_resolver=resolver)
    loaded = reloaded.get("phase_session", scope="Phase One")

    assert loaded is not None
    assert loaded.session_id == binding.session_id


def test_filesystem_session_store_sparse_writes_preserve_existing_metadata(tmp_path: Path):
    run_dir = tmp_path / "run"
    session_file = run_dir / "sessions" / "main.json"
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
            bindings=(SessionBinding(ref_name="main", scope=None, session_id="thread-456"),),
            active_scopes={"main": None},
        )
    )
    restored_payload = load_session_payload(session_file, "persistent", "codex")

    assert restored_payload["session_id"] == "thread-456"
    assert restored_payload["metadata"]["provider_metadata"] == {"source": "legacy"}
    assert restored_payload["metadata"]["pending_clarification_note"] == "Question:\nShip this?\n\nAnswer:\nYes"
    assert restored_payload["metadata"]["created_at"] == "2026-04-17T00:00:00+00:00"
    assert restored_payload["metadata"]["last_used_at"] == "2026-04-17T00:05:00+00:00"

    upsert_store = FilesystemSessionStore(run_dir)
    upsert_store.upsert(SessionBinding(ref_name="main", scope=None, session_id="thread-789"))
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
        stage="survey",
        state=State(value="saved"),
        session_bindings=SessionSnapshot(
            bindings=(SessionBinding(ref_name="main", scope=None, session_id="main:1"),),
            active_scopes={"main": None},
        ),
        pending_question="Need approval?",
        pending_answer=None,
    )

    store.save(checkpoint)
    loaded = store.load()

    assert loaded is not None
    assert loaded.stage == "survey"
    assert loaded.state.value == "saved"
    assert loaded.pending_question == "Need approval?"
    assert loaded.session_bindings.bindings[0].session_id == "main:1"


def test_workspace_creates_generic_layout_and_preserves_resume_root_compatibility(tmp_path: Path):
    workspace = ensure_workspace(tmp_path, "task-1", "Initial request")
    run = create_run(workspace, run_id="run-1", request_text="Initial request")

    assert workspace.task_request_file.read_text(encoding="utf-8") == "Initial request\n"
    assert run.request_file.read_text(encoding="utf-8") == "Initial request\n"
    assert run.sessions_dir == run.run_dir / "sessions"
    assert not (workspace.task_dir / "plan").exists()
    assert not (workspace.task_dir / "implement").exists()
    assert not (workspace.task_dir / "test").exists()
    assert not (workspace.task_dir / "raw_phase_log.md").exists()
    assert not (workspace.task_dir / "decisions.txt").exists()
    assert not (run.run_dir / "raw_phase_log.md").exists()
    assert not (run.run_dir / "phase_selection.json").exists()

    legacy_run = tmp_path / ".superloop" / "tasks" / "legacy-task" / "runs" / "legacy-run"
    legacy_run.mkdir(parents=True)
    assert resolve_resume_state_root(tmp_path, task_id="legacy-task") == tmp_path / ".superloop"
    assert resolve_resume_state_root(tmp_path, run_id="legacy-run") == tmp_path / ".superloop"


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
                "runtime": {"max_steps": 75, "intent_mode": "append"},
            }
        ),
        encoding="utf-8",
    )
    (workspace_root / "autoloop.config").write_text(
        json.dumps(
            {
                "provider": {"name": "claude", "codex": {"model": "gpt-local"}},
                "runtime": {"max_steps": 25},
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_runtime_config(
        workspace_root,
        Namespace(
            model="gpt-cli",
            model_effort="high",
            max_steps=None,
            intent_mode=None,
        ),
    )

    assert resolved.provider == ProviderConfig(
        name="claude",
        codex=CodexProviderConfig(model="gpt-cli", model_effort="high"),
        claude=ClaudeProviderConfig(),
    )
    assert resolved.runtime == RuntimeConfig(max_steps=25, intent_mode="append")

    (workspace_root / "autoloop.yaml").write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError, match="multiple configuration files"):
        discover_config_file(workspace_root)


def test_runner_rejects_non_positive_max_steps(tmp_path: Path):
    with pytest.raises(ConfigError, match="max_steps must be a positive integer"):
        run_workflow(
            TOY_WORKFLOW,
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="task-1", request_text="Ship it", max_steps=0),
        )


def test_runner_resume_without_checkpoint_but_with_persisted_state_fails_with_targeted_message(tmp_path: Path):
    workspace = ensure_workspace(tmp_path, "task-1", "Initial request")
    run = create_run(workspace, run_id="run-1", request_text="Initial request")
    (run.sessions_dir / "main.json").write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-123"}) + "\n",
        encoding="utf-8",
    )
    run.events_file.write_text(json.dumps({"seq": 1, "event_type": "run_started"}) + "\n", encoding="utf-8")
    original_events = run.events_file.read_text(encoding="utf-8")

    with pytest.raises(Exception, match="without autoloop_v3 checkpoint.json"):
        run_workflow(
            TOY_WORKFLOW,
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="task-1", run_id="run-1", resume=True),
        )

    assert run.events_file.read_text(encoding="utf-8") == original_events


def test_runner_resume_without_checkpoint_rejects_scoped_session_files(tmp_path: Path):
    workspace = ensure_workspace(tmp_path, "task-1", "Initial request")
    run = create_run(workspace, run_id="run-1", request_text="Initial request")
    scoped_session = run.sessions_dir / "scopes" / "phase-a" / "phase_session.json"
    scoped_session.parent.mkdir(parents=True)
    scoped_session.write_text(
        json.dumps({"mode": "persistent", "thread_id": "thread-456"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="without autoloop_v3 checkpoint.json"):
        run_workflow(
            TOY_WORKFLOW,
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(root=tmp_path, task_id="task-1", run_id="run-1", resume=True),
        )


def test_cli_main_threads_generic_runtime_options_into_runner_options(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_resolve_runtime_config(root: Path, args: Namespace):
        assert root == tmp_path
        return Namespace(runtime=Namespace(intent_mode="replace", max_steps=23))

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
            str(TOY_WORKFLOW),
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
            "ToyRuntimeWorkflow",
        ]
    )

    assert exit_code == 0
    assert captured["workflow_target"] == str(TOY_WORKFLOW)
    options = captured["options"]
    assert isinstance(options, RunnerOptions)
    assert options.root == tmp_path
    assert options.task_id == "task-1"
    assert options.run_id == "run-1"
    assert options.resume is True
    assert options.answer == "approved"
    assert options.request_text == "Ship it"
    assert options.class_name == "ToyRuntimeWorkflow"
    assert options.intent_mode == "replace"
    assert options.max_steps == 23


def test_cli_main_turns_config_errors_into_parser_exit(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(cli_module, "resolve_runtime_config", lambda root, args: (_ for _ in ()).throw(ConfigError("bad config")))

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main(
            [
                str(TOY_WORKFLOW),
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
    monkeypatch.setattr(
        cli_module,
        "resolve_runtime_config",
        lambda root, args: Namespace(runtime=Namespace(intent_mode="preserve", max_steps=100)),
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
                str(TOY_WORKFLOW),
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


def test_runner_executes_toy_workflow_without_phase_scaffolding(tmp_path: Path):
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.notes.write_text("nebula notes\n"),
                Outcome(raw_output="survey raw\n", tag="surveyed"),
            )[1]
        ]
    )

    result = run_workflow(
        TOY_WORKFLOW,
        provider=provider,
        options=RunnerOptions(root=tmp_path, task_id="toy-task", request_text="Map the nebula"),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / "toy-task"
    run_dir = next((task_dir / "runs").iterdir())
    events = [json.loads(line) for line in run_dir.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert result.terminal == "SUCCESS"
    assert result.history == ("survey", "archive")
    assert result.state.note == "nebula notes"
    assert result.state.archived is True
    assert (task_dir / "toy" / "notes.md").read_text(encoding="utf-8") == "nebula notes\n"
    assert (run_dir / "toy_transcript.log").read_text(encoding="utf-8") == "survey raw\n"
    assert (run_dir / "sessions" / "scopes" / "cluster-1" / "orbit.json").exists()
    assert (run_dir / "request.md").read_text(encoding="utf-8") == "Map the nebula\n"
    assert not (task_dir / "plan").exists()
    assert not (task_dir / "implement").exists()
    assert not (task_dir / "test").exists()
    assert not (task_dir / "raw_phase_log.md").exists()
    assert not (task_dir / "decisions.txt").exists()
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"


def test_cli_module_smoke_executes_toy_workflow_end_to_end(tmp_path: Path):
    provider_module = tmp_path / "smoke_provider.py"
    _write_cli_smoke_provider_module(provider_module)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autoloop_v3.runtime.cli",
            str(TOY_WORKFLOW),
            "--task-id",
            "toy-task",
            "--provider-factory",
            "smoke_provider:factory",
            "--root",
            str(tmp_path),
            "--request-text",
            "Map the nebula",
        ],
        cwd=REPO_ROOT,
        env=_cli_smoke_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    task_dir = tmp_path / ".autoloop" / "tasks" / "toy-task"
    run_dir = next((task_dir / "runs").iterdir())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert (task_dir / "toy" / "notes.md").read_text(encoding="utf-8") == "nebula notes\n"
    assert (run_dir / "request.md").read_text(encoding="utf-8") == "Map the nebula\n"
    assert (run_dir / "sessions" / "scopes" / "cluster-1" / "orbit.json").exists()
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["status"] == "success"
