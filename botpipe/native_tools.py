"""Confined read tools and finite exact-command recipes for native loops."""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import stat
import subprocess
import threading
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .processes import ProcessContainment
from .providers import CapabilityError

_PRIVATE_NAMES = frozenset({
    ".aws", ".azure", ".botpipe", ".botpipe-v2", ".claude", ".codex", ".config",
    ".env", ".git", ".gnupg", ".pi", ".ssh", ".botpipe-workspace.lock", "credential",
    "credentials", "credentials.json",
})
_OPEN_BASE = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


class _DirectoryIdentityChanged(CapabilityError):
    pass


def _private_name(name):
    lowered = name.lower()
    return lowered in _PRIVATE_NAMES or lowered.startswith(".env.")


def _positive_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def command_scope_is_workspace_wide(workspace, allow_read, deny_read) -> bool:
    """Return whether command reads are exactly the whole resolved workspace."""
    if allow_read is None or deny_read:
        return False
    try:
        resolved_workspace = Path(workspace).resolve()
        roots = tuple(
            (
                Path(value)
                if Path(value).is_absolute()
                else resolved_workspace / Path(value)
            ).resolve()
            for value in allow_read
        )
    except (OSError, TypeError, ValueError):
        return False
    return roots == (resolved_workspace,)


@dataclass(frozen=True, slots=True)
class ToolObservation:
    tool: str
    input: Mapping[str, Any]
    output: str
    truncated: bool = False
    exit_code: int | None = None
    identity: Mapping[str, Any] | None = None

    def to_record(self):
        return {
            "tool": self.tool, "input": dict(self.input), "output": self.output,
            "truncated": self.truncated, "exit_code": self.exit_code,
            "identity": dict(self.identity) if self.identity is not None else None,
        }


def _path_identity(path, *, trusted=False):
    resolved = Path(path).resolve(strict=True)
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode):
        raise CapabilityError(f"command executable is not a regular file: {resolved}")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise CapabilityError(f"command executable is group/world writable: {resolved}")
    if trusted and hasattr(os, "geteuid") and info.st_uid != 0:
        raise CapabilityError(f"sandbox executable is not root-owned: {resolved}")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(resolved), "device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "sha256": digest.hexdigest()}


def _directory_identity(path, fd=None):
    info = os.fstat(fd) if fd is not None else Path(path).stat()
    if not stat.S_ISDIR(info.st_mode):
        raise CapabilityError(f"workspace is not a directory: {path}")
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino}


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    grant_id: str
    public_argv: tuple[str, ...]
    executable: Path
    native_argv: tuple[str, ...]
    cwd: Path
    environment: Mapping[str, str]
    executable_identity: Mapping[str, Any]
    sandbox_identity: Mapping[str, Any]
    workspace_identity: Mapping[str, Any]

    def __post_init__(self):
        for name in ("environment", "executable_identity", "sandbox_identity", "workspace_identity"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    def to_record(self):
        return {
            "grant_id": self.grant_id, "public_argv": list(self.public_argv),
            "executable": str(self.executable), "native_argv": list(self.native_argv),
            "cwd": str(self.cwd), "environment": dict(self.environment),
            "executable_identity": dict(self.executable_identity),
            "sandbox_identity": dict(self.sandbox_identity),
            "workspace_identity": dict(self.workspace_identity),
            "stdin": "empty", "network": "none",
        }


@dataclass(frozen=True, slots=True)
class LineCountEnvelope:
    """The fixed executable contract exposed by the query line-count tool."""

    executable: Path
    native_argv: tuple[str, ...]
    environment: Mapping[str, str]
    executable_identity: Mapping[str, Any]
    max_input_bytes: int
    timeout: float

    def __post_init__(self):
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(
            self,
            "executable_identity",
            MappingProxyType(dict(self.executable_identity)),
        )

    def to_record(self):
        return {
            "tool": "count_lines",
            "executable": str(self.executable),
            "native_argv": list(self.native_argv),
            "environment": dict(self.environment),
            "executable_identity": dict(self.executable_identity),
            "stdin": "bounded authorized regular-file snapshot",
            "max_input_bytes": self.max_input_bytes,
            "timeout": self.timeout,
        }


class ReadOnlyTools:
    """Descriptor-confined, symlink-denying, resource-bounded local reads."""

    def __init__(self, roots, *, exclusions=(), max_output_bytes=256_000,
                 max_read_bytes=1_000_000, max_entries=2_000,
                 max_files=5_000, max_depth=32, max_matches=2_000,
                 command_timeout=5.0, read_fence=None):
        if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                or os.open not in os.supports_dir_fd
                or os.scandir not in os.supports_fd):
            raise CapabilityError("descriptor-confined query tools are unavailable on this platform")
        for name in ("max_output_bytes", "max_read_bytes", "max_entries", "max_files", "max_depth", "max_matches"):
            setattr(self, name, _positive_int(name, locals()[name]))
        if (
            isinstance(command_timeout, bool)
            or not isinstance(command_timeout, (int, float))
            or not math.isfinite(command_timeout)
            or command_timeout <= 0
        ):
            raise ValueError("command_timeout must be finite and positive")
        self.command_timeout = float(command_timeout)
        if read_fence is not None and not callable(read_fence):
            raise TypeError("read_fence must be callable or None")
        self._read_fence = read_fence
        self._fenced_directories = {}
        self._fences = ExitStack()
        self.roots = tuple(Path(root).resolve(strict=True) for root in roots)
        if any(any(_private_name(part) for part in root.parts) for root in self.roots):
            raise CapabilityError(
                "query root is inside an enumerated private-state directory"
            )
        self._root_fds = []
        for root in self.roots:
            try:
                self._fence_directory(root)
                root_fd = os.open(root, _OPEN_BASE | os.O_DIRECTORY)
                try:
                    self._fence_directory(root, root_fd)
                except BaseException:
                    os.close(root_fd)
                    raise
                self._root_fds.append(root_fd)
            except OSError as exc:
                self.close()
                raise CapabilityError(f"cannot securely open read root: {root}") from exc
            except BaseException:
                self.close()
                raise
        self.exclusions = tuple(Path(path).resolve(strict=False) for path in exclusions)
        self.observations = []
        try:
            executable = shutil.which("wc", path="/usr/bin:/bin")
            if executable is None:
                raise CapabilityError(
                    "count_lines requires a trusted system wc executable"
                )
            executable = Path(executable).resolve(strict=True)
            environment = {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            }
            self.count_lines_envelope = LineCountEnvelope(
                executable=executable,
                native_argv=(str(executable), "-l"),
                environment=environment,
                executable_identity=_path_identity(executable, trusted=True),
                max_input_bytes=self.max_read_bytes,
                timeout=self.command_timeout,
            )
            self.command_envelopes = MappingProxyType(
                {"count_lines": self.count_lines_envelope}
            )
        except BaseException:
            self.close()
            raise

    def close(self):
        while getattr(self, "_root_fds", []):
            os.close(self._root_fds.pop())
        fences = getattr(self, "_fences", None)
        if fences is not None:
            fences.close()
            self._fences = None

    def __del__(self):
        try:
            self.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def _directory_fd_identity(fd):
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise CapabilityError("read fence target is not a directory")
        return info.st_dev, info.st_ino

    @staticmethod
    def _directory_path_identity(path):
        info = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise CapabilityError("read fence path is not a directory")
        return info.st_dev, info.st_ino

    def _fence_directory(self, path, fd=None):
        if self._read_fence is None:
            return
        directory = Path(path)
        key = str(directory)
        try:
            descriptor_identity = (
                self._directory_fd_identity(fd) if fd is not None else None
            )
            before_identity = descriptor_identity or self._directory_path_identity(
                directory
            )
        except OSError as exc:
            raise CapabilityError(
                "read directory identity could not be verified before fencing"
            ) from exc
        recorded = self._fenced_directories.get(key)
        if recorded is not None:
            try:
                path_identity = self._directory_path_identity(directory)
            except OSError as exc:
                raise CapabilityError(
                    "read directory identity could not be verified after fencing"
                ) from exc
            if before_identity != recorded or path_identity != recorded:
                raise _DirectoryIdentityChanged(
                    "read directory changed after its ownership fence was acquired"
                )
            return
        context = self._read_fence(directory)
        if context is not None:
            self._fences.enter_context(context)
        try:
            path_identity = self._directory_path_identity(directory)
        except OSError as exc:
            raise CapabilityError(
                "read directory identity could not be verified while fencing"
            ) from exc
        if before_identity != path_identity:
            raise _DirectoryIdentityChanged(
                "read directory changed while its ownership fence was acquired"
            )
        self._fenced_directories[key] = before_identity

    def _candidates(self, value):
        if type(value) is not str or not value or "\x00" in value:
            raise CapabilityError("read path must be a non-empty string without NUL")
        authored = Path(value)
        candidates = []
        for index, root in enumerate(self.roots):
            try:
                relative = authored.relative_to(root) if authored.is_absolute() else authored
            except ValueError:
                continue
            parts = tuple(part for part in relative.parts if part not in ("", "."))
            if any(part == ".." for part in parts):
                continue
            target = root.joinpath(*parts)
            if any(_private_name(part) for part in parts):
                raise CapabilityError(f"read path is excluded by the native query profile: {value!r}")
            if any(target == denied or target.is_relative_to(denied) for denied in self.exclusions):
                continue
            candidates.append((index, target, parts))
        return candidates

    def _open(self, value, *, directory=False):
        for index, target, parts in self._candidates(value):
            fd = os.dup(self._root_fds[index])
            try:
                for offset, part in enumerate(parts):
                    final = offset == len(parts) - 1
                    flags = _OPEN_BASE
                    if not final or directory:
                        flags |= os.O_DIRECTORY
                    elif final:
                        flags |= getattr(os, "O_NONBLOCK", 0)
                    child = os.open(part, flags, dir_fd=fd)
                    os.close(fd)
                    fd = child
                    if not final or directory:
                        self._fence_directory(
                            self.roots[index].joinpath(*parts[:offset + 1]), child
                        )
                info = os.fstat(fd)
                valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
                if not valid:
                    raise CapabilityError(f"query path has the wrong file type: {value!r}")
                return fd, target
            except _DirectoryIdentityChanged:
                os.close(fd)
                raise
            except (OSError, CapabilityError):
                os.close(fd)
            except BaseException:
                os.close(fd)
                raise
        raise CapabilityError(f"read path is outside authorized roots or uses a symlink: {value!r}")

    def _read_fd(self, fd):
        info = os.fstat(fd)
        remaining = self.max_read_bytes + 1
        chunks = []
        while remaining:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        captured = b"".join(chunks)
        return captured[:self.max_read_bytes], info, len(captured) > self.max_read_bytes

    def _bounded_text(self, raw):
        return raw[:self.max_output_bytes].decode(errors="replace"), len(raw) > self.max_output_bytes

    def read(self, path):
        fd, display = self._open(path)
        try:
            raw, info, input_truncated = self._read_fd(fd)
        finally:
            os.close(fd)
        text, output_truncated = self._bounded_text(raw)
        scope = "captured_prefix" if input_truncated else "full"
        observation = ToolObservation(
            "read", {"path": str(display)}, text, input_truncated or output_truncated,
            identity={"sha256": hashlib.sha256(raw).hexdigest(), "digest_scope": scope,
                      "hashed_bytes": len(raw), "bytes": info.st_size,
                      "device": info.st_dev, "inode": info.st_ino})
        self.observations.append(observation)
        return observation

    def count_lines(self, path):
        """Count newlines in one bounded authorized file using fixed system wc."""
        fd, display = self._open(path)
        try:
            raw, info, input_truncated = self._read_fd(fd)
        finally:
            os.close(fd)
        if input_truncated:
            raise CapabilityError(
                "count_lines source exceeds the authorized snapshot byte limit"
            )

        envelope = self.count_lines_envelope
        if _path_identity(envelope.executable, trusted=True) != dict(
            envelope.executable_identity
        ):
            raise CapabilityError(
                "count_lines executable identity changed after authorization"
            )

        containment = ProcessContainment.create()
        process = None
        retained = {"stdout": bytearray(), "stderr": bytearray()}
        output_truncated = {"stdout": False, "stderr": False}
        writer_errors = []
        reader_errors = []

        def write_snapshot():
            try:
                process.stdin.write(raw)
            except BrokenPipeError:
                pass
            except BaseException as exc:
                writer_errors.append(exc)
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError, ValueError):
                    pass

        def drain(name):
            try:
                stream = getattr(process, name)
                for chunk in iter(lambda: stream.read(64 * 1024), b""):
                    remaining = self.max_output_bytes - len(retained[name])
                    if remaining > 0:
                        retained[name].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        output_truncated[name] = True
            except BaseException as exc:
                reader_errors.append(exc)

        threads = []
        try:
            process = subprocess.Popen(
                envelope.native_argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd="/",
                env=dict(envelope.environment),
                **containment.creation_kwargs,
            )
            containment.attach_and_start(process)
            threads = [
                threading.Thread(
                    target=write_snapshot,
                    name="botpipe-count-lines-input",
                    daemon=True,
                ),
                threading.Thread(
                    target=drain,
                    args=("stdout",),
                    name="botpipe-count-lines-stdout",
                    daemon=True,
                ),
                threading.Thread(
                    target=drain,
                    args=("stderr",),
                    name="botpipe-count-lines-stderr",
                    daemon=True,
                ),
            ]
            for thread in threads:
                thread.start()
            try:
                returncode = process.wait(timeout=envelope.timeout)
            except subprocess.TimeoutExpired as exc:
                containment.terminate(process, grace_seconds=1.0)
                for thread in threads:
                    thread.join(1.0)
                raise CapabilityError("count_lines command timed out") from exc
            containment.ensure_tree_exited(process, grace_seconds=1.0)
            for thread in threads:
                thread.join(1.0)
            if any(thread.is_alive() for thread in threads):
                raise CapabilityError("count_lines command I/O did not terminate")
        finally:
            if process is not None and process.poll() is None:
                containment.terminate(process, grace_seconds=1.0)
            containment.close()

        if writer_errors:
            raise CapabilityError("count_lines snapshot input could not be delivered") from writer_errors[0]
        if reader_errors:
            raise CapabilityError("count_lines command output could not be drained") from reader_errors[0]
        if any(output_truncated.values()):
            raise CapabilityError("count_lines command output exceeded its byte limit")
        diagnostic = bytes(retained["stderr"]).decode(errors="replace").strip()
        if returncode:
            raise CapabilityError(
                f"count_lines command failed with exit code {returncode}: {diagnostic}"
            )
        try:
            output = bytes(retained["stdout"]).decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise CapabilityError("count_lines command returned non-ASCII output") from exc
        if diagnostic or output != str(raw.count(b"\n")):
            raise CapabilityError("count_lines command returned an invalid count")

        source = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "digest_scope": "full",
            "captured_bytes": len(raw),
            "bytes": info.st_size,
            "device": info.st_dev,
            "inode": info.st_ino,
        }
        observation = ToolObservation(
            "count_lines",
            {"path": str(display), "source": source},
            output,
            exit_code=returncode,
            identity={"command_envelope": envelope.to_record()},
        )
        self.observations.append(observation)
        return observation

    def list(self, path="."):
        fd, display = self._open(path, directory=True)
        entries, truncated = [], False
        try:
            with os.scandir(fd) as scan:
                for entry in scan:
                    if _private_name(entry.name) or entry.is_symlink():
                        continue
                    child = display / entry.name
                    if any(child == denied or child.is_relative_to(denied) for denied in self.exclusions):
                        continue
                    if len(entries) >= self.max_entries:
                        truncated = True
                        break
                    try:
                        is_directory = entry.is_dir(follow_symlinks=False)
                        if is_directory:
                            child_fd = os.open(
                                entry.name,
                                _OPEN_BASE | os.O_DIRECTORY,
                                dir_fd=fd,
                            )
                            try:
                                self._fence_directory(child, child_fd)
                            finally:
                                os.close(child_fd)
                        entries.append(entry.name + ("/" if is_directory else ""))
                    except OSError:
                        continue
        finally:
            os.close(fd)
        text, output_truncated = self._bounded_text("\n".join(sorted(entries)).encode())
        observation = ToolObservation("list", {"path": str(display)}, text,
                                      truncated or output_truncated,
                                      identity={"entries_returned": len(entries),
                                                "entry_limit": self.max_entries})
        self.observations.append(observation)
        return observation

    def search(self, query, path="."):
        if type(query) is not str or not query or "\x00" in query:
            raise CapabilityError("search query must be a non-empty literal string")
        try:
            file_fd, display = self._open(path)
        except CapabilityError:
            root_fd, display = self._open(path, directory=True)
            stack = [(root_fd, display, 0)]
        else:
            stack = []
        output = bytearray()
        files = matches = visited = 0
        truncated = False

        def search_file(fd, shown):
            nonlocal matches, truncated
            raw, _, prefix = self._read_fd(fd)
            truncated |= prefix
            for number, line in enumerate(raw.decode(errors="replace").splitlines(), 1):
                if query not in line:
                    continue
                rendered = f"{shown}:{number}:{line}\n".encode(errors="replace")
                remaining = self.max_output_bytes - len(output)
                if matches >= self.max_matches or remaining <= 0:
                    truncated = True
                    return
                output.extend(rendered[:remaining])
                matches += 1
                if len(rendered) > remaining:
                    truncated = True
                    return

        if not stack:
            try:
                search_file(file_fd, display)
            finally:
                os.close(file_fd)
            files = 1
        while stack and not truncated:
            directory_fd, directory, depth = stack.pop()
            try:
                with os.scandir(directory_fd) as scan:
                    for entry in scan:
                        visited += 1
                        if visited > self.max_files:
                            truncated = True
                            break
                        if _private_name(entry.name) or entry.is_symlink():
                            continue
                        shown = directory / entry.name
                        if any(shown == denied or shown.is_relative_to(denied) for denied in self.exclusions):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if depth >= self.max_depth:
                                    truncated = True
                                    continue
                                child = os.open(entry.name, _OPEN_BASE | os.O_DIRECTORY, dir_fd=directory_fd)
                                try:
                                    self._fence_directory(shown, child)
                                except BaseException:
                                    os.close(child)
                                    raise
                                stack.append((child, shown, depth + 1))
                            elif entry.is_file(follow_symlinks=False):
                                child = os.open(entry.name, _OPEN_BASE | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
                                try:
                                    if stat.S_ISREG(os.fstat(child).st_mode):
                                        files += 1
                                        search_file(child, shown)
                                finally:
                                    os.close(child)
                        except OSError:
                            continue
                        if truncated:
                            break
            finally:
                os.close(directory_fd)
        while stack:
            os.close(stack.pop()[0])
        observation = ToolObservation(
            "search", {"query": query, "path": str(display)},
            bytes(output).decode(errors="replace").rstrip("\n"), truncated,
            identity={"files_visited": files, "file_limit": self.max_files,
                      "nodes_visited": visited,
                      "matches": matches, "match_limit": self.max_matches,
                      "depth_limit": self.max_depth})
        self.observations.append(observation)
        return observation


class ExactCommandTools:
    """Closed read-only recipes executed by trusted bubblewrap without a shell."""

    def __init__(self, workspace, grants, *, timeout=30, max_output_bytes=256_000):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.max_output_bytes = _positive_int("max_output_bytes", max_output_bytes)
        self.timeout = float(timeout)
        self.workspace = Path(workspace).resolve(strict=True)
        try:
            self._workspace_fd = os.open(
                self.workspace,
                _OPEN_BASE | os.O_DIRECTORY,
            )
        except OSError as exc:
            raise CapabilityError("workspace cannot be pinned for sandbox mounting") from exc
        self.workspace_identity = _directory_identity(
            self.workspace, self._workspace_fd
        )
        self._audit_repository()
        executable = shutil.which("bwrap", path="/usr/bin:/bin")
        if executable is None:
            raise CapabilityError("exact command mediation requires trusted system bubblewrap")
        self.bwrap = Path(executable).resolve(strict=True)
        self.bwrap_identity = _path_identity(self.bwrap, trusted=True)
        self.envelopes = MappingProxyType(self._resolve(grants))
        if self.envelopes:
            self._probe(next(iter(self.envelopes.values())))
        self.observations = []

    def close(self):
        fd = getattr(self, "_workspace_fd", None)
        if fd is not None:
            os.close(fd)
            self._workspace_fd = None

    def __del__(self):
        try:
            self.close()
        except OSError:
            pass

    def _audit_repository(self):
        """Reject repository inputs that can make status launch a helper."""
        stack = [(os.dup(self._workspace_fd), (), 0)]
        visited = 0
        try:
            while stack:
                directory_fd, relative, depth = stack.pop()
                try:
                    with os.scandir(directory_fd) as scan:
                        for entry in scan:
                            visited += 1
                            if visited > 20_000 or depth > 64:
                                raise CapabilityError(
                                    "git status repository audit exceeds its traversal bound"
                                )
                            path = (*relative, entry.name)
                            if entry.name == ".gitattributes" or path[-3:] == (
                                ".git", "info", "attributes"
                            ):
                                raise CapabilityError(
                                    "git status exact grant does not support repository attributes; "
                                    "attributes can launch external filter helpers"
                                )
                            if entry.name == ".git" and not entry.is_dir(
                                follow_symlinks=False
                            ):
                                raise CapabilityError(
                                    "git status exact grant supports only an in-workspace .git directory"
                                )
                            if entry.is_dir(follow_symlinks=False):
                                child = os.open(
                                    entry.name,
                                    _OPEN_BASE | os.O_DIRECTORY,
                                    dir_fd=directory_fd,
                                )
                                stack.append((child, path, depth + 1))
                finally:
                    os.close(directory_fd)
        finally:
            while stack:
                os.close(stack.pop()[0])

    def _probe(self, envelope):
        command = self._command(envelope)
        command = command[:command.index("--") + 1] + ["/usr/bin/true"]
        try:
            completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       timeout=5, check=False,
                                       env={"PATH": "/usr/bin:/bin"},
                                       pass_fds=(self._workspace_fd,))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CapabilityError("bubblewrap isolation probe failed") from exc
        if completed.returncode:
            diagnostic = completed.stderr[:200].decode(errors="replace")
            raise CapabilityError(f"bubblewrap isolation is unavailable: {diagnostic}")

    def _resolve(self, grants):
        result = {}
        for index, public in enumerate(grants):
            if public != ("git", "status", "--short"):
                raise CapabilityError(f"command grant is not in the finite read-only recipe set: {public!r}")
            git = shutil.which("git", path="/usr/bin:/bin")
            if git is None:
                raise CapabilityError("git status grant requires a system git executable")
            executable = Path(git).resolve(strict=True)
            grant_id = f"grant_{index + 1}"
            environment = {"HOME": "/tmp/home", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                           "PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1",
                           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                           "GIT_ATTR_NOSYSTEM": "1", "GIT_PAGER": "cat", "PAGER": "cat"}
            result[grant_id] = CommandEnvelope(
                grant_id, public, executable,
                (str(executable), "--no-optional-locks", "-c", "core.fsmonitor=false",
                 "-c", "core.untrackedCache=false", "-c", "core.hooksPath=/dev/null",
                 "-c", "submodule.recurse=false", "-c", "fetch.recurseSubmodules=false",
                 "-c", "maintenance.auto=false", "-c", "gc.auto=0",
                 "status", "--short", "--ignore-submodules=all"),
                self.workspace, environment, _path_identity(executable, trusted=True),
                self.bwrap_identity, self.workspace_identity)
        return result

    def _command(self, envelope):
        command = [str(self.bwrap), "--die-with-parent", "--new-session", "--unshare-all", "--clearenv",
                   "--tmpfs", "/tmp", "--dev", "/dev", "--dir", "/tmp/home",
                   "--ro-bind", "/usr", "/usr"]
        for source in ("/bin", "/lib", "/lib64"):
            path = Path(source)
            if path.exists() and path.resolve() != Path("/usr").resolve():
                command += ["--ro-bind", source, source]
        parent, mount_dirs = self.workspace.parent, []
        stop = {Path(base) for base in ("/usr", "/bin", "/lib", "/lib64", "/tmp", "/")}
        while parent not in stop:
            mount_dirs.append(parent)
            parent = parent.parent
        for directory in reversed(mount_dirs):
            command += ["--dir", str(directory)]
        command += ["--dir", str(self.workspace), "--ro-bind-fd",
                    str(self._workspace_fd), str(self.workspace),
                    "--chdir", str(self.workspace)]
        for key, value in envelope.environment.items():
            command += ["--setenv", key, value]
        return [*command, "--", *envelope.native_argv]

    def execute(self, grant_id):
        envelope = self.envelopes.get(grant_id)
        if envelope is None:
            raise CapabilityError(f"unknown command grant ID: {grant_id!r}")
        if _path_identity(envelope.executable, trusted=True) != dict(envelope.executable_identity):
            raise CapabilityError("command executable identity changed after authorization")
        if _path_identity(self.bwrap, trusted=True) != dict(envelope.sandbox_identity):
            raise CapabilityError("sandbox executable identity changed after authorization")
        if _directory_identity(self.workspace, self._workspace_fd) != dict(envelope.workspace_identity):
            raise CapabilityError("pinned workspace identity changed after authorization")
        self._audit_repository()
        containment = ProcessContainment.create()
        retained, truncated = bytearray(), False
        process = None

        def drain():
            nonlocal truncated
            for chunk in iter(lambda: process.stdout.read(64 * 1024), b""):
                remaining = self.max_output_bytes - len(retained)
                if remaining > 0:
                    retained.extend(chunk[:remaining])
                truncated |= len(chunk) > remaining

        try:
            process = subprocess.Popen(
                self._command(envelope), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                pass_fds=(self._workspace_fd,),
                **containment.creation_kwargs)
            containment.attach_and_start(process)
            reader = threading.Thread(target=drain, name="botpipe-command-output", daemon=True)
            reader.start()
            try:
                returncode = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                containment.terminate(process, grace_seconds=1.0)
                reader.join(1.0)
                raise CapabilityError(f"command grant timed out: {grant_id}") from exc
            containment.ensure_tree_exited(process, grace_seconds=1.0)
            reader.join(1.0)
            if reader.is_alive():
                raise CapabilityError("command output drain did not terminate")
        finally:
            if process is not None and process.poll() is None:
                containment.terminate(process, grace_seconds=1.0)
            containment.close()
        observation = ToolObservation(
            "exec_grant", {"grant_id": grant_id, "argv": list(envelope.public_argv)},
            bytes(retained).decode(errors="replace"), truncated, returncode,
            envelope.to_record())
        self.observations.append(observation)
        return observation


__all__ = [
    "CommandEnvelope",
    "ExactCommandTools",
    "LineCountEnvelope",
    "ReadOnlyTools",
    "ToolObservation",
    "command_scope_is_workspace_wide",
]
