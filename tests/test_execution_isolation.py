from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from botpipe.journal import workspace_lock
from botpipe_optimizer.execution_trees import (
    allocate_owned_directory,
    assert_execution_arm_unchanged,
    capture_execution_tree,
    cleanup_owned_directory,
    materialize_execution_arm,
    snapshot_execution_arm,
    verify_frozen_execution_tree,
)
from botpipe_optimizer.processes import run_bounded_process
from botpipe_optimizer.surface_identity import (
    derive_surface_manifest,
    validate_surface_manifest,
)


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


def test_execution_tree_ignores_workspace_fence_while_owned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "workflow.py").write_text("VALUE = 1\n", encoding="utf-8")
    lock_name = ".botpipe-workspace.lock"
    with workspace_lock(source / lock_name) as fence:
        fence.seek(0)
        fence.write(b"first owner")
        fence.flush()
        frozen = capture_execution_tree(source, tmp_path / "staging")
        try:
            assert not (frozen.root / lock_name).exists()
            assert [record["path"] for record in frozen.source_records] == [
                "workflow.py"
            ]
            assert lock_name in frozen.manifest["boundary"]["exclusions"]
            fence.seek(0)
            fence.truncate()
            fence.write(b"next owner")
            fence.flush()
            verify_frozen_execution_tree(frozen)
        finally:
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
        Path(__file__).parents[1] / "botpipe_optimizer" / "_isolation_bootstrap.py"
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


def test_execution_tree_rejects_aba_source_change_during_copy(
    tmp_path: Path, monkeypatch
) -> None:
    from botpipe_optimizer import execution_trees

    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()
    helper = source / "helper.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    (source / "workflow.py").write_text("from helper import VALUE\n", encoding="utf-8")

    copy2 = execution_trees.shutil.copy2

    def copy_changed_bytes(source_path, destination, *args, **kwargs):
        source_path = Path(source_path)
        if source_path == helper:
            original = source_path.read_bytes()
            source_path.write_text("VALUE = 999\n", encoding="utf-8")
            try:
                return copy2(source_path, destination, *args, **kwargs)
            finally:
                source_path.write_bytes(original)
        return copy2(source_path, destination, *args, **kwargs)

    monkeypatch.setattr(execution_trees.shutil, "copy2", copy_changed_bytes)
    with pytest.raises(ValueError, match="frozen tree identity"):
        capture_execution_tree(source, staging)

    assert helper.read_text(encoding="utf-8") == "VALUE = 1\n"
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
            # ERROR_INVALID_PARAMETER means the PID is gone; unknown states stay live.
            return error != 87
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


def _native_inputs(tmp_path: Path, *, source_layout="flat", namespace=False):
    """Capture a consumer plus its selected installed Botpipe package layer."""
    source = tmp_path / "consumer"
    source.mkdir()
    relative = ("src/" if source_layout == "src" else "") + "isolated_demo"
    package = source / relative
    package.mkdir(parents=True)
    if not namespace:
        (package / "__init__.py").write_text("")
    (package / "logic.py").write_text("VALUE = 'baseline'\n")
    workflow_relative = relative + "/workflow.py"
    (source / workflow_relative).write_text(
        "from botpipe import workflow\n"
        "from isolated_demo.logic import VALUE\n"
        "VERSION = 1\n"
        "@workflow\n"
        "def demo():\n"
        "    return (VERSION, VALUE)\n"
    )
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    shutil.copytree(source, baseline)
    shutil.copytree(source, candidate)
    installed = tmp_path / "installed" / "botpipe"
    shutil.copytree(
        Path(__file__).parents[1] / "botpipe",
        installed,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    staging = tmp_path / "staging"
    staging.mkdir()
    frozen = capture_execution_tree(
        source,
        staging,
        selected_package_root=installed,
        selected_package_import_path="botpipe",
    )
    return {
        "source": source,
        "baseline": baseline,
        "candidate": candidate,
        "installed": installed,
        "staging": staging,
        "frozen": frozen,
        "workflow_relative": workflow_relative,
        "package_relative": relative,
    }


def _native_validate(inputs, **kwargs):
    from botpipe_optimizer.candidate_validation import validate_frozen_candidate

    boundary = {
        "workflow_name": "demo",
        "package_root_relative_path": inputs["package_relative"],
    }
    baseline = derive_surface_manifest(
        inputs["baseline"],
        expected_root=inputs["baseline"],
        boundary=boundary,
        surface_kind="baseline",
    )
    candidate = derive_surface_manifest(
        inputs["candidate"],
        expected_root=inputs["candidate"],
        boundary=boundary,
        surface_kind="candidate",
    )
    return validate_frozen_candidate(
        inputs["frozen"],
        baseline_surface_manifest=baseline,
        candidate_surface_manifest=candidate,
        expected_baseline_root=inputs["baseline"],
        expected_candidate_root=inputs["candidate"],
        expected_boundary=boundary,
        baseline_surface_kind="baseline",
        candidate_surface_kind="candidate",
        workflow_refs=kwargs.pop("workflow_refs", ["isolated_demo.workflow:demo"]),
        staging_parent=inputs["staging"],
        **kwargs,
    )


def _cleanup_snapshot(inputs):
    frozen = inputs["frozen"]
    cleanup_owned_directory(
        frozen.root,
        owned_parent=frozen.owned_parent,
        ownership_token=frozen.ownership_token,
    )


@pytest.mark.parametrize("source_layout", ["flat", "src"])
@pytest.mark.parametrize("namespace", [False, True])
def test_native_candidate_uses_staged_behavior_and_package_origins(
    tmp_path, source_layout, namespace
):
    inputs = _native_inputs(tmp_path, source_layout=source_layout, namespace=namespace)
    candidate = inputs["candidate"]
    workflow_relative = inputs["workflow_relative"]
    helper_relative = inputs["package_relative"] + "/logic.py"
    (candidate / workflow_relative).write_text(
        (candidate / workflow_relative)
        .read_text()
        .replace("VERSION = 1", "VERSION = 2")
    )
    (candidate / helper_relative).write_text("VALUE = 'candidate'\n")
    check_relative = "checks with spaces/check candidate.py"
    (candidate / check_relative).parent.mkdir()
    (candidate / check_relative).write_text(
        "from isolated_demo.workflow import demo\n"
        "assert demo.fn() == (2, 'candidate')\n"
    )
    poisoned_site = tmp_path / "poisoned-site-packages"
    poisoned_site.mkdir()
    (poisoned_site / "isolated_demo").mkdir()
    (poisoned_site / "isolated_demo/__init__.py").write_text("")
    (poisoned_site / "isolated_demo/logic.py").write_text(
        "raise RuntimeError('installed original was loaded')\n"
    )
    (poisoned_site / "botpipe").mkdir()
    (poisoned_site / "botpipe/__init__.py").write_text(
        "raise RuntimeError('poisoned framework was loaded')\n"
    )
    sentinel = tmp_path / "editable-hook-executed"
    (poisoned_site / "editable.pth").write_text(
        f"import pathlib; pathlib.Path({str(sentinel)!r}).touch()\n"
        + str(inputs["source"])
        + "\n"
    )
    metadata = poisoned_site / "isolation_probe-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: isolation-probe\nVersion: 1.2.3\n"
    )
    try:
        result = _native_validate(
            inputs,
            target_test_argv=[sys.executable, check_relative],
            allowed_added_exact_paths=[check_relative],
            dependency_roots=[poisoned_site, *_installed_dependency_roots()],
        )
        assert result.success, result.model_dump()
        assert len(result.checks) == 2
        assert result.derived_changes == tuple(
            sorted((workflow_relative, helper_relative, check_relative))
        )
        assert result.baseline_execution_tree_id != result.candidate_execution_tree_id
        origins = [
            entry
            for check in result.checks
            for entry in check.result["module_origins"]
            if entry["module"] == "botpipe"
            or entry["module"].startswith("isolated_demo.")
        ]
        assert any(entry["module"] == "botpipe" for entry in origins)
        assert any(entry["module"] == "isolated_demo.logic" for entry in origins)
        assert all(
            Path(entry["origin"]).is_relative_to(inputs["staging"]) for entry in origins
        )
        from hashlib import sha256

        assert (
            result.compiled_workflows[0]["source_sha256"]
            == sha256((candidate / workflow_relative).read_bytes()).hexdigest()
        )
        assert {"name": "isolation-probe", "version": "1.2.3"} in result.environment[
            "distributions"
        ]
        assert not sentinel.exists()
        assert "VERSION = 1" in (inputs["source"] / workflow_relative).read_text()
        assert (
            inputs["source"] / helper_relative
        ).read_text() == "VALUE = 'baseline'\n"
        assert not list(inputs["staging"].glob("execution-arm-*"))
    finally:
        _cleanup_snapshot(inputs)


def test_imported_original_cannot_hide_invalid_native_candidate(tmp_path, monkeypatch):
    inputs = _native_inputs(tmp_path)
    monkeypatch.syspath_prepend(str(inputs["source"]))
    imported = importlib.import_module("isolated_demo.workflow")
    assert imported.demo.fn() == (1, "baseline")
    (inputs["candidate"] / inputs["workflow_relative"]).write_text(
        "this is invalid Python !!!\n"
    )
    try:
        result = _native_validate(
            inputs, target_test_argv=[sys.executable, "-c", "raise SystemExit(0)"]
        )
        assert result.success is False
        assert len(result.checks) == 1
        assert result.checks[0].kind == "compile_probe"
        assert "SyntaxError" in result.checks[0].result["traceback"]
        assert imported.demo.fn() == (1, "baseline")
    finally:
        for name in list(sys.modules):
            if name == "isolated_demo" or name.startswith("isolated_demo."):
                sys.modules.pop(name)
        _cleanup_snapshot(inputs)


@pytest.mark.parametrize("which", ["source", "installed", "frozen"])
def test_native_validation_rejects_source_or_snapshot_drift_before_launch(
    tmp_path, which
):
    inputs = _native_inputs(tmp_path)
    if which == "source":
        target = inputs["source"] / inputs["workflow_relative"]
    elif which == "installed":
        target = inputs["installed"] / "__init__.py"
    else:
        target = inputs["frozen"].root / inputs["workflow_relative"]
    target.write_text(target.read_text() + "\n# drift\n")
    try:
        with pytest.raises(ValueError, match="changed"):
            _native_validate(inputs)
        assert not list(inputs["staging"].glob("execution-arm-*"))
    finally:
        _cleanup_snapshot(inputs)


def test_execution_tree_byte_limit_is_checked_before_any_copy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "large.py").write_bytes(b"x" * 32)
    staging = tmp_path / "staging"
    with pytest.raises(ValueError, match="max_execution_tree_bytes"):
        capture_execution_tree(source, staging, max_bytes=31)
    assert not list(staging.iterdir())


def test_installed_selected_workflow_is_captured_and_candidate_overlay_executes(
    tmp_path,
):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "README.md").write_text("consumer without Botpipe source")
    installed = tmp_path / "installed" / "botpipe"
    shutil.copytree(
        Path(__file__).parents[1] / "botpipe",
        installed,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    definition = (
        "from botpipe import workflow\n@workflow\ndef demo():\n    return 'original'\n"
    )
    (installed / "isolated_builtin.py").write_text(definition)
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    relative = "botpipe/isolated_builtin.py"
    for root in (baseline, candidate):
        (root / relative).parent.mkdir(parents=True)
        (root / relative).write_text(definition)
    (candidate / relative).write_text(definition.replace("'original'", "'candidate'"))
    (candidate / "check.py").write_text(
        "from botpipe.isolated_builtin import demo\nassert demo.fn() == 'candidate'\n"
    )
    staging = tmp_path / "staging"
    frozen = capture_execution_tree(
        consumer,
        staging,
        selected_package_root=installed,
        selected_package_import_path="botpipe",
    )
    inputs = {
        "source": consumer,
        "baseline": baseline,
        "candidate": candidate,
        "staging": staging,
        "frozen": frozen,
        "package_relative": "botpipe",
        "workflow_relative": relative,
    }
    try:
        result = _native_validate(
            inputs,
            workflow_refs=["botpipe.isolated_builtin:demo"],
            allowed_added_exact_paths=["check.py"],
            target_test_argv=[sys.executable, "check.py"],
        )
        assert result.success, result.model_dump()
        assert (
            result.compiled_workflows[0]["requested_reference"]
            == "botpipe.isolated_builtin:demo"
        )
        assert Path(result.compiled_workflows[0]["source_path"]).is_relative_to(staging)
        assert (installed / "isolated_builtin.py").read_text() == definition
        assert not (consumer / "botpipe").exists()
    finally:
        _cleanup_snapshot(inputs)


@pytest.mark.parametrize("mutation", ["new_staged_code", "authoritative_source"])
def test_python_check_source_mutation_is_detected_and_owned_arms_cleaned(
    tmp_path, mutation
):
    inputs = _native_inputs(tmp_path)
    target = (
        "injected.py"
        if mutation == "new_staged_code"
        else str(inputs["source"] / inputs["workflow_relative"])
    )
    (inputs["candidate"] / "check.py").write_text(
        f"from pathlib import Path\nPath({target!r}).write_text('MUTATED = True\\n')\n"
    )
    try:
        with pytest.raises(ValueError, match="changed"):
            _native_validate(
                inputs,
                allowed_added_exact_paths=["check.py"],
                target_test_argv=[sys.executable, "check.py"],
            )
        assert not list(inputs["staging"].glob("execution-arm-*"))
    finally:
        _cleanup_snapshot(inputs)


def test_native_python_dash_c_check_uses_candidate_imports(tmp_path):
    inputs = _native_inputs(tmp_path)
    (inputs["candidate"] / inputs["workflow_relative"]).write_text(
        (inputs["candidate"] / inputs["workflow_relative"])
        .read_text()
        .replace("VERSION = 1", "VERSION = 2")
    )
    try:
        result = _native_validate(
            inputs,
            target_test_argv=[
                sys.executable,
                "-c",
                "from isolated_demo.workflow import demo; assert demo.fn() == (2, 'baseline')",
            ],
        )
        assert result.success, result.model_dump()
    finally:
        _cleanup_snapshot(inputs)
