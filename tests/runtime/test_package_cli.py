from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from botlane.core.compiler import compile_workflow
from botlane.runtime import cli
from botlane.runtime.loader import resolve_workflow_reference


PUBLIC_PROVIDER_FACTORY_FLAG = "--provider" + "-factory"
REMOVED_CONTRACTS_PATH = "contracts" + "_path"
REMOVED_WORKFLOW_PY_FIELD = "legacy_" + "workflow_path"


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
    async def run_producer(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"producer should not run for system-only workflow: {request!r}")

    async def run_verifier(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"verifier should not run for system-only workflow: {request!r}")

    async def run_llm(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"llm should not run for system-only workflow: {request!r}")


def _provider_factory(**_: object) -> _UnusedProvider:
    return _UnusedProvider()


def _assert_bootstrap_scaffold_contract(source: str) -> None:
    assert 'from botlane import Event, FINISH, Workflow, python_step' in source
    assert '@python_step(name="bootstrap", routes={"ready": FINISH})' in source
    assert "def bootstrap(ctx):" in source
    assert 'ctx.state = ctx.state.model_copy(update={"ready": True})' in source
    assert 'return Event("ready")' in source
    assert "def _bootstrap(" not in source
    assert "python_step(_bootstrap" not in source
    assert "state, ctx" not in source


def _assert_compiled_bootstrap_contract(compiled) -> None:
    assert compiled.entry_step_name == "bootstrap"
    assert compiled.steps["bootstrap"].available_routes == ("ready",)
    assert compiled.steps["bootstrap"].authored_routes == ("ready",)
    assert compiled.steps["bootstrap"].runtime_control_routes == ()
    assert compiled.route("bootstrap", "ready").target == "FINISH"
    assert tuple(inspect.signature(compiled.steps["bootstrap"].python_handler).parameters) == ("ctx",)


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
    _git(root, "add", ".autoloop")
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
    workflows_root = root / ".autoloop" / "workflows"
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

from botlane import Event, FINISH, Workflow, python_step


class {class_name}(Workflow):
    name = "{manifest_name}"

    class State(BaseModel):
        ready: bool = False

    @python_step(name="bootstrap", routes={{"ready": FINISH}})
    def bootstrap(ctx):
        ctx.state = ctx.state.model_copy(update={{"ready": True}})
        return Event("ready")
""".strip()
    (package_dir / "workflow.py").write_text(workflow_source + "\n", encoding="utf-8")

    if export_parameters:
        source = parameters_source or """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        (package_dir / "params.py").write_text(source + "\n", encoding="utf-8")

    init_lines = [f"from .workflow import {class_name}"]
    exports = [class_name]
    if export_parameters:
        init_lines.append("from .params import Params")
        exports.append("Params")
    init_lines.append(f"__all__ = {exports!r}")
    (package_dir / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")
    return package_dir


def _paused_workflow_source(class_name: str, workflow_name: str) -> str:
    return f"""
from __future__ import annotations

import json

from pydantic import BaseModel

from botlane import AWAIT_INPUT, Event, FINISH, Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name}"

    class State(BaseModel):
        answered: bool = False

    @python_step(name="ask", routes={{"question": AWAIT_INPUT, "answered": FINISH}})
    def ask(ctx):
        payload = {{
            "answer": ctx.answer,
            "workflow_name": ctx.workflow_name,
            "workflow_params": ctx.workflow_params,
        }}
        (ctx.run_folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        if ctx.answer is None:
            return Event("question", question="What value?")
        ctx.state = ctx.state.model_copy(update={{"answered": True}})
        return Event("answered")
""".strip()


def test_cli_help_exposes_package_commands_only() -> None:
    help_text = cli.build_arg_parser().format_help()

    for required in ("workflows", "run", "resume", "answer", "runs", "logs", "init"):
        assert required in help_text
    assert "ROOT" not in help_text

    for forbidden in ("--class-name", "--request-text", "--resume", " exec "):
        assert forbidden not in help_text


def test_cli_mutating_command_help_exposes_provider_and_hides_provider_factory(capsys) -> None:
    for command in ("run", "resume", "answer"):
        with pytest.raises(SystemExit) as excinfo:
            cli.build_arg_parser().parse_args([command, "--help"])

        assert excinfo.value.code == 0
        help_text = capsys.readouterr().out
        assert "--workspace" in help_text
        assert "--workspace WORKSPACE" in help_text
        assert "--root" not in help_text
        assert "ROOT" not in help_text
        assert "--provider" in help_text
        assert "--policy-file" in help_text
        assert "--policy-validation-unsupported" in help_text
        assert "--policy-validation-lossy" in help_text
        assert "--policy-validation-unsafe-expansion" in help_text
        assert "--no-git" in help_text
        assert "--git-commit-policy" in help_text
        assert "--no-trace" in help_text
        assert PUBLIC_PROVIDER_FACTORY_FLAG not in help_text


@pytest.mark.parametrize(
    "argv",
    [
        ["workflows", "list", "--help"],
        ["runs", "list", "--help"],
        ["logs", "--help"],
        ["init", "workflow", "--help"],
    ],
)
def test_cli_common_workspace_help_surfaces_render_workspace_metavar(argv: list[str], capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(argv)

    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "--workspace WORKSPACE" in help_text
    assert "--root" not in help_text
    assert "ROOT" not in help_text
    assert "workspace directory" in help_text.lower()


@pytest.mark.parametrize(
    "argv",
    [
        ["workflows", "list"],
        ["workflows", "show", "review"],
        ["run", "review", "task-1", "--message", "hello"],
        ["resume", "review", "task-1"],
        ["answer", "review", "task-1", "--answer", "hello"],
        ["runs", "list"],
        ["runs", "show", "review", "task-1"],
        ["logs", "review", "task-1"],
        ["init", "workflow", "child_workflow"],
    ],
)
def test_cli_requires_workspace_for_public_entry_points(argv: list[str], capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.build_arg_parser().parse_args(argv)

    assert excinfo.value.code == cli.EXIT_USAGE_ERROR
    assert "--workspace" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["workflows", "list", "--workspace", "workspace", "--root", "legacy"],
        ["workflows", "show", "review", "--workspace", "workspace", "--root", "legacy"],
        ["run", "review", "task-1", "--message", "hello", "--workspace", "workspace", "--root", "legacy"],
        ["resume", "review", "task-1", "--workspace", "workspace", "--root", "legacy"],
        ["answer", "review", "task-1", "--answer", "hello", "--workspace", "workspace", "--root", "legacy"],
        ["runs", "list", "--workspace", "workspace", "--root", "legacy"],
        ["runs", "show", "review", "task-1", "--workspace", "workspace", "--root", "legacy"],
        ["logs", "review", "task-1", "--workspace", "workspace", "--root", "legacy"],
        ["init", "workflow", "child_workflow", "--workspace", "workspace", "--root", "legacy"],
    ],
)
def test_cli_rejects_root_flag_for_public_entry_points(argv: list[str], capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.build_arg_parser().parse_args(argv)

    assert excinfo.value.code == cli.EXIT_USAGE_ERROR
    assert "unrecognized arguments: --root legacy" in capsys.readouterr().err


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


class Params(BaseModel):
    mode: str = "strict"
    reviewers: list[str] = []
""".strip(),
    )

    exit_code = cli.main(["workflows", "show", "reviewer", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["name"] == "review"
    assert payload["aliases"] == ["reviewer"]
    assert payload["authoring_shape"] == "manifest_package"
    assert payload["source_path"] == str(tmp_path / ".autoloop" / "workflows" / "review_workflow" / "workflow.py")
    assert payload["manifest_path"] == str(tmp_path / ".autoloop" / "workflows" / "review_workflow" / "workflow.toml")
    assert payload["workflow_py_path"] == str(tmp_path / ".autoloop" / "workflows" / "review_workflow" / "workflow.py")
    assert payload["parameters_supported"] is True
    assert payload["workflow_class"] == "ReviewWorkflow"
    assert payload["state_model"].endswith("ReviewWorkflow.State")
    assert REMOVED_WORKFLOW_PY_FIELD not in payload
    assert payload["global_routes"] == {}
    assert payload["routes"] == {
        "global": {},
        "steps": {
            "bootstrap": {
                "ready": "FINISH",
            }
        },
    }
    assert payload["parameters"] == [
        {"default": "strict", "name": "mode", "repeated": False, "required": False, "type": "str"},
        {"default": [], "name": "reviewers", "repeated": True, "required": False, "type": "list[str]"},
    ]
    assert payload["steps"] == [
        {
            "available_routes": ["ready"],
            "authored_routes": ["ready"],
            "has_expected_output_schema": False,
            "kind": "python",
            "log_artifacts": [],
            "name": "bootstrap",
            "producer_prompt": None,
            "provider_visible_routes_full_auto": [],
            "provider_visible_routes_interactive": [],
            "reads": [],
            "requires": [],
            "routes": {
                "ready": {
                    "target": "FINISH",
                    "summary": "Routes from 'bootstrap' to 'FINISH'.",
                    "required_writes": [],
                    "handoff": None,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_interactive": False,
                    "provider_visible_full_auto": False,
                    "is_runtime_control": False,
                }
            },
            "runtime_control_routes": [],
            "session_name": None,
            "typed_output_schema": None,
            "verifier_prompt": None,
            "writes": [],
        }
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
    (package_dir / "specs.py").write_text("class Params:\n    pass\n", encoding="utf-8")
    (package_dir / "contracts.py").write_text("# support schema\n", encoding="utf-8")

    exit_code = cli.main(["workflows", "show", "review", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert REMOVED_CONTRACTS_PATH not in payload
    assert REMOVED_WORKFLOW_PY_FIELD not in payload
    assert payload["spec_paths"] == [
        str(package_dir / "specs.py"),
        str(package_dir / "contracts.py"),
    ]


def test_cli_workflow_resolution_rejects_same_tier_name_alias_collisions_and_ambiguous_aliases(
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

    duplicate_key_exit = cli.main(["workflows", "show", "shared", "--workspace", str(tmp_path)])
    duplicate_key_captured = capsys.readouterr()

    assert duplicate_key_exit == cli.EXIT_RESOLUTION_ERROR
    assert "duplicate workflow resolution key 'shared'" in duplicate_key_captured.err
    assert str(tmp_path / ".autoloop" / "workflows" / "review_pkg" / "workflow.py") in duplicate_key_captured.err
    assert str(tmp_path / ".autoloop" / "workflows" / "shared_pkg" / "workflow.py") in duplicate_key_captured.err

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

    ambiguous_exit = cli.main(["workflows", "show", "common", "--workspace", str(tmp_path)])
    ambiguous_captured = capsys.readouterr()

    assert ambiguous_exit == cli.EXIT_RESOLUTION_ERROR
    assert "duplicate workflow resolution key 'common'" in ambiguous_captured.err
    assert str(tmp_path / ".autoloop" / "workflows" / "audit_pkg" / "workflow.py") in ambiguous_captured.err
    assert str(tmp_path / ".autoloop" / "workflows" / "reviewer_pkg" / "workflow.py") in ambiguous_captured.err


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
    single_file = tmp_path / ".autoloop" / "workflows" / "single_review.py"
    single_file.write_text(
        'raise AssertionError("single-file workflow should not import during list")\n',
        encoding="utf-8",
    )

    exit_code = cli.main(["workflows", "list", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    payload_by_name = {entry["name"]: entry for entry in payload}
    assert payload_by_name["manifest_review"] == {
        "aliases": ["manifest_alias"],
        "authoring_shape": "manifest_package",
        "description": "Workflow test package.",
        "manifest_present": True,
        "name": "manifest_review",
        "package_folder": str(tmp_path / ".autoloop" / "workflows" / "manifest_review"),
        "source_path": str(tmp_path / ".autoloop" / "workflows" / "manifest_review" / "workflow.py"),
        "source_root_kind": "workspace",
        "shadowed": False,
        "shadowed_by": None,
        "title": "Manifest Review",
    }
    assert payload_by_name["single_review"] == {
        "aliases": [],
        "authoring_shape": "single_file",
        "description": "",
        "manifest_present": False,
        "name": "single_review",
        "package_folder": str(tmp_path / ".autoloop" / "workflows"),
        "source_path": str(single_file),
        "source_root_kind": "workspace",
        "shadowed": False,
        "shadowed_by": None,
        "title": "Single Review",
    }
    assert any(entry["source_root_kind"] == "package" for entry in payload)


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


class Params(BaseModel):
    output_dir: Path = Path("reports")
    requested_at: datetime = datetime.fromisoformat("{requested_at.isoformat()}")
    mode: ReviewMode = ReviewMode.strict
""".strip(),
    )

    show_exit = cli.main(["workflows", "show", "typed_review", "--workspace", str(tmp_path)])
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
    assert show_payload["parameters_model"].endswith("Params")

    run_exit = cli.main(
        [
            "run",
            "typed_review",
            "task-json",
            "--workspace",
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
            "--workspace",
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
            "--workspace",
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
            "--workspace",
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
                "--workspace",
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


class Params(BaseModel):
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
            "--workspace",
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
    assert run_output["status"] == "awaiting_input"
    assert run_output["awaiting_input"] is True
    assert run_output["pending_input"]["question"] == "What value?"
    run_id = run_output["run_id"]

    run_dir = tmp_path / ".autoloop" / "tasks" / "task-42" / "wf_review" / "runs" / run_id
    assert len(list((run_dir.parent).iterdir())) == 1

    show_exit = cli.main(["runs", "show", "review", "task-42", "--workspace", str(tmp_path)])
    show_output = json.loads(capsys.readouterr().out)

    assert show_exit == 0
    assert show_output["run_id"] == run_id
    assert show_output["status"] == "awaiting_input"
    assert show_output["resumable"] is True
    assert show_output["awaiting_input"] is True
    assert show_output["workflow_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}
    assert show_output["pending_input"]["question"] == "What value?"

    list_exit = cli.main(["runs", "list", "--workflow", "reviewer", "--task", "task-42", "--workspace", str(tmp_path)])
    list_output = json.loads(capsys.readouterr().out)

    assert list_exit == 0
    assert len(list_output) == 1
    assert list_output[0]["run_id"] == run_id
    assert list_output[0]["awaiting_input"] is True

    logs_exit = cli.main(["logs", "review", "task-42", "--workspace", str(tmp_path)])
    logs_output = capsys.readouterr().out

    assert logs_exit == 0
    assert '"event_type": "run_started"' in logs_output

    raw_logs_exit = cli.main(["logs", "review", "task-42", "--workspace", str(tmp_path), "--raw"])
    raw_logs_captured = capsys.readouterr()

    assert raw_logs_exit == cli.EXIT_RESOLUTION_ERROR
    assert "raw log output is missing" in raw_logs_captured.err

    resume_exit = cli.main(
        ["resume", "review", "task-42", "--workspace", str(tmp_path), "--no-git"],
        provider_factory=_provider_factory,
    )
    resume_output = json.loads(capsys.readouterr().out)

    assert resume_exit == 0
    assert resume_output["run_id"] == run_id
    assert resume_output["status"] == "awaiting_input"
    assert len(list((run_dir.parent).iterdir())) == 1

    answer_exit = cli.main(
        ["answer", "review", "task-42", "--workspace", str(tmp_path), "--answer", "Use OAuth", "--no-git"],
        provider_factory=_provider_factory,
    )
    answer_output = json.loads(capsys.readouterr().out)

    assert answer_exit == 0
    assert answer_output["run_id"] == run_id
    assert answer_output["status"] == "success"
    assert answer_output["awaiting_input"] is False
    assert len(list((run_dir.parent).iterdir())) == 1

    final_show_exit = cli.main(["runs", "show", "reviewer", "task-42", "--workspace", str(tmp_path)])
    final_show = json.loads(capsys.readouterr().out)
    result_payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))

    assert final_show_exit == 0
    assert final_show["status"] == "success"
    assert final_show["awaiting_input"] is False
    assert result_payload["answer"] == "Use OAuth"
    assert result_payload["workflow_params"] == {"mode": "focused", "reviewers": ["alice", "bob"]}


def test_cli_runs_list_filters_legacy_paused_run_metadata_as_awaiting_input(
    tmp_path: Path,
    capsys,
) -> None:
    _write_workflow_package(
        tmp_path,
        "review_workflow",
        workflow_name="review",
        class_name="ReviewWorkflow",
    )

    run_dir = tmp_path / ".autoloop" / "tasks" / "task-legacy" / "wf_review" / "runs" / "run-legacy"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "created_at": "2026-04-24T06:00:00+00:00",
                "run_id": "run-legacy",
                "status": "paused",
                "task_id": "task-legacy",
                "updated_at": "2026-04-24T06:03:00+00:00",
                "workflow_name": "review",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "runs",
            "list",
            "--workflow",
            "review",
            "--task",
            "task-legacy",
            "--status",
            "awaiting_input",
            "--workspace",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == [
        {
            "awaiting_input": True,
            "created_at": "2026-04-24T06:00:00+00:00",
            "resumable": False,
            "run_id": "run-legacy",
            "status": "awaiting_input",
            "task_id": "task-legacy",
            "updated_at": "2026-04-24T06:03:00+00:00",
            "workflow": "review",
        }
    ]


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
        ["run", "review", "task-runs", "--workspace", str(tmp_path), "--message", "First request", "--no-git"],
        provider_factory=_provider_factory,
    )
    first_run = json.loads(capsys.readouterr().out)
    second_exit = cli.main(
        ["run", "review", "task-runs", "--workspace", str(tmp_path), "--message", "Second request", "--no-git"],
        provider_factory=_provider_factory,
    )
    second_run = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert second_exit == 0
    assert first_run["run_id"] != second_run["run_id"]

    latest_show_exit = cli.main(["runs", "show", "review", "task-runs", "--workspace", str(tmp_path)])
    latest_show = json.loads(capsys.readouterr().out)

    assert latest_show_exit == 0
    assert latest_show["run_id"] == second_run["run_id"]
    assert latest_show["status"] == "awaiting_input"

    latest_resume_exit = cli.main(
        ["resume", "review", "task-runs", "--workspace", str(tmp_path), "--no-git"],
        provider_factory=_provider_factory,
    )
    latest_resume = json.loads(capsys.readouterr().out)

    assert latest_resume_exit == 0
    assert latest_resume["run_id"] == second_run["run_id"]
    assert latest_resume["status"] == "awaiting_input"

    explicit_answer_exit = cli.main(
        [
            "answer",
            "review",
            "task-runs",
            "--workspace",
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
            "--workspace",
            str(tmp_path),
            "--run-id",
            second_run["run_id"],
        ]
    )
    latest_run_state = json.loads(capsys.readouterr().out)

    assert latest_run_state_exit == 0
    assert latest_run_state["run_id"] == second_run["run_id"]
    assert latest_run_state["status"] == "awaiting_input"


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
        ["run", "no_params", "task-1", "--workspace", str(tmp_path), "--message", "hello", "-wf", "mode", "strict"],
        provider_factory=_provider_factory,
    )
    captured = capsys.readouterr()

    assert exit_code == cli.EXIT_USAGE_ERROR
    assert "does not declare Params" in captured.err

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
            "--workspace",
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
        ["run", "strict_review", "task-1", "--workspace", str(tmp_path), "--message", "hello", "-wf", "unknown", "x"],
        provider_factory=_provider_factory,
    )
    unknown_captured = capsys.readouterr()

    assert unknown_exit == cli.EXIT_USAGE_ERROR
    assert "unknown workflow parameter 'unknown'" in unknown_captured.err


@pytest.mark.parametrize(
    ("shape", "expected_relpaths"),
    [
        ("single", (".autoloop/workflows/child_workflow.py",)),
        ("flow-specs", (".autoloop/workflows/child_workflow/flow.py", ".autoloop/workflows/child_workflow/specs.py")),
        (
            "package",
            (
                ".autoloop/workflows/child_workflow/flow.py",
                ".autoloop/workflows/child_workflow/specs.py",
                ".autoloop/workflows/child_workflow/__init__.py",
                ".autoloop/workflows/child_workflow/workflow.toml",
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
    exit_code = cli.main(["init", "workflow", "child_workflow", "--shape", shape, "--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["name"] == "child_workflow"
    assert payload["workflow_class"] == "ChildWorkflow"
    assert payload["shape"] == shape
    for relative_path in expected_relpaths:
        assert (tmp_path / relative_path).exists()

    source_path = (
        tmp_path / ".autoloop" / "workflows" / "child_workflow.py"
        if shape == "single"
        else tmp_path / ".autoloop" / "workflows" / "child_workflow" / "flow.py"
    )
    source = source_path.read_text(encoding="utf-8")
    _assert_bootstrap_scaffold_contract(source)

    if shape == "package":
        assert (tmp_path / ".autoloop" / "workflows" / "child_workflow" / "prompts" / "README.md").exists()
        assert (tmp_path / ".autoloop" / "workflows" / "child_workflow" / "assets" / ".gitkeep").exists()
    elif shape == "flow-specs":
        package_dir = tmp_path / ".autoloop" / "workflows" / "child_workflow"
        assert not (package_dir / "__init__.py").exists()
        assert not (package_dir / "workflow.toml").exists()
        assert not (package_dir / "prompts").exists()
        assert not (package_dir / "assets").exists()
    else:
        assert not (tmp_path / ".autoloop" / "workflows" / "child_workflow").exists()

    compiled = compile_workflow(resolve_workflow_reference(tmp_path, "child_workflow").workflow_cls)
    assert compiled.workflow_name == "child_workflow"
    _assert_compiled_bootstrap_contract(compiled)

    duplicate_exit = cli.main(["init", "workflow", "child_workflow", "--shape", shape, "--workspace", str(tmp_path)])
    duplicate = capsys.readouterr()

    assert duplicate_exit == cli.EXIT_USAGE_ERROR
    assert "already exists" in duplicate.err


def test_cli_init_workflow_defaults_to_package_shape(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(["init", "workflow", "child_workflow", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["shape"] == "package"
    flow_path = tmp_path / ".autoloop" / "workflows" / "child_workflow" / "flow.py"
    assert flow_path.exists()
    assert (tmp_path / ".autoloop" / "workflows" / "child_workflow" / "specs.py").exists()
    assert (tmp_path / ".autoloop" / "workflows" / "child_workflow" / "workflow.toml").exists()
    _assert_bootstrap_scaffold_contract(flow_path.read_text(encoding="utf-8"))

    compiled = compile_workflow(resolve_workflow_reference(tmp_path, "child_workflow").workflow_cls)
    assert compiled.workflow_name == "child_workflow"
    _assert_compiled_bootstrap_contract(compiled)
