import io
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe.native_tools import ExactCommandTools, ReadOnlyTools
from botpipe import RunBusy
from botpipe.providers import CapabilityError


def test_reads_are_descriptor_confined_and_symlinks_and_traversal_fail(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("safe")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link.txt").symlink_to(outside)
    (root / "linked-dir").symlink_to(tmp_path, target_is_directory=True)

    with ReadOnlyTools((root,)) as tools:
        assert tools.read("safe.txt").output == "safe"
        for path in ("../outside.txt", "link.txt", "linked-dir/outside.txt"):
            with pytest.raises(CapabilityError):
                tools.read(path)


def test_private_and_configured_exclusions_apply_to_read_list_and_search(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    for private in (
        ".git", ".botpipe", ".botpipe-v2", ".ssh", "credentials", ".env.local"
    ):
        folder = root / private
        folder.mkdir()
        (folder / "secret.txt").write_text("needle")
    excluded = root / "excluded"
    excluded.mkdir()
    (excluded / "secret.txt").write_text("needle")
    (root / "visible.txt").write_text("needle")

    with ReadOnlyTools((root,), exclusions=(excluded,)) as tools:
        listing = tools.list()
        assert listing.output == "visible.txt"
        found = tools.search("needle")
        assert "visible.txt" in found.output
        assert "secret.txt" not in found.output
        with pytest.raises(CapabilityError):
            tools.read(".git/secret.txt")
        with pytest.raises(CapabilityError):
            tools.read("excluded/secret.txt")


def test_read_is_bounded_and_labels_digest_as_captured_prefix(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "large.txt").write_bytes(b"abcdefghij")
    with ReadOnlyTools((root,), max_read_bytes=6, max_output_bytes=4) as tools:
        observation = tools.read("large.txt")
    assert observation.output == "abcd"
    assert observation.truncated
    assert observation.identity["digest_scope"] == "captured_prefix"
    assert observation.identity["hashed_bytes"] == 6
    assert observation.identity["bytes"] == 10


def test_list_and_search_stop_at_configured_bounds(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    for index in range(8):
        (root / f"file-{index}.txt").write_text("needle\n")
    with ReadOnlyTools(
        (root,), max_entries=2, max_files=3, max_matches=2, max_output_bytes=100
    ) as tools:
        listing = tools.list()
        searched = tools.search("needle")
    assert listing.truncated and listing.identity["entries_returned"] == 2
    assert searched.truncated
    assert searched.identity["nodes_visited"] <= 4
    assert searched.identity["matches"] <= 2


def test_search_depth_is_bounded_without_following_directory_symlinks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    shallow = root / "shallow"
    deep = shallow / "deep"
    deep.mkdir(parents=True)
    (deep / "match.txt").write_text("needle")
    (root / "alias").symlink_to(shallow, target_is_directory=True)
    with ReadOnlyTools((root,), max_depth=1) as tools:
        observation = tools.search("needle")
    assert observation.truncated
    assert "match.txt" not in observation.output


def test_nested_workspace_fence_blocks_native_read_before_file_observation(tmp_path):
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / ".botpipe-workspace.lock").write_text("private owner record")
    (child / "secret.txt").write_text("unsettled contents")
    checked = []

    @contextmanager
    def fence(directory):
        checked.append(Path(directory))
        if Path(directory) == child:
            raise RunBusy("nested workspace has unresolved effects")
        yield

    with ReadOnlyTools((root,), read_fence=fence) as tools:
        with pytest.raises(RunBusy, match="unresolved"):
            tools.read("child/secret.txt")
        assert tools.observations == []

    assert child in checked


def test_native_read_root_is_fenced_before_its_descriptor_is_opened(tmp_path):
    root = tmp_path / "foreign-workspace"
    root.mkdir()
    (root / "secret.txt").write_text("unsettled contents")
    checked = []

    @contextmanager
    def fence(directory):
        checked.append(Path(directory))
        raise RunBusy("read root has unresolved effects")
        yield

    with pytest.raises(RunBusy, match="unresolved"):
        ReadOnlyTools((root,), read_fence=fence)
    assert checked == [root]


def _exact_tool(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bwrap = tmp_path / "bwrap"
    git = tmp_path / "git"
    bwrap.write_bytes(b"bwrap")
    git.write_bytes(b"git")
    bwrap.chmod(0o755)
    git.chmod(0o755)

    def which(name, path=None):
        return str(bwrap if name == "bwrap" else git if name == "git" else "") or None

    monkeypatch.setattr("botpipe.native_tools.shutil.which", which)
    monkeypatch.setattr(
        "botpipe.native_tools.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr=b""),
    )
    return ExactCommandTools(workspace, (("git", "status", "--short"),)), bwrap, git


def test_bwrap_probe_and_command_order_support_tmp_workspace(tmp_path, monkeypatch):
    probes = []

    def run(command, **kwargs):
        probes.append((command, kwargs))
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("botpipe.native_tools.subprocess.run", run)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bwrap, git = tmp_path / "bwrap", tmp_path / "git"
    bwrap.write_bytes(b"bwrap")
    git.write_bytes(b"git")
    bwrap.chmod(0o755)
    git.chmod(0o755)
    monkeypatch.setattr(
        "botpipe.native_tools.shutil.which",
        lambda name, path=None: str(bwrap if name == "bwrap" else git),
    )
    tool = ExactCommandTools(workspace, (("git", "status", "--short"),))
    command = tool._command(tool.envelopes["grant_1"])
    assert probes and probes[0][1]["env"] == {"PATH": "/usr/bin:/bin"}
    assert command.index("--tmpfs") < command.index(str(workspace))
    assert "--unshare-all" in command and "--clearenv" in command
    bind_index = command.index("--ro-bind-fd")
    assert command[bind_index + 1] == str(tool._workspace_fd)
    assert command[bind_index + 2] == str(workspace)
    assert probes[0][1]["pass_fds"] == (tool._workspace_fd,)
    assert command[-3:] == ["status", "--short", "--ignore-submodules=all"]
    assert "core.fsmonitor=false" in command
    assert "core.hooksPath=/dev/null" in command
    assert "submodule.recurse=false" in command


def test_unknown_grant_and_identity_change_fail_before_spawn(tmp_path, monkeypatch):
    tool, _, git = _exact_tool(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "botpipe.native_tools.subprocess.Popen",
        lambda *a, **k: pytest.fail("native process must not start"),
    )
    with pytest.raises(CapabilityError, match="unknown command grant"):
        tool.execute("missing")
    git.write_bytes(b"replaced")
    with pytest.raises(CapabilityError, match="identity changed"):
        tool.execute("grant_1")


def test_repository_attributes_and_external_gitdir_are_rejected_predispatch(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitattributes").write_text("*.txt filter=external\n")
    bwrap, git = tmp_path / "bwrap", tmp_path / "git"
    bwrap.write_bytes(b"bwrap")
    git.write_bytes(b"git")
    bwrap.chmod(0o755)
    git.chmod(0o755)
    monkeypatch.setattr(
        "botpipe.native_tools.shutil.which",
        lambda name, path=None: str(bwrap if name == "bwrap" else git),
    )
    monkeypatch.setattr(
        "botpipe.native_tools.subprocess.run",
        lambda *a, **k: pytest.fail("bubblewrap probe must not start"),
    )
    with pytest.raises(CapabilityError, match="external filter helpers"):
        ExactCommandTools(workspace, (("git", "status", "--short"),))

    (workspace / ".gitattributes").unlink()
    (workspace / ".git").write_text("gitdir: /outside\n")
    with pytest.raises(CapabilityError, match="in-workspace .git directory"):
        ExactCommandTools(workspace, (("git", "status", "--short"),))


def test_exact_command_bounds_output_controls_env_and_uses_containment(tmp_path, monkeypatch):
    tool, _, _ = _exact_tool(tmp_path, monkeypatch)
    tool.max_output_bytes = 4
    calls = []

    class Process:
        pid = 1234
        returncode = 0

        def __init__(self):
            self.stdout = io.BytesIO(b"abcdefgh")

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            return 0

        def poll(self):
            return 0

    process = Process()

    class Containment:
        creation_kwargs = {"start_new_session": True}

        def attach_and_start(self, observed):
            calls.append(("attach", observed))

        def ensure_tree_exited(self, observed, grace_seconds):
            calls.append(("ensure", observed, grace_seconds))

        def terminate(self, *args, **kwargs):
            calls.append(("terminate",))

        def close(self):
            calls.append(("close",))

    spawned = []
    monkeypatch.setattr("botpipe.native_tools.ProcessContainment.create", lambda: Containment())
    monkeypatch.setattr(
        "botpipe.native_tools.subprocess.Popen",
        lambda command, **kwargs: spawned.append((command, kwargs)) or process,
    )
    observation = tool.execute("grant_1")
    assert observation.output == "abcd" and observation.truncated
    assert spawned[0][1]["stdin"] is subprocess.DEVNULL
    assert spawned[0][1]["pass_fds"] == (tool._workspace_fd,)
    assert spawned[0][1]["env"] == {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"
    }
    assert [call[0] for call in calls] == ["attach", "wait", "ensure", "close"]
