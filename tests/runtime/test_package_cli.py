from __future__ import annotations

import json
from pathlib import Path

from autoloop_v3.runtime import cli


class _UnusedProvider:
    def run_producer(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"producer should not run for system-only workflow: {request!r}")

    def run_verifier(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"verifier should not run for system-only workflow: {request!r}")

    def run_llm(self, request):  # pragma: no cover - defensive
        raise AssertionError(f"llm should not run for system-only workflow: {request!r}")


def _provider_factory(**_: object) -> _UnusedProvider:
    return _UnusedProvider()


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

from workflow import GLOBAL, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


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

from workflow import GLOBAL, PAUSE, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event


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

    for forbidden in ("--class-name", "--request-text", "--resume", "provider-factory", " exec "):
        assert forbidden not in help_text


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
    assert payload["parameters_supported"] is True
    assert payload["workflow_class"] == "ReviewWorkflow"
    assert payload["parameters"] == [
        {"default": "strict", "name": "mode", "repeated": False, "required": False, "type": "str"},
        {"default": [], "name": "reviewers", "repeated": True, "required": False, "type": "list[str]"},
    ]


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
    assert '"event": "run_started"' in logs_output

    raw_logs_exit = cli.main(["logs", "review", "task-42", "--root", str(tmp_path), "--raw"])
    raw_logs_captured = capsys.readouterr()

    assert raw_logs_exit == cli.EXIT_RESOLUTION_ERROR
    assert "raw log output is missing" in raw_logs_captured.err

    resume_exit = cli.main(
        ["resume", "review", "task-42", "--root", str(tmp_path)],
        provider_factory=_provider_factory,
    )
    resume_output = json.loads(capsys.readouterr().out)

    assert resume_exit == 0
    assert resume_output["run_id"] == run_id
    assert resume_output["status"] == "paused"
    assert len(list((run_dir.parent).iterdir())) == 1

    answer_exit = cli.main(
        ["answer", "review", "task-42", "--root", str(tmp_path), "--answer", "Use OAuth"],
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


def test_cli_init_workflow_scaffolds_package_and_rejects_duplicates(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = cli.main(["init", "workflow", "child_workflow", "--root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    package_dir = tmp_path / "workflows" / "child_workflow"
    assert payload["name"] == "child_workflow"
    assert payload["workflow_class"] == "ChildWorkflow"
    assert package_dir.is_dir()
    assert (package_dir / "__init__.py").exists()
    assert (package_dir / "workflow.py").exists()
    assert (package_dir / "workflow.toml").exists()
    assert (package_dir / "prompts" / "README.md").exists()
    assert (package_dir / "assets" / ".gitkeep").exists()

    duplicate_exit = cli.main(["init", "workflow", "child_workflow", "--root", str(tmp_path)])
    duplicate = capsys.readouterr()

    assert duplicate_exit == cli.EXIT_USAGE_ERROR
    assert "already exists" in duplicate.err
