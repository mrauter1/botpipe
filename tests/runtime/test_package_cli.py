from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.runtime import cli
from autoloop_v3.runtime.loader import resolve_workflow_reference


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PROVIDER_FACTORY_FLAG = "--provider" + "-factory"
LEGACY_WRAPPER_MODE = "AUTOLOOP_" + "CLI_MODE"
LEGACY_WRAPPER_DETECT = "detect_auto" + "loop_cli_mode"
LEGACY_REPO_LAYOUT = "src/auto" + "loop/"
GLOBAL_INTENT_FLAG = "--in" + "tent"
GLOBAL_PAIRS_FLAG = "--pa" + "irs"
GLOBAL_TASK_ID_FLAG = "--task" + "-id"


def _read_recursive_template(name: str) -> str:
    return (REPO_ROOT / "recursive_autoloop" / "run_recursive_autoloop_templates" / name).read_text(
        encoding="utf-8"
    )


def _shell_function_section(script: str, name: str, next_name: str) -> str:
    return script.split(f"{name}() {{", 1)[1].split(f"{next_name}()", 1)[0]


def _evict_generated_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name == "provider_backend":
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_workflow_modules():
    # Each test creates temporary workflow packages under the same module names.
    _evict_generated_modules()
    yield
    _evict_generated_modules()


class _UnusedProvider:
    def run_producer(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"producer should not run for system-only workflow: {request!r}")

    def run_verifier(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"verifier should not run for system-only workflow: {request!r}")

    def run_llm(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"llm should not run for system-only workflow: {request!r}")


def _provider_factory(**_: object) -> _UnusedProvider:
    return _UnusedProvider()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "workflows")
    _git(root, "commit", "-m", "baseline")


def _write_workflow_package(
    root: Path,
    package_name: str,
    *,
    workflow_name: str | None = None,
    class_name: str = "ExampleWorkflow",
    aliases: tuple[str, ...] = (),
    parameters_source: str | None = None,
    workflow_source: str | None = None,
    export_parameters: bool = False,
) -> Path:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "README.md").write_text("# Prompts\n", encoding="utf-8")
    (package_dir / "assets" / ".gitkeep").write_text("", encoding="utf-8")

    manifest_name = workflow_name or package_name
    aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{manifest_name}"',
                f'title = "{manifest_name.replace("_", " ").title()}"',
                'description = "Workflow test package."',
                f"aliases = [{aliases_source}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    if workflow_source is None:
        workflow_source = f"""
from __future__ import annotations

from pydantic import BaseModel

from core import GLOBAL, SUCCESS, SystemStep, Workflow
from core.primitives import Event


class {class_name}(Workflow):
    name = "{manifest_name}"

    class State(BaseModel):
        ready: bool = False

    bootstrap = SystemStep(name="bootstrap")
    entry = bootstrap
    transitions = {{
        GLOBAL: {{}},
        bootstrap: {{"ready": SUCCESS}},
    }}

    @staticmethod
    def on_bootstrap(state: State, ctx):
        return state.model_copy(update={{"ready": True}}), Event("ready")
""".strip()
    (package_dir / "workflow.py").write_text(workflow_source + "\n", encoding="utf-8")

    if export_parameters:
        source = parameters_source or """
from pydantic import BaseModel


class Parameters(BaseModel):
    mode: str = "strict"
""".strip()
        (package_dir / "params.py").write_text(source + "\n", encoding="utf-8")

    init_lines = [f"from .workflow import {class_name}"]
    exports = [class_name]
    if export_parameters:
        init_lines.append("from .params import Parameters")
        exports.append("Parameters")
    init_lines.append(f"__all__ = {exports!r}")
    (package_dir / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")
    return package_dir


def _paused_workflow_source(class_name: str, workflow_name: str) -> str:
    return f"""
from __future__ import annotations

import json

from pydantic import BaseModel

from core import GLOBAL, PAUSE, SUCCESS, SystemStep, Workflow
from core.primitives import Event


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        answered: bool = False

    ask = SystemStep(name="ask")
    entry = ask
    transitions = {{
        GLOBAL: {{}},
        ask: {{
            "question": PAUSE,
            "answered": SUCCESS,
        }},
    }}

    @staticmethod
    def on_ask(state: State, ctx):
        payload = {{
            "answer": ctx.answer,
            "workflow_name": ctx.workflow_name,
            "workflow_params": ctx.workflow_params,
        }}
        (ctx.run_folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        if ctx.answer is None:
            return state, Event("question", question="What value?")
        return state.model_copy(update={{"answered": True}}), Event("answered")
""".strip()


def test_cli_help_exposes_package_commands_only() -> None:
    help_text = cli.build_arg_parser().format_help()

    for required in ("workflows", "run", "resume", "answer", "runs", "logs", "init"):
        assert required in help_text

    for forbidden in ("--class-name", "--request-text", "--resume", " exec "):
        assert forbidden not in help_text


def test_cli_mutating_command_help_exposes_provider_and_hides_provider_factory(capsys) -> None:
    for command in ("run", "resume", "answer"):
        with pytest.raises(SystemExit) as excinfo:
            cli.build_arg_parser().parse_args([command, "--help"])

        assert excinfo.value.code == 0
        help_text = capsys.readouterr().out
        assert "--provider" in help_text
        assert "--no-git" in help_text
        assert "--git-commit-policy" in help_text
        assert "--no-trace" in help_text
        assert PUBLIC_PROVIDER_FACTORY_FLAG not in help_text


def test_cli_workflows_show_reports_parameters_and_aliases(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "review_workflow",
        workflow_name="review",
        class_name="ReviewWorkflow",
        aliases=("reviewer",),
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Parameters(BaseModel):
    mode: str = "strict"
    reviewers: list[str] = []
""".strip(),
    )

    exit_code = cli.main(["workflows", "show", "reviewer", "--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["name"] == "review"
    assert payload["aliases"] == ["reviewer"]
    assert payload["authoring_shape"] == "manifest_package"
    assert payload["source_path"] == str(tmp_path / "workflows" / "review_workflow" / "workflow.py")
    assert payload["manifest_path"] == str(tmp_path / "workflows" / "review_workflow" / "workflow.toml")
    assert payload["parameters_supported"] is True
    assert payload["workflow_class"] == "ReviewWorkflow"
    assert payload["state_model"].endswith("ReviewWorkflow.State")
    assert payload["transitions"] == {
        "global": {},
        "steps": {
            "bootstrap": {
                "ready": "SUCCESS",
                "question": "PAUSE",
                "blocked": "PAUSE",
                "failed": "FAIL",
            }
        },
    }
    assert payload["parameters"] == [
        {"default": "strict", "name": "mode", "repeated": False, "required": False, "type": "str"},
        {"default": [], "name": "reviewers", "repeated": True, "required": False, "type": "list[str]"},
    ]


def test_cli_workflows_show_uses_spec_paths_for_specs_and_contracts_support_files(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _write_workflow_package(
        tmp_path,
        "review_workflow",
        workflow_name="review",
        class_name="ReviewWorkflow",
    )
    (package_dir / "specs.py").write_text("class Parameters:\n    pass\n", encoding="utf-8")
    (package_dir / "contracts.py").write_text("# support schema\n", encoding="utf-8")

    exit_code = cli.main(["workflows", "show", "review", "--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert "contracts_path" not in payload
    assert payload["spec_paths"] == [
        str(package_dir / "specs.py"),
        str(package_dir / "contracts.py"),
    ]


def test_cli_workflow_resolution_prefers_canonical_names_and_rejects_ambiguous_aliases(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "review_pkg",
        workflow_name="review",
        class_name="ReviewWorkflow",
        aliases=("shared",),
    )
    _write_workflow_package(
        tmp_path,
        "shared_pkg",
        workflow_name="shared",
        class_name="SharedWorkflow",
    )

    canonical_exit = cli.main(["workflows", "show", "shared", "--root", str(tmp_path)])
    canonical_payload = json.loads(capsys.readouterr().out)

    assert canonical_exit == 0
    assert canonical_payload["name"] == "shared"
    assert canonical_payload["workflow_class"] == "SharedWorkflow"

    _write_workflow_package(
        tmp_path,
        "audit_pkg",
        workflow_name="audit",
        class_name="AuditWorkflow",
        aliases=("common",),
    )
    _write_workflow_package(
        tmp_path,
        "reviewer_pkg",
        workflow_name="reviewer",
        class_name="ReviewerWorkflow",
        aliases=("common",),
    )

    ambiguous_exit = cli.main(["workflows", "show", "common", "--root", str(tmp_path)])
    ambiguous_captured = capsys.readouterr()

    assert ambiguous_exit == cli.EXIT_RESOLUTION_ERROR
    assert "workflow alias 'common' is ambiguous" in ambiguous_captured.err
    assert "audit" in ambiguous_captured.err
    assert "reviewer" in ambiguous_captured.err


def test_cli_workflows_list_includes_manifest_and_inferred_workflows_without_imports(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "manifest_review",
        workflow_name="manifest_review",
        class_name="ManifestReviewWorkflow",
        aliases=("manifest_alias",),
    )
    single_file = tmp_path / "workflows" / "single_review.py"
    single_file.write_text(
        'raise AssertionError("single-file workflow should not import during list")\n',
        encoding="utf-8",
    )

    exit_code = cli.main(["workflows", "list", "--root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == [
        {
            "aliases": ["manifest_alias"],
            "authoring_shape": "manifest_package",
            "description": "Workflow test package.",
            "manifest_present": True,
            "name": "manifest_review",
            "source_path": str(tmp_path / "workflows" / "manifest_review" / "workflow.py"),
            "title": "Manifest Review",
        },
        {
            "aliases": [],
            "authoring_shape": "single_file",
            "description": None,
            "manifest_present": False,
            "name": "single_review",
            "source_path": str(single_file),
            "title": "Single Review",
        },
    ]


def test_cli_serializes_typed_workflow_parameters_as_json_safe_values(
    tmp_path: Path,
    capsys,
) -> None:
    requested_at = datetime(2026, 4, 22, 12, 30, tzinfo=timezone.utc)
    _write_workflow_package(
        tmp_path,
        "typed_review",
        workflow_name="typed_review",
        class_name="TypedReviewWorkflow",
        export_parameters=True,
        parameters_source=f"""
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class ReviewMode(str, Enum):
    strict = "strict"


class Parameters(BaseModel):
    output_dir: Path = Path("reports")
    requested_at: datetime = datetime.fromisoformat("{requested_at.isoformat()}")
    mode: ReviewMode = ReviewMode.strict
""".strip(),
    )

    show_exit = cli.main(["workflows", "show", "typed_review", "--root", str(tmp_path)])
    show_payload = json.loads(capsys.readouterr().out)

    assert show_exit == 0
    assert show_payload["parameters"] == [
        {"default": "reports", "name": "output_dir", "repeated": False, "required": False, "type": "Path"},
        {
            "default": requested_at.isoformat(),
            "name": "requested_at",
            "repeated": False,
            "required": False,
            "type": "datetime",
        },
        {"default": "strict", "name": "mode", "repeated": False, "required": False, "type": "ReviewMode"},
    ]
    assert show_payload["parameters_model"].endswith("Parameters")

    run_exit = cli.main(
        [
            "run",
            "typed_review",
            "task-json",
            "--root",
            str(tmp_path),
            "--message",
            "Serialize defaults",
            "--no-git",
        ],
        provider_factory=_provider_factory,
    )
    run_payload = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    run_dir = tmp_path / ".autoloop" / "tasks" / "task-json" / "wf_typed_review" / "runs" / run_payload["run_id"]
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["workflow_params"] == {
        "mode": "strict",
        "output_dir": "reports",
        "requested_at": requested_at.isoformat(),
    }


def test_cli_mutating_commands_accept_non_public_provider_factory_injection_seam(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "injected_provider",
        workflow_name="injected_provider",
        class_name="InjectedProviderWorkflow",
    )

    exit_code = cli.main(
        [
            "run",
            "injected_provider",
            "task-injected-provider",
            "--root",
            str(tmp_path),
            "--message",
            "Run with a non-public injected provider factory",
            "--no-git",
        ],
        provider_factory=_provider_factory,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["workflow"] == "injected_provider"
    assert payload["status"] == "success"


def test_cli_mutating_commands_route_public_provider_selection_through_typed_config(
    tmp_path: Path,
    capsys,
) -> None:
    seen_configs: list[object] = []

    def inspect_provider_factory(**kwargs: object) -> _UnusedProvider:
        seen_configs.append(kwargs["config"])
        return _UnusedProvider()

    _write_workflow_package(
        tmp_path,
        "selected_provider",
        workflow_name="selected_provider",
        class_name="SelectedProviderWorkflow",
    )

    exit_code = cli.main(
        [
            "run",
            "selected_provider",
            "task-selected-provider",
            "--root",
            str(tmp_path),
            "--message",
            "Run with a public provider selection path",
            "--no-git",
            "--provider",
            "claude",
            "--model",
            "claude-opus",
            "--model-effort",
            "max",
        ],
        provider_factory=inspect_provider_factory,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["workflow"] == "selected_provider"
    assert len(seen_configs) == 1
    config = seen_configs[0]
    assert config.provider.name == "claude"
    assert config.provider.claude.model == "claude-opus"
    assert config.provider.claude.effort == "max"


def test_cli_mutating_commands_route_runtime_git_and_trace_overrides_through_typed_config(
    tmp_path: Path,
    capsys,
) -> None:
    seen_configs: list[object] = []

    def inspect_provider_factory(**kwargs: object) -> _UnusedProvider:
        seen_configs.append(kwargs["config"])
        return _UnusedProvider()

    _write_workflow_package(
        tmp_path,
        "runtime_configured",
        workflow_name="runtime_configured",
        class_name="RuntimeConfiguredWorkflow",
    )
    _init_repo(tmp_path)

    exit_code = cli.main(
        [
            "run",
            "runtime_configured",
            "task-runtime-configured",
            "--root",
            str(tmp_path),
            "--message",
            "Run with runtime git and trace overrides",
            "--no-git",
            "--git-commit-policy",
            "run",
            "--no-trace",
        ],
        provider_factory=inspect_provider_factory,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["workflow"] == "runtime_configured"
    assert len(seen_configs) == 1
    config = seen_configs[0]
    assert config.runtime.git_tracking.enabled is True
    assert config.runtime.git_tracking.commit_policy == "run"
    assert config.runtime.tracing.enabled is False


def test_cli_run_rejects_public_provider_factory_flag(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "public_provider",
        workflow_name="public_provider",
        class_name="PublicProviderWorkflow",
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "run",
                "public_provider",
                "task-public-provider",
                "--root",
                str(tmp_path),
                "--message",
                "Run with a public provider factory",
                PUBLIC_PROVIDER_FACTORY_FLAG,
                "provider_backend:build",
            ]
        )
    captured = capsys.readouterr()

    assert excinfo.value.code == cli.EXIT_USAGE_ERROR
    assert f"unrecognized arguments: {PUBLIC_PROVIDER_FACTORY_FLAG} provider_backend:build" in captured.err


def test_cli_run_resume_answer_and_diagnostics_follow_package_contract(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "review_workflow",
        workflow_name="review",
        class_name="ReviewWorkflow",
        aliases=("reviewer",),
        export_parameters=True,
        parameters_source="""
from pydantic import BaseModel


class Parameters(BaseModel):
    mode: str = "strict"
    reviewers: list[str] = []
""".strip(),
        workflow_source=_paused_workflow_source("ReviewWorkflow", "review"),
    )

    run_exit = cli.main(
        [
            "run",
            "reviewer",
            "task-42",
            "--root",
            str(tmp_path),
            "--message",
            "Review this change",
            "--no-git",
            "-wf",
            "mode",
            "focused",
            "-wf",
            "reviewers",
            "alice",
            "-wf",
            "reviewers",
            "bob",
        ],
        provider_factory=_provider_factory,
    )
    run_output = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert run_output["workflow"] == "review"
    assert run_output["task_id"] == "task-42"
    assert run_output["status"] == "paused"
    assert run_output["paused"] is True
    run_id = run_output["run_id"]

    run_dir = tmp_path / ".autoloop" / "tasks" / "task-42" / "wf_review" / "runs" / run_id
    assert len(list((run_dir.parent).iterdir())) == 1

    show_exit = cli.main(["runs", "show", "review", "task-42", "--root", str(tmp_path)])
    show_output = json.loads(capsys.readouterr().out)

    assert show_exit == 0
    assert show_output["run_id"] == run_id
    assert show_output["status"] == "paused"
    assert show_output["resumable"] is True
    assert show_output["workflow_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}
    assert show_output["pending_question"] == "What value?"

    list_exit = cli.main(["runs", "list", "--workflow", "reviewer", "--task", "task-42", "--root", str(tmp_path)])
    list_output = json.loads(capsys.readouterr().out)

    assert list_exit == 0
    assert len(list_output) == 1
    assert list_output[0]["run_id"] == run_id
    assert list_output[0]["paused"] is True

    logs_exit = cli.main(["logs", "review", "task-42", "--root", str(tmp_path)])
    logs_output = capsys.readouterr().out

    assert logs_exit == 0
    assert '"event_type": "run_started"' in logs_output

    raw_logs_exit = cli.main(["logs", "review", "task-42", "--root", str(tmp_path), "--raw"])
    raw_logs_captured = capsys.readouterr()

    assert raw_logs_exit == cli.EXIT_RESOLUTION_ERROR
    assert "raw log output is missing" in raw_logs_captured.err

    resume_exit = cli.main(
        ["resume", "review", "task-42", "--root", str(tmp_path), "--no-git"],
        provider_factory=_provider_factory,
    )
    resume_output = json.loads(capsys.readouterr().out)

    assert resume_exit == 0
    assert resume_output["run_id"] == run_id
    assert resume_output["status"] == "paused"
    assert len(list((run_dir.parent).iterdir())) == 1

    answer_exit = cli.main(
        ["answer", "review", "task-42", "--root", str(tmp_path), "--answer", "Use OAuth", "--no-git"],
        provider_factory=_provider_factory,
    )
    answer_output = json.loads(capsys.readouterr().out)

    assert answer_exit == 0
    assert answer_output["run_id"] == run_id
    assert answer_output["status"] == "success"
    assert answer_output["paused"] is False
    assert len(list((run_dir.parent).iterdir())) == 1

    final_show_exit = cli.main(["runs", "show", "reviewer", "task-42", "--root", str(tmp_path)])
    final_show = json.loads(capsys.readouterr().out)
    result_payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))

    assert final_show_exit == 0
    assert final_show["status"] == "success"
    assert final_show["paused"] is False
    assert result_payload["answer"] == "Use OAuth"
    assert result_payload["workflow_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}


def test_cli_latest_run_selection_and_explicit_run_id_targeting_are_deterministic(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "review_workflow",
        workflow_name="review",
        class_name="ReviewWorkflow",
        workflow_source=_paused_workflow_source("ReviewWorkflow", "review"),
    )

    first_exit = cli.main(
        ["run", "review", "task-runs", "--root", str(tmp_path), "--message", "First request", "--no-git"],
        provider_factory=_provider_factory,
    )
    first_run = json.loads(capsys.readouterr().out)
    second_exit = cli.main(
        ["run", "review", "task-runs", "--root", str(tmp_path), "--message", "Second request", "--no-git"],
        provider_factory=_provider_factory,
    )
    second_run = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert second_exit == 0
    assert first_run["run_id"] != second_run["run_id"]

    latest_show_exit = cli.main(["runs", "show", "review", "task-runs", "--root", str(tmp_path)])
    latest_show = json.loads(capsys.readouterr().out)

    assert latest_show_exit == 0
    assert latest_show["run_id"] == second_run["run_id"]
    assert latest_show["status"] == "paused"

    latest_resume_exit = cli.main(
        ["resume", "review", "task-runs", "--root", str(tmp_path), "--no-git"],
        provider_factory=_provider_factory,
    )
    latest_resume = json.loads(capsys.readouterr().out)

    assert latest_resume_exit == 0
    assert latest_resume["run_id"] == second_run["run_id"]
    assert latest_resume["status"] == "paused"

    explicit_answer_exit = cli.main(
        [
            "answer",
            "review",
            "task-runs",
            "--root",
            str(tmp_path),
            "--run-id",
            first_run["run_id"],
            "--answer",
            "Resolve the older run explicitly",
            "--no-git",
        ],
        provider_factory=_provider_factory,
    )
    explicit_answer = json.loads(capsys.readouterr().out)

    assert explicit_answer_exit == 0
    assert explicit_answer["run_id"] == first_run["run_id"]
    assert explicit_answer["status"] == "success"

    latest_run_state_exit = cli.main(
        [
            "runs",
            "show",
            "review",
            "task-runs",
            "--root",
            str(tmp_path),
            "--run-id",
            second_run["run_id"],
        ]
    )
    latest_run_state = json.loads(capsys.readouterr().out)

    assert latest_run_state_exit == 0
    assert latest_run_state["run_id"] == second_run["run_id"]
    assert latest_run_state["status"] == "paused"


def test_cli_rejects_invalid_or_unsupported_workflow_params(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "no_params",
        workflow_name="no_params",
        class_name="NoParamsWorkflow",
    )
    exit_code = cli.main(
        ["run", "no_params", "task-1", "--root", str(tmp_path), "--message", "hello", "-wf", "mode", "strict"],
        provider_factory=_provider_factory,
    )
    captured = capsys.readouterr()

    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "does not declare Parameters" in captured.err

    _write_workflow_package(
        tmp_path,
        "strict_review",
        workflow_name="strict_review",
        class_name="StrictReviewWorkflow",
        export_parameters=True,
        workflow_source=_paused_workflow_source("StrictReviewWorkflow", "strict_review"),
    )
    duplicate_exit = cli.main(
        [
            "run",
            "strict_review",
            "task-1",
            "--root",
            str(tmp_path),
            "--message",
            "hello",
            "-wf",
            "mode",
            "strict",
            "-wf",
            "mode",
            "loose",
        ],
        provider_factory=_provider_factory,
    )
    duplicate_captured = capsys.readouterr()

    assert duplicate_exit == cli.EXIT_USAGE_ERROR
    assert "does not accept repeated values" in duplicate_captured.err

    unknown_exit = cli.main(
        ["run", "strict_review", "task-1", "--root", str(tmp_path), "--message", "hello", "-wf", "unknown", "x"],
        provider_factory=_provider_factory,
    )
    unknown_captured = capsys.readouterr()

    assert unknown_exit == cli.EXIT_USAGE_ERROR
    assert "unknown workflow parameter 'unknown'" in unknown_captured.err


@pytest.mark.parametrize(
    ("shape", "expected_relpaths"),
    [
        ("single", ("workflows/child_workflow.py",)),
        ("flow-specs", ("workflows/child_workflow/flow.py", "workflows/child_workflow/specs.py")),
        (
            "package",
            (
                "workflows/child_workflow/flow.py",
                "workflows/child_workflow/specs.py",
                "workflows/child_workflow/__init__.py",
                "workflows/child_workflow/workflow.toml",
            ),
        ),
    ],
)
def test_cli_init_workflow_scaffolds_supported_shapes_and_rejects_duplicates(
    tmp_path: Path,
    capsys,
    shape: str,
    expected_relpaths: tuple[str, ...],
) -> None:
    exit_code = cli.main(["init", "workflow", "child_workflow", "--shape", shape, "--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["name"] == "child_workflow"
    assert payload["workflow_class"] == "ChildWorkflow"
    assert payload["shape"] == shape
    for relative_path in expected_relpaths:
        assert (tmp_path / relative_path).exists()

    if shape == "package":
        assert (tmp_path / "workflows" / "child_workflow" / "prompts" / "README.md").exists()
        assert (tmp_path / "workflows" / "child_workflow" / "assets" / ".gitkeep").exists()
    elif shape == "flow-specs":
        package_dir = tmp_path / "workflows" / "child_workflow"
        assert not (package_dir / "__init__.py").exists()
        assert not (package_dir / "workflow.toml").exists()
        assert not (package_dir / "prompts").exists()
        assert not (package_dir / "assets").exists()
    else:
        assert not (tmp_path / "workflows" / "child_workflow").exists()

    compiled = compile_workflow(resolve_workflow_reference(tmp_path, "child_workflow").workflow_cls)
    assert compiled.workflow_name == "child_workflow"

    duplicate_exit = cli.main(["init", "workflow", "child_workflow", "--shape", shape, "--root", str(tmp_path)])
    duplicate = capsys.readouterr()

    assert duplicate_exit == cli.EXIT_USAGE_ERROR
    assert "already exists" in duplicate.err


def test_cli_init_workflow_defaults_to_flow_specs_shape(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(["init", "workflow", "child_workflow", "--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["shape"] == "flow-specs"
    assert (tmp_path / "workflows" / "child_workflow" / "flow.py").exists()
    assert (tmp_path / "workflows" / "child_workflow" / "specs.py").exists()


def test_recursive_wrapper_targets_the_global_cli_contract() -> None:
    script = (REPO_ROOT / "recursive_autoloop" / "run_recursive_autoloop.sh").read_text(encoding="utf-8")

    cli_guard_section = _shell_function_section(script, "require_global_autoloop_cli", "resolve_task_dir")
    start_cli_section = _shell_function_section(script, "run_autoloop_start_cli", "run_autoloop_resume_cli")
    resume_cli_section = _shell_function_section(script, "run_autoloop_resume_cli", "latest_autoloop_run_dir")

    assert LEGACY_WRAPPER_MODE not in script
    assert LEGACY_WRAPPER_DETECT not in script
    assert "legacy)" not in script
    assert '"--workspace"' in cli_guard_section
    assert '"--task-id"' in cli_guard_section
    assert '"--intent"' in cli_guard_section
    assert '"--intent-mode"' in cli_guard_section
    assert '"--pairs"' in cli_guard_section
    assert '"--resume"' in cli_guard_section
    assert 'fatal "autoloop on PATH does not expose the global CLI surface required by recursive_autoloop."' in cli_guard_section
    assert "\nrequire_global_autoloop_cli\n" in script
    assert 'Direct Autoloop resume hint: autoloop --workspace \\"$WORKSPACE\\" --task-id \\"$task_id\\" --resume' in script
    assert '--workspace "$WORKSPACE"' in start_cli_section
    assert f'{GLOBAL_TASK_ID_FLAG} "$task_id"' in start_cli_section
    assert f'{GLOBAL_INTENT_FLAG} "$message"' in start_cli_section
    assert "--intent-mode replace" in start_cli_section
    assert f'{GLOBAL_PAIRS_FLAG} "$pair_selection"' in start_cli_section
    assert '--workspace "$WORKSPACE"' in resume_cli_section
    assert f'{GLOBAL_TASK_ID_FLAG} "$task_id"' in resume_cli_section
    assert "--resume" in resume_cli_section


def test_recursive_templates_reference_current_global_cli_contract() -> None:
    templates = {
        name: _read_recursive_template(name)
        for name in (
            "bootstrap_task.md.tmpl",
            "cycle_task.md.tmpl",
            "framework_evolution_charter.md.tmpl",
            "framework_roadmap.md.tmpl",
            "workflow_authoring_doctrine.md.tmpl",
            "workflow_examples.md.tmpl",
        )
    }

    for text in templates.values():
        assert LEGACY_REPO_LAYOUT not in text
        assert "docs/autoloop_workflow_framework_prd.md" not in text
        assert "docs/autoloop_workflow_framework_adr.md" not in text

    bootstrap_lower = templates["bootstrap_task.md.tmpl"].lower()
    cycle_lower = templates["cycle_task.md.tmpl"].lower()
    charter_lower = templates["framework_evolution_charter.md.tmpl"].lower()
    roadmap_lower = templates["framework_roadmap.md.tmpl"].lower()
    doctrine_lower = templates["workflow_authoring_doctrine.md.tmpl"].lower()
    examples_lower = templates["workflow_examples.md.tmpl"].lower()

    for text in (bootstrap_lower, cycle_lower):
        for required in (
            "docs/architecture.md",
            "docs/authoring.md",
            "core/",
            "runtime/",
            "extensions/",
            "stdlib/",
            "workflows/",
            ".autoloop_recursive/",
            "greenfield",
            "feature compatibility",
            "autoloop --workspace ... --task-id ... --intent ... --pairs ...",
            "autoloop --workspace ... --task-id ... --resume",
            "ctx.invoke_workflow(...)",
        ):
            assert required in text

    for required in (
        "workflows/",
        "flow.py",
        "specs.py",
        "workflow.toml",
        "workflow.py",
        "autoloop --workspace ... --task-id ... --intent ... --pairs ...",
        "autoloop --workspace ... --task-id ... --resume",
        "greenfield",
    ):
        assert required in charter_lower

    for required in (
        "runtime/cli.py",
        "runtime/runner.py",
        "workflows/",
        "autoloop --workspace ... --task-id ... --intent ... --pairs ...",
        "autoloop --workspace ... --task-id ... --resume",
        "greenfield",
        "feature compatibility only",
        "workflow surfaces remain ordinary python modules or packages",
    ):
        assert required in roadmap_lower

    for required in (
        "single-file workflow",
        "flow.py",
        "autoloop run/resume/answer",
        "ctx.invoke_workflow(...)",
    ):
        assert required in doctrine_lower

    for required in (
        "workflows/<name>.py",
        "flow.py",
        "specs.py",
        "workflow.toml",
        "autoloop --workspace ... --task-id ... --intent ... --pairs ...",
        "ctx.invoke_workflow(...)",
    ):
        assert required in examples_lower
