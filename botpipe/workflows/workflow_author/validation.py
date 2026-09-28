"""Prepare and check a generated workflow in one run-owned project copy."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from botpipe import activity, current_run
from botpipe.surface_identity import derive_surface_manifest
from botpipe_optimizer.processes import ProcessResult, run_bounded_process

_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist", ".tox"}
_SKIP_FILES = {".git", ".coverage", ".DS_Store"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class Validation(BaseModel):
    reference: str | None = None
    success: bool = False
    errors: list[str] = Field(default_factory=list)
    transcript: str = ""
    digest: str = ""
    output: str = ""


def _name(value: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError("workflow name must be a Python identifier")
    return value


def _inventory(root: Path) -> list[str]:
    """Include every candidate source/dependency byte, excluding generated state."""
    paths = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.endswith(".egg-info") and (parent != root / ".botpipe" or d == "workflows"))
        for item in [*(parent / d for d in dirs), *(parent / f for f in files)]:
            if item.is_symlink():
                raise ValueError(f"candidate contains a symlink: {item}")
        paths.extend((parent / f).relative_to(root).as_posix() for f in sorted(files) if f not in _SKIP_FILES and not f.endswith((".pyc", ".pyo")))
    return paths


def _digest(root: Path) -> str:
    paths = _inventory(root)
    return derive_surface_manifest(
        root, expected_root=root, boundary={"candidate": "workflow-author"},
        surface_kind="candidate", relative_paths=paths, allow_empty=True,
    )["surface_id"]


def _transcript_path(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("transcript must be absolute")
    path = path.absolute()
    if path.is_symlink():
        raise ValueError("transcript must not be a symlink")
    if path.is_relative_to(root):
        relative = path.relative_to(root)
        if (len(relative.parts) != 3 or relative.parts[:2] != (".botpipe", "transcripts")
                or re.fullmatch(r"round-[1-9][0-9]*\.md", relative.name) is None):
            raise ValueError("internal transcript must be .botpipe/transcripts/round-N.md")
        for directory in (root / ".botpipe", root / ".botpipe" / "transcripts"):
            if directory.is_symlink():
                raise ValueError("transcript directory must not be a symlink")
    elif path.resolve().is_relative_to(root):
        raise ValueError("external transcript must not point inside the candidate")
    return path


@activity(retry_safe=True)
def prepare_candidate(workspace: str, destination: str, name: str) -> str:
    """Copy one project context without touching the source workspace."""
    _name(name)
    source = Path(workspace).absolute().resolve(strict=True)
    target = Path(destination).absolute()
    run_folder = current_run().folder.resolve(strict=True)
    if not source.is_dir() or target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError("candidate source must be a directory and destination a directory")
    if target != run_folder / "candidate" or target == source or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("candidate destination must be the run-owned candidate outside the source")
    for relative in (f".botpipe/workflows/{name}", f"tests/runtime/test_{name}.py"):
        existing = source / relative
        if existing.exists() or existing.is_symlink():
            raise ValueError(f"generated workflow target already exists: {relative}")
    # The activity journal caches successful initialization. An interrupted
    # initialization may leave a partial copy at exactly this run-owned path.
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    try:
        for relative in _inventory(source):
            original = source / relative
            if not stat.S_ISREG(original.stat(follow_symlinks=False).st_mode):
                raise ValueError(f"project file is not regular: {relative}")
            copied = target / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, copied)
    except BaseException:
        shutil.rmtree(target)
        raise
    return str(target.resolve())


def _environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    host_checkout = str(Path(__file__).resolve().parents[3])
    entries = [str(root), host_checkout, *env.get("PYTHONPATH", "").split(os.pathsep)]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(entry for entry in entries if entry))
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("BOTPIPE_TRANSCRIPT", None)
    return env


def _run(argv: list[str], root: Path, env: dict[str, str], timeout: float) -> ProcessResult:
    return run_bounded_process(argv, cwd=root, env=env, timeout_seconds=timeout, max_stream_bytes=24_000, termination_grace_seconds=1)


def _check(root: Path, name: str, reference: str, transcript: Path, extra_argv: list[str] | None) -> Validation:
    errors: list[str] = []
    logs: list[str] = []
    expected = f".botpipe/workflows/{name}/flow.py:"
    package = root / ".botpipe" / "workflows" / name
    test = root / "tests" / "runtime" / f"test_{name}.py"
    if not reference.startswith(expected) or not _NAME.fullmatch(reference[len(expected):]):
        errors.append(f"reference must be {expected}<callable>")
    function = reference[len(expected):] if reference.startswith(expected) else ""
    if not (package / "flow.py").is_file():
        errors.append("generated flow.py is missing")
    if not test.is_file():
        errors.append(f"required generated test is missing: tests/runtime/test_{name}.py")
    try:
        metadata = tomllib.loads((package / "workflow.toml").read_text(encoding="utf-8"))
        if metadata.get("name") != name or (metadata.get("function") or metadata.get("entrypoint")) != function:
            errors.append("workflow.toml must name the package and select the reference callable")
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"workflow.toml: {exc}")
    env = _environment(root)
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.unlink(missing_ok=True)
    try:
        initial_digest = _digest(root)
    except (OSError, ValueError) as exc:
        return Validation(reference=reference, errors=[f"candidate surface: {exc}"], transcript=str(transcript))

    def execute(label: str, argv: list[str], timeout: float, *, transcript_test: bool = False) -> None:
        process_env = {**env, "BOTPIPE_TRANSCRIPT": str(transcript)} if transcript_test else env
        try:
            result = _run(argv, root, process_env, timeout)
            output = (result.stdout + "\n" + result.stderr).strip()[-12_000:]
            logs.append(f"{label}: exit={result.exit_code}, timeout={result.timed_out}\n{output}")
            if result.timed_out or result.exit_code != 0:
                errors.append(f"{label} {'timed out' if result.timed_out else f'exited {result.exit_code}'}: {output[-1200:] or '(no output)'}")
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{label}: {exc}")

    if not errors:
        # Compile without writing bytecode and resolve with Botpipe in another process.
        script = "from pathlib import Path; import sys; package=Path(sys.argv[1]); test=Path(sys.argv[2]); [compile(p.read_bytes(),str(p),'exec') for p in [*package.rglob('*.py'),test] if '__pycache__' not in p.parts]"
        execute("compile", [sys.executable, "-c", script, str(package), str(test)], 30)
    if not errors:
        script = """import sys
from pathlib import Path
from botpipe import Botpipe
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.runtime import Workflow
root, reference, name = Path.cwd(), sys.argv[1], sys.argv[2]
source = (root / '.botpipe' / 'workflows' / name / 'flow.py').resolve()
manifest = (source.parent / 'workflow.toml').resolve()
function = reference.rsplit(':', 1)[1]
matches = [e for e in discover_workflows(root, include_labs=False)
           if e.source_kind == 'workspace' and e.name == name and e.function == function
           and e.source_path == source and e.manifest_path == manifest]
assert len(matches) == 1, 'catalog does not select generated name, file and callable'
fn = resolve_workflow(reference, root)
assert isinstance(fn, Workflow), 'workflow reference is not a Botpipe @workflow'
"""
        execute("import and catalog", [sys.executable, "-c", script, reference, name], 30)
    if not errors:
        execute("generated test", [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "botpipe.workflows.workflow_author.transcript_plugin", f"tests/runtime/test_{name}.py"], 120, transcript_test=True)
        evidence = transcript.read_bytes() if transcript.is_file() else b""
        if b"## tests/runtime/test_" not in evidence:
            errors.append("generated test did not produce a fresh test transcript")
    if not errors and extra_argv:
        execute("additional test", extra_argv, 120)
    try:
        source_digest = _digest(root)
    except (OSError, ValueError) as exc:
        errors.append(f"candidate surface after tests: {exc}")
        source_digest = initial_digest
    if source_digest != initial_digest:
        errors.append("candidate source or dependencies changed during validation")
    transcript_digest = hashlib.sha256(transcript.read_bytes()).hexdigest() if transcript.is_file() else ""
    return Validation(reference=reference, success=not errors, errors=errors,
                      transcript=str(transcript), digest=f"{source_digest}:{transcript_digest}",
                      output="\n\n".join(logs)[-24_000:])


@activity(retry_safe=True)
def validate_candidate(root: str, name: str, reference: str, transcript: str, extra_argv: list[str] | None = None) -> Validation:
    """Run mandatory focused pytest and preserve independently checkable evidence."""
    _name(name)
    candidate = Path(root).absolute().resolve(strict=True)
    evidence = _transcript_path(candidate, transcript)
    if not candidate.is_dir():
        raise ValueError("candidate must be a directory")
    return _check(candidate, name, reference, evidence, extra_argv)


def verify_candidate(root: str, result: Validation) -> None:
    """Reject changed source or evidence after cached validation and before handoff."""
    candidate = Path(root).absolute().resolve(strict=True)
    transcript = _transcript_path(candidate, result.transcript)
    if not transcript.is_file():
        raise ValueError("candidate transcript is missing")
    actual = f"{_digest(candidate)}:{hashlib.sha256(transcript.read_bytes()).hexdigest()}"
    if actual != result.digest:
        raise ValueError("candidate files or transcript changed since validation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a generated Botpipe workflow")
    parser.add_argument("name")
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--reference")
    args = parser.parse_args(argv)
    try:
        _name(args.name)
        root = Path.cwd()
        if args.reference:
            reference = args.reference
        else:
            metadata = tomllib.loads((root / ".botpipe" / "workflows" / args.name / "workflow.toml").read_text(encoding="utf-8"))
            reference = f".botpipe/workflows/{args.name}/flow.py:{metadata.get('function') or metadata.get('entrypoint') or 'workflow'}"
        result = validate_candidate.__wrapped__(str(root), args.name, reference, args.transcript)
        print(result.output)
        for error in result.errors:
            print(error, file=sys.stderr)
        return 0 if result.success else 1
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"validation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
