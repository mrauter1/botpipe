from __future__ import annotations

from tests.unit._stdlib_and_extensions_shared import _git
from tests.unit._stdlib_and_extensions_shared import *

TEST_USER_EMAIL = "botlane@example.com"
TEST_USER_NAME = "Botlane Tests"

def test_session_paths_extraction_returns_only_the_declared_strategy() -> None:
    class Strategy:
        def path_for(self, run_dir: Path, ref_name: str, scope: str | None) -> Path:
            return run_dir / "custom" / f"{ref_name}.json"

    strategy = Strategy()
    extension = SessionPaths(strategy=strategy)

    assert extract_session_path_strategy((extension,)) is strategy
    with pytest.raises(ValueError, match="multiple SessionPaths"):
        extract_session_path_strategy((extension, SessionPaths(strategy=Strategy())))
def test_git_filters_preserve_raw_delta_when_scoping_to_the_workflow_workspace(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    task_folder = repo_root / STATE_DIRNAME / "tasks" / "task-1"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    binding = RunBinding(
        root=repo_root,
        task_id="task-1",
        run_id="run-1",
        workflow_name="ExampleWorkflow",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=repo_root / "workflows" / "example",
    )
    raw_delta = GitDelta(
        (
            GitChange(status="M", path=f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md"),
            GitChange(status="M", path=f"{STATE_DIRNAME}/tasks/task-1/shared.md"),
            GitChange(status="M", path="README.md"),
        )
    )

    prefix = workflow_workspace_pathspec(repo_root, binding)
    scoped = filter_delta_by_prefixes(raw_delta, (prefix,) if prefix else ())
    narrowed = filter_delta_by_pathspecs(scoped, (f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md",))

    assert raw_delta.changes == (
        GitChange(status="M", path=f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md"),
        GitChange(status="M", path=f"{STATE_DIRNAME}/tasks/task-1/shared.md"),
        GitChange(status="M", path="README.md"),
    )
    assert tuple(change.path for change in scoped.changes) == (f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md",)
    assert tuple(change.path for change in narrowed.changes) == (f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md",)
    assert delta_pathspecs(narrowed) == (f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md",)
def test_git_repo_commit_scope_uses_filtered_delta_without_rewriting_raw_delta(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    task_folder = repo_root / STATE_DIRNAME / "tasks" / "task-1"
    workflow_folder = task_folder / "wf_example"
    workflow_note = workflow_folder / "notes.md"
    workflow_note.parent.mkdir(parents=True, exist_ok=True)
    workflow_note.write_text("tracked workflow note\n", encoding="utf-8")
    shared_task_note = task_folder / "shared.md"
    shared_task_note.write_text("outside workflow scope\n", encoding="utf-8")
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
        workflow_folder=workflow_folder,
        run_folder=workflow_folder / "runs" / "run-1",
        package_folder=repo_root / "workflows" / "example",
    )
    prefix = workflow_workspace_pathspec(repo.root, binding)
    scoped = filter_delta_by_prefixes(raw_delta, (prefix,) if prefix else ())

    commit_sha = repo.commit(GitCommitPlan(message="track workflow workspace"), pathspecs=delta_pathspecs(scoped))

    assert commit_sha
    assert {change.path for change in raw_delta.changes} == {
        f"{STATE_DIRNAME}/tasks/task-1/wf_example/notes.md",
        f"{STATE_DIRNAME}/tasks/task-1/shared.md",
        "README.md",
    }
    assert {change.path for change in repo.raw_delta().changes} == {
        f"{STATE_DIRNAME}/tasks/task-1/shared.md",
        "README.md",
    }
def test_git_repo_commit_ignores_empty_selected_scope_when_unrelated_changes_are_pre_staged(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
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
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    commit_sha = repo.commit(GitCommitPlan(message="empty-tracking-checkpoint", allow_empty=True), pathspecs=())

    assert commit_sha
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "empty-tracking-checkpoint"
    assert repo.staged_paths() == ()
def test_git_repo_status_porcelain_and_is_dirty_report_workspace_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    readme = repo_root / "README.md"
    readme.write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None
    assert repo.status_porcelain() == ""
    assert repo.is_dirty() is False

    readme.write_text("dirty\n", encoding="utf-8")

    assert "README.md" in repo.status_porcelain()
    assert repo.is_dirty() is True
def test_git_repo_commit_all_tracks_untracked_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    (repo_root / "notes.txt").write_text("tracked by commit_all\n", encoding="utf-8")

    commit_sha, created_commit = repo.commit_all("track entire workspace")

    assert created_commit is True
    assert commit_sha == repo.head()
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "track entire workspace"
    assert _git(repo_root, "show", "--pretty=", "--name-only", "HEAD").splitlines() == ["notes.txt"]
def test_git_repo_commit_all_stages_tracked_and_untracked_workspace_changes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    readme = repo_root / "README.md"
    readme.write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    readme.write_text("updated\n", encoding="utf-8")
    (repo_root / "notes.txt").write_text("new file\n", encoding="utf-8")

    commit_sha, created_commit = repo.commit_all("snapshot full workspace")

    assert created_commit is True
    assert commit_sha == repo.head()
    assert set(_git(repo_root, "show", "--pretty=", "--name-only", "HEAD").splitlines()) == {"README.md", "notes.txt"}
def test_git_repo_commit_all_returns_current_head_without_empty_commit(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", TEST_USER_EMAIL)
    _git(repo_root, "config", "user.name", TEST_USER_NAME)
    (repo_root / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "baseline")

    repo = GitRepo.discover(repo_root)
    assert repo is not None

    baseline_head = repo.head()
    commit_sha, created_commit = repo.commit_all("noop commit_all")

    assert created_commit is False
    assert commit_sha == baseline_head
    assert repo.head() == baseline_head
    assert _git(repo_root, "log", "-1", "--pretty=%s").strip() == "baseline"
def test_git_repo_raw_delta_preserves_two_column_git_status_semantics(tmp_path: Path) -> None:
    staged_repo = tmp_path / "staged"
    staged_repo.mkdir()
    _git(staged_repo, "init")
    _git(staged_repo, "config", "user.email", TEST_USER_EMAIL)
    _git(staged_repo, "config", "user.name", TEST_USER_NAME)
    staged_file = staged_repo / "file.txt"
    staged_file.write_text("base\n", encoding="utf-8")
    _git(staged_repo, "add", "file.txt")
    _git(staged_repo, "commit", "-m", "baseline")
    staged_file.write_text("staged\n", encoding="utf-8")
    _git(staged_repo, "add", "file.txt")

    unstaged_repo = tmp_path / "unstaged"
    unstaged_repo.mkdir()
    _git(unstaged_repo, "init")
    _git(unstaged_repo, "config", "user.email", TEST_USER_EMAIL)
    _git(unstaged_repo, "config", "user.name", TEST_USER_NAME)
    unstaged_file = unstaged_repo / "file.txt"
    unstaged_file.write_text("base\n", encoding="utf-8")
    _git(unstaged_repo, "add", "file.txt")
    _git(unstaged_repo, "commit", "-m", "baseline")
    unstaged_file.write_text("unstaged\n", encoding="utf-8")

    staged_delta = GitRepo.discover(staged_repo).raw_delta()
    unstaged_delta = GitRepo.discover(unstaged_repo).raw_delta()

    assert staged_delta.changes[0].status == "M "
    assert unstaged_delta.changes[0].status == " M"
