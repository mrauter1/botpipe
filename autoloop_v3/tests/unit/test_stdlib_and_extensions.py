from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autoloop_v3.extensions.session_paths import SessionPaths, extract_session_path_strategy
from autoloop_v3.extensions.git.filters import (
    delta_pathspecs,
    filter_delta_by_pathspecs,
    filter_delta_by_prefixes,
    task_workspace_pathspec,
)
from autoloop_v3.extensions.git.policy import GitChange, GitCommitPlan, GitDelta
from autoloop_v3.extensions.git.repo import GitRepo
from autoloop_v3.stdlib import (
    PromptBundle,
    event_on_outcome_tags,
    global_routes,
    merge_transitions,
    pair_step,
    pause_on_outcome_tags,
)
from autoloop_v3.stdlib.state import SequenceCursor
from autoloop_v3.workflow import FAIL, GLOBAL, PAUSE, SUCCESS, PairStep
from autoloop_v3.workflow.extensions import RunBinding
from autoloop_v3.workflow.primitives import Event, Outcome


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def test_stdlib_modules_remain_pure_authoring_helpers() -> None:
    for relative_path in (
        "stdlib/control.py",
        "stdlib/prompts.py",
        "stdlib/steps.py",
        "stdlib/state/cursor.py",
    ):
        text = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")
        assert "autoloop_v3.runtime" not in text
        assert "autoloop_v3.workflows" not in text


def test_control_helpers_merge_routes_and_build_outcome_passthrough() -> None:
    step = object()
    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {step: {"done": SUCCESS}},
    )
    handler = event_on_outcome_tags("question", "blocked", "failed")

    assert transitions[GLOBAL] == {"question": PAUSE, "blocked": PAUSE, "failed": FAIL}
    assert transitions[step] == {"done": SUCCESS}
    assert handler(None, Outcome(raw_output="need help", tag="question", question="Clarify?")) == Event(
        "question",
        question="Clarify?",
    )
    assert handler(None, Outcome(raw_output="done", tag="done")) is None


def test_prompt_bundle_and_pair_step_compile_to_plain_prompt_and_step_objects() -> None:
    prompts = PromptBundle("prompts/plan").pair("producer.md", "verifier.md")
    step = pair_step(name="plan", prompts=prompts)

    assert isinstance(step, PairStep)
    assert step.producer.path == "prompts/plan/producer.md"
    assert step.verifier.path == "prompts/plan/verifier.md"


def test_sequence_cursor_advances_without_hidden_state() -> None:
    cursor = SequenceCursor.from_items(["phase-a", "phase-b"])

    assert cursor.current is None
    assert cursor.peek() == "phase-a"

    cursor = cursor.advance()
    assert cursor.current == "phase-a"
    assert cursor.peek() == "phase-b"

    cursor = cursor.advance()
    assert cursor.current == "phase-b"
    assert cursor.peek() is None
    assert cursor.advance() == cursor
    assert cursor.reset().current is None


def test_session_paths_extraction_returns_only_the_declared_strategy() -> None:
    class Strategy:
        def path_for(self, run_dir: Path, ref_name: str, scope: str | None) -> Path:
            return run_dir / "custom" / f"{ref_name}.json"

    strategy = Strategy()
    extension = SessionPaths(strategy=strategy)

    assert extract_session_path_strategy((extension,)) is strategy
    with pytest.raises(ValueError, match="multiple SessionPaths"):
        extract_session_path_strategy((extension, SessionPaths(strategy=Strategy())))


def test_git_filters_preserve_raw_delta_when_scoping_to_the_task_workspace(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    task_folder = repo_root / ".autoloop" / "tasks" / "task-1"
    run_folder = task_folder / "runs" / "run-1"
    binding = RunBinding(
        root=repo_root,
        task_id="task-1",
        run_id="run-1",
        workflow_name="ExampleWorkflow",
        task_folder=task_folder,
        run_folder=run_folder,
    )
    raw_delta = GitDelta(
        (
            GitChange(status="M", path=".autoloop/tasks/task-1/notes.md"),
            GitChange(status="M", path="README.md"),
        )
    )

    prefix = task_workspace_pathspec(repo_root, binding)
    scoped = filter_delta_by_prefixes(raw_delta, (prefix,) if prefix else ())
    narrowed = filter_delta_by_pathspecs(scoped, (".autoloop/tasks/task-1/notes.md",))

    assert raw_delta.changes == (
        GitChange(status="M", path=".autoloop/tasks/task-1/notes.md"),
        GitChange(status="M", path="README.md"),
    )
    assert tuple(change.path for change in scoped.changes) == (".autoloop/tasks/task-1/notes.md",)
    assert tuple(change.path for change in narrowed.changes) == (".autoloop/tasks/task-1/notes.md",)
    assert delta_pathspecs(narrowed) == (".autoloop/tasks/task-1/notes.md",)


def test_git_repo_commit_scope_uses_filtered_delta_without_rewriting_raw_delta(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "autoloop@example.com")
    _git(repo_root, "config", "user.name", "Autoloop Tests")
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    task_folder = repo_root / ".autoloop" / "tasks" / "task-1"
    task_note = task_folder / "notes.md"
    task_note.parent.mkdir(parents=True, exist_ok=True)
    task_note.write_text("tracked task note\n", encoding="utf-8")
    (repo_root / "README.md").write_text("changed outside task\n", encoding="utf-8")

    repo = GitRepo.discover(repo_root)
    assert repo is not None
    raw_delta = repo.raw_delta()
    binding = RunBinding(
        root=repo_root,
        task_id="task-1",
        run_id="run-1",
        workflow_name="ExampleWorkflow",
        task_folder=task_folder,
        run_folder=task_folder / "runs" / "run-1",
    )
    prefix = task_workspace_pathspec(repo.root, binding)
    scoped = filter_delta_by_prefixes(raw_delta, (prefix,) if prefix else ())

    commit_sha = repo.commit(GitCommitPlan(message="track task workspace"), pathspecs=delta_pathspecs(scoped))

    assert commit_sha
    assert {change.path for change in raw_delta.changes} == {
        ".autoloop/tasks/task-1/notes.md",
        "README.md",
    }
    assert {change.path for change in repo.raw_delta().changes} == {"README.md"}


def test_git_repo_commit_ignores_empty_selected_scope_when_unrelated_changes_are_pre_staged(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "autoloop@example.com")
    _git(repo_root, "config", "user.name", "Autoloop Tests")
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    (repo_root / "README.md").write_text("staged outside scope\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    commit_sha = repo.commit(GitCommitPlan(message="should-not-commit"), pathspecs=())

    assert commit_sha is None
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "baseline"
    assert repo.staged_paths() == ("README.md",)


def test_git_repo_commit_allows_explicit_empty_commit_for_empty_selected_scope(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "autoloop@example.com")
    _git(repo_root, "config", "user.name", "Autoloop Tests")
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    commit_sha = repo.commit(GitCommitPlan(message="empty-tracking-checkpoint", allow_empty=True), pathspecs=())

    assert commit_sha
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "empty-tracking-checkpoint"
    assert repo.staged_paths() == ()


def test_git_repo_raw_delta_preserves_two_column_git_status_semantics(tmp_path: Path) -> None:
    staged_repo = tmp_path / "staged"
    staged_repo.mkdir()
    _git(staged_repo, "init")
    _git(staged_repo, "config", "user.email", "autoloop@example.com")
    _git(staged_repo, "config", "user.name", "Autoloop Tests")
    staged_file = staged_repo / "file.txt"
    staged_file.write_text("base\n", encoding="utf-8")
    _git(staged_repo, "add", "file.txt")
    _git(staged_repo, "commit", "-m", "baseline")
    staged_file.write_text("staged\n", encoding="utf-8")
    _git(staged_repo, "add", "file.txt")

    unstaged_repo = tmp_path / "unstaged"
    unstaged_repo.mkdir()
    _git(unstaged_repo, "init")
    _git(unstaged_repo, "config", "user.email", "autoloop@example.com")
    _git(unstaged_repo, "config", "user.name", "Autoloop Tests")
    unstaged_file = unstaged_repo / "file.txt"
    unstaged_file.write_text("base\n", encoding="utf-8")
    _git(unstaged_repo, "add", "file.txt")
    _git(unstaged_repo, "commit", "-m", "baseline")
    unstaged_file.write_text("unstaged\n", encoding="utf-8")

    staged_delta = GitRepo.discover(staged_repo).raw_delta()
    unstaged_delta = GitRepo.discover(unstaged_repo).raw_delta()

    assert staged_delta.changes[0].status == "M "
    assert unstaged_delta.changes[0].status == " M"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout
