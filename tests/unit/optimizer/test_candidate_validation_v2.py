from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from botpipe_optimizer.candidate_surfaces import (
    derive_surface_manifest,
    validate_surface_manifest,
)
from botpipe_optimizer.execution_trees import (
    allocate_owned_directory,
    assert_execution_arm_unchanged,
    capture_execution_tree,
    cleanup_owned_directory,
    materialize_execution_arm,
    snapshot_execution_arm,
)
from botpipe_optimizer.processes import run_bounded_process
from botpipe.core.surface_identity import derive_workflow_surface_manifest
from botpipe.runtime.inspection import inspect_workflow_reference


def test_t03_surface_manifest_rejects_forged_derived_fields(tmp_path: Path) -> None:
    root = tmp_path / "surface"
    root.mkdir()
    (root / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    boundary = {"workflow_name": "demo", "package_root_relative_path": "."}
    manifest = derive_surface_manifest(
        root,
        expected_root=root,
        boundary=boundary,
        surface_kind="candidate",
    )
    validated = validate_surface_manifest(
        manifest,
        expected_root=root,
        expected_boundary=boundary,
        expected_surface_kind="candidate",
    )
    assert validated["surface_id"] == manifest["surface_id"]

    other_root = tmp_path / "other-surface"
    other_root.mkdir()
    (other_root / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    for field, false_value in (
        ("root", str(other_root)),
        ("file_count", 99),
        ("size_bytes", 0),
        ("surface_id", "sha256:" + "0" * 64),
        ("relative_paths", ["forged.py"]),
        ("mode_semantics", "forged-mode-semantics"),
    ):
        forged = dict(manifest)
        forged[field] = false_value
        with pytest.raises(ValueError, match=field):
            validate_surface_manifest(
                forged,
                expected_root=root,
                expected_boundary=boundary,
                expected_surface_kind="candidate",
            )

    for field, false_value in (
        ("surface_sha256", "0" * 64),
        ("size_bytes", manifest["files"][0]["size_bytes"] + 1),
        ("executable", not manifest["files"][0]["executable"]),
    ):
        forged = dict(manifest)
        forged["files"] = [dict(entry) for entry in manifest["files"]]
        forged["files"][0][field] = false_value
        with pytest.raises(ValueError, match="files"):
            validate_surface_manifest(
                forged,
                expected_root=root,
                expected_boundary=boundary,
                expected_surface_kind="candidate",
            )


def test_runtime_and_optimizer_derive_the_same_workflow_surface_id(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    capability = inspect_workflow_reference(repo_root, "devloop")
    runtime_manifest = derive_workflow_surface_manifest(repo_root, capability)
    copied_root = tmp_path / "copied-surface"
    source_map: dict[str, Path] = {}
    for entry in runtime_manifest["files"]:
        relative = entry["relative_path"]
        source = Path(entry["surface_path"])
        target = copied_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_map[relative] = source
    optimizer_manifest = derive_surface_manifest(
        copied_root,
        expected_root=copied_root,
        boundary={
            key: value
            for key, value in runtime_manifest["boundary"].items()
            if key != "surface_kind"
        },
        surface_kind="workflow",
        authoritative_sources=source_map,
    )
    assert optimizer_manifest["surface_id"] == runtime_manifest["surface_id"]


def test_t04_execution_arm_detects_new_file_and_source_anchor_drift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()
    (source / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    frozen = capture_execution_tree(source, staging)
    arm = materialize_execution_arm(frozen, staging)
    expected = snapshot_execution_arm(arm)
    try:
        (arm.root / "created_during_check.py").write_text(
            "MUTATION = True\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="changed during test"):
            assert_execution_arm_unchanged(expected, arm.root, phase="test")
    finally:
        cleanup_owned_directory(
            arm.root,
            owned_parent=arm.owned_parent,
            ownership_token=arm.ownership_token,
        )
        cleanup_owned_directory(
            frozen.root,
            owned_parent=frozen.owned_parent,
            ownership_token=frozen.ownership_token,
        )


def test_validation_entrypoint_rejects_forged_surface_id_before_launch(
    tmp_path: Path,
) -> None:
    from botpipe_optimizer.candidate_validation import validate_frozen_candidate

    source = tmp_path / "source"
    staging = tmp_path / "staging"
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    for root in (source, staging, baseline_root, candidate_root):
        root.mkdir()
    for root in (source, baseline_root, candidate_root):
        (root / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    boundary = {"workflow_name": "demo"}
    baseline = derive_surface_manifest(
        baseline_root,
        expected_root=baseline_root,
        boundary=boundary,
        surface_kind="baseline",
    )
    candidate = derive_surface_manifest(
        candidate_root,
        expected_root=candidate_root,
        boundary=boundary,
        surface_kind="candidate",
    )
    candidate["surface_id"] = "sha256:" + "0" * 64
    frozen = capture_execution_tree(source, staging)
    try:
        with pytest.raises(ValueError, match="surface_id"):
            validate_frozen_candidate(
                frozen,
                baseline_surface_manifest=baseline,
                candidate_surface_manifest=candidate,
                expected_baseline_root=baseline_root,
                expected_candidate_root=candidate_root,
                expected_boundary=boundary,
                baseline_surface_kind="baseline",
                candidate_surface_kind="candidate",
                workflow_refs=["demo"],
                staging_parent=staging,
            )
    finally:
        cleanup_owned_directory(
            frozen.root,
            owned_parent=frozen.owned_parent,
            ownership_token=frozen.ownership_token,
        )


def test_isolated_python_check_rejects_new_module_loaded_from_outside_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "staged"
    outside = tmp_path / "outside"
    probe = tmp_path / "probe"
    root.mkdir()
    outside.mkdir()
    probe.mkdir()
    (outside / "unrelated_helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (root / "check.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(outside)!r})\n"
        "import unrelated_helper\n"
        "assert unrelated_helper.VALUE == 42\n",
        encoding="utf-8",
    )
    config = probe / "config.json"
    result_path = probe / "result.json"
    config.write_text(
        json.dumps(
            {
                "staged_root": str(root),
                "dependency_roots": [],
                "project_prefixes": [],
                "mode": "python",
                "argv": [sys.executable, "check.py"],
            }
        ),
        encoding="utf-8",
    )
    bootstrap = (
        Path(__file__).parents[3] / "botpipe_optimizer" / "_isolation_bootstrap.py"
    )
    process = run_bounded_process(
        [sys.executable, "-I", "-S", str(bootstrap), str(config), str(result_path)],
        cwd=root,
        timeout_seconds=10,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert process.exit_code == 1
    assert result["ok"] is False
    assert "unapproved root" in result["error"]


def test_t16_tree_limits_symlinks_and_logs_are_bounded(tmp_path: Path) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()
    (source / "one.py").write_text("1\n", encoding="utf-8")
    (source / "two.py").write_text("2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_execution_tree_files=1"):
        capture_execution_tree(source, staging, max_files=1)

    (source / "two.py").unlink()
    try:
        (source / "escape.py").symlink_to(tmp_path / "outside.py")
    except OSError:
        pass  # Some Windows runners do not grant symlink creation privilege.
    else:
        with pytest.raises(ValueError, match="symlink"):
            capture_execution_tree(source, staging)
        (source / "escape.py").unlink()
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            "import sys;sys.stdout.write('x'*5000);sys.stderr.write('y'*5000)",
        ],
        cwd=source,
        timeout_seconds=5,
        max_stream_bytes=128,
    )
    assert result.exit_code == 0
    assert result.stdout == "x" * 128
    assert result.stderr == "y" * 128
    assert result.stdout_truncated and result.stderr_truncated


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO acceptance")
def test_t16_execution_tree_rejects_fifo_before_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()
    (source / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    os.mkfifo(source / "events.fifo")

    with pytest.raises(ValueError, match="special file: events.fifo"):
        capture_execution_tree(source, staging)

    assert list(staging.iterdir()) == []


@pytest.mark.parametrize("leader_exits", [False, True])
def test_t16_bounded_process_reaps_children_on_timeout_and_normal_leader_exit(
    tmp_path: Path,
    leader_exits: bool,
) -> None:
    child_pid_path = tmp_path / "child.pid"
    leader_tail = "" if leader_exits else ";time.sleep(30)"
    program = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
        f"{leader_tail}"
    )
    result = run_bounded_process(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        timeout_seconds=2 if leader_exits else 0.3,
        termination_grace_seconds=0.2,
    )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while _process_is_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _process_is_running(child_pid)
    assert result.timed_out is (not leader_exits)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object acceptance")
def test_windows_job_object_timeout_reaps_descendant(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "windows-child.pid"
    program = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid));"
        "time.sleep(30)"
    )
    result = run_bounded_process(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        timeout_seconds=2,
        termination_grace_seconds=0.5,
    )
    assert result.timed_out is True
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 3
    while _process_is_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _process_is_running(child_pid)


def test_t19_cleanup_refuses_unowned_overlapping_and_wrong_marker_paths(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "owned-parent"
    parent.mkdir()
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    preexisting = parent / "preexisting"
    preexisting.mkdir()
    (preexisting / "data.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="not owned"):
        cleanup_owned_directory(
            preexisting, owned_parent=parent, ownership_token="wrong"
        )
    with pytest.raises(ValueError, match="child"):
        cleanup_owned_directory(parent, owned_parent=parent, ownership_token="wrong")

    allocation, token = allocate_owned_directory(parent, prefix="test-")
    with pytest.raises(ValueError, match="marker does not match"):
        cleanup_owned_directory(
            allocation, owned_parent=parent, ownership_token="wrong"
        )
    cleanup_owned_directory(allocation, owned_parent=parent, ownership_token=token)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert (preexisting / "data.txt").is_file()


@pytest.mark.parametrize("workflow_name", ["devloop", "ralph_loop"])
def test_t01_invalid_candidate_cannot_hide_behind_imported_original(
    tmp_path: Path,
    workflow_name: str,
) -> None:
    # Importing the authoritative module here reproduces the historical module-cache bug.
    importlib.import_module(f"botpipe.workflows.{workflow_name}.workflow")

    from botpipe_optimizer.candidate_validation import validate_frozen_candidate

    repo_root = Path(__file__).resolve().parents[3]
    staging = tmp_path / "staging"
    staging.mkdir()
    relative = f"botpipe/workflows/{workflow_name}/workflow.py"
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    (baseline_root / relative).parent.mkdir(parents=True)
    (candidate_root / relative).parent.mkdir(parents=True)
    shutil.copy2(repo_root / relative, baseline_root / relative)
    (candidate_root / relative).write_text(
        "this is invalid python !!!\n", encoding="utf-8"
    )
    boundary = {
        "workflow_name": workflow_name,
        "package_root_relative_path": f"botpipe/workflows/{workflow_name}",
    }
    baseline = derive_surface_manifest(
        baseline_root,
        expected_root=baseline_root,
        boundary=boundary,
        surface_kind="baseline",
    )
    candidate = derive_surface_manifest(
        candidate_root,
        expected_root=candidate_root,
        boundary=boundary,
        surface_kind="candidate",
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "README.md").write_text("consumer project\n", encoding="utf-8")
    installed_package = tmp_path / "installed" / "botpipe"
    shutil.copytree(
        repo_root / "botpipe",
        installed_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    frozen = capture_execution_tree(
        consumer,
        staging,
        selected_package_root=installed_package,
        selected_package_import_path="botpipe",
    )
    fake_site_packages = tmp_path / "fake-site-packages"
    fake_site_packages.mkdir()
    (fake_site_packages / "botpipe-editable.pth").write_text(
        str(repo_root) + "\n",
        encoding="utf-8",
    )
    dependency_roots = [fake_site_packages, *_installed_dependency_roots()]
    try:
        result = validate_frozen_candidate(
            frozen,
            baseline_surface_manifest=baseline,
            candidate_surface_manifest=candidate,
            expected_baseline_root=baseline_root,
            expected_candidate_root=candidate_root,
            expected_boundary=boundary,
            baseline_surface_kind="baseline",
            candidate_surface_kind="candidate",
            workflow_refs=[workflow_name],
            staging_parent=staging,
            target_test_argv=[sys.executable, "-c", "raise SystemExit(0)"],
            dependency_roots=dependency_roots,
        )
        assert result.success is False
        assert result.checks[0].kind == "compile_probe"
        assert len(result.checks) == 1
    finally:
        cleanup_owned_directory(
            frozen.root,
            owned_parent=frozen.owned_parent,
            ownership_token=frozen.ownership_token,
        )


def test_t02_valid_candidate_behavior_and_origins_come_from_staged_tree(
    tmp_path: Path,
) -> None:
    from botpipe_optimizer.candidate_validation import validate_frozen_candidate

    repo_root = Path(__file__).resolve().parents[3]
    staging = tmp_path / "staging"
    staging.mkdir()
    workflow_relative = "botpipe/workflows/devloop/workflow.py"
    check_relative = "checks with spaces/check candidate.py"
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    (baseline_root / workflow_relative).parent.mkdir(parents=True)
    (candidate_root / workflow_relative).parent.mkdir(parents=True)
    authoritative = (repo_root / workflow_relative).read_text(encoding="utf-8")
    (baseline_root / workflow_relative).write_text(authoritative, encoding="utf-8")
    (candidate_root / workflow_relative).write_text(
        authoritative.replace("AUDIT_RESULT_VERSION = 1", "AUDIT_RESULT_VERSION = 2"),
        encoding="utf-8",
    )
    (candidate_root / check_relative).parent.mkdir(parents=True)
    (candidate_root / check_relative).write_text(
        "from botpipe.workflows.devloop.workflow import AUDIT_RESULT_VERSION\n"
        "assert AUDIT_RESULT_VERSION == 2\n",
        encoding="utf-8",
    )
    boundary = {
        "workflow_name": "devloop",
        "package_root_relative_path": "botpipe/workflows/devloop",
    }
    baseline = derive_surface_manifest(
        baseline_root,
        expected_root=baseline_root,
        boundary=boundary,
        surface_kind="baseline",
    )
    candidate = derive_surface_manifest(
        candidate_root,
        expected_root=candidate_root,
        boundary=boundary,
        surface_kind="candidate",
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "README.md").write_text("consumer project\n", encoding="utf-8")
    installed_package = tmp_path / "installed" / "botpipe"
    shutil.copytree(
        repo_root / "botpipe",
        installed_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    frozen = capture_execution_tree(
        consumer,
        staging,
        selected_package_root=installed_package,
        selected_package_import_path="botpipe",
    )
    fake_site_packages = tmp_path / "fake-site-packages"
    fake_site_packages.mkdir()
    (fake_site_packages / "botpipe-editable.pth").write_text(
        str(repo_root) + "\n",
        encoding="utf-8",
    )
    dependency_roots = [fake_site_packages, *_installed_dependency_roots()]
    try:
        result = validate_frozen_candidate(
            frozen,
            baseline_surface_manifest=baseline,
            candidate_surface_manifest=candidate,
            expected_baseline_root=baseline_root,
            expected_candidate_root=candidate_root,
            expected_boundary=boundary,
            baseline_surface_kind="baseline",
            candidate_surface_kind="candidate",
            allowed_added_exact_paths=[check_relative],
            dependency_roots=dependency_roots,
            workflow_refs=["devloop"],
            staging_parent=staging,
            target_test_argv=[sys.executable, check_relative],
        )
        assert result.success is True
        assert result.derived_changes == tuple(
            sorted((check_relative, workflow_relative))
        )
        candidate_digests = {
            entry["relative_path"]: entry["surface_sha256"]
            for entry in candidate["files"]
        }
        assert (
            result.compiled_workflows[0]["source_sha256"]
            == candidate_digests[workflow_relative]
        )
        assert (
            Path(result.compiled_workflows[0]["source_path"])
            != repo_root / workflow_relative
        )
        project_origins = [
            entry["origin"]
            for check in result.checks
            if check.result is not None
            for entry in check.result.get("module_origins", [])
            if entry["module"] == "botpipe" or entry["module"].startswith("botpipe.")
        ]
        assert project_origins
        assert all(
            not Path(origin).is_relative_to(repo_root) for origin in project_origins
        )
        assert (repo_root / workflow_relative).read_text(
            encoding="utf-8"
        ) == authoritative
    finally:
        cleanup_owned_directory(
            frozen.root,
            owned_parent=frozen.owned_parent,
            ownership_token=frozen.ownership_token,
        )


def _process_is_running(process_id: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: the PID no longer exists.
                return False
            return (
                True  # Access denied or another unknown state is conservatively live.
            )
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path("/proc") / str(process_id) / "stat"
    if stat_path.is_file():
        fields = stat_path.read_text(encoding="utf-8").split()
        return len(fields) > 2 and fields[2] != "Z"
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    return True


def _installed_dependency_roots() -> list[Path]:
    return [
        Path(value).resolve()
        for value in sys.path
        if value
        and Path(value).is_dir()
        and (
            "site-packages" in Path(value).parts or "dist-packages" in Path(value).parts
        )
    ]
