"""Standard-library bootstrap for isolated candidate checks."""

from __future__ import annotations

import hashlib
import importlib.machinery
import inspect
import json
import os
import runpy
import sys
import traceback
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: bootstrap CONFIG RESULT")
    config_path = Path(sys.argv[1]).resolve(strict=True)
    result_path = Path(sys.argv[2]).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = Path(config["staged_root"]).resolve(strict=True)
    sources = [
        Path(x).resolve(strict=True)
        for x in config.get("project_import_roots", [str(root)])
    ]
    if any(not path.is_dir() or not _under(path, root) for path in sources):
        raise ValueError("project import roots must be directories inside staging")
    prefixes = set(config["project_prefixes"])
    deps = [Path(x).resolve(strict=True) for x in config["dependency_roots"]]
    script_dir = Path(__file__).resolve().parent
    stdlib = []
    for raw in sys.path:
        if not raw:
            continue
        path = Path(raw).resolve()
        if path not in [script_dir, root, *deps]:
            stdlib.append(str(path))
    sys.path[:] = [*(str(x) for x in sources), *(str(x) for x in deps), *stdlib]
    sys.meta_path.insert(0, _StagedImports(root, sources, prefixes))
    os.chdir(root)
    code = 0
    environment = {}
    try:
        environment = _environment(deps)
        if config["mode"] == "compile":
            from botpipe.discovery import resolve_workflow
            from botpipe.runtime import Workflow

            compiled = []
            for reference in config["workflow_refs"]:
                resolved = resolve_workflow(reference, workspace=root)
                if not isinstance(resolved, Workflow):
                    raise TypeError(
                        "Candidate reference must resolve to a @workflow callable"
                    )
                source = Path(inspect.getsourcefile(resolved.fn)).resolve(strict=True)
                # Import + signature/schema inspection validate this concrete source;
                # dynamic branches are only exercised by the requested test command.
                inspect.signature(resolved.fn)
                compiled.append(
                    {
                        "requested_reference": reference,
                        "workflow_name": resolved.name,
                        "workflow_version": resolved.version,
                        "callable_signature": str(inspect.signature(resolved.fn)),
                        "source_path": (
                            None if source is None else str(source.resolve())
                        ),
                        "source_sha256": None if source is None else _sha(source),
                    }
                )
            payload = {"ok": True, "compiled_workflows": compiled}
        elif config["mode"] == "python":
            code = _run(list(config["argv"]))
            payload = {"ok": code == 0, "python_exit_code": code}
        else:
            raise ValueError("unsupported bootstrap mode")
        origins = _origins()
        _validate(
            origins,
            root,
            prefixes,
            deps,
            [Path(value) for value in stdlib],
            Path(__file__).resolve(),
        )
        payload["module_origins"] = origins
    except BaseException as exc:  # noqa: BLE001 - subprocess diagnostic boundary includes SystemExit
        if isinstance(exc, SystemExit):
            code = (
                0 if exc.code is None else exc.code if isinstance(exc.code, int) else 1
            )
            payload = {"ok": code == 0, "python_exit_code": code}
            try:
                origins = _origins()
                _validate(
                    origins,
                    root,
                    prefixes,
                    deps,
                    [Path(value) for value in stdlib],
                    Path(__file__).resolve(),
                )
                payload["module_origins"] = origins
            except BaseException as origin:  # noqa: BLE001 - preserve the original failed probe
                code = 1
                payload = _error(origin)
        else:
            code = 1
            payload = _error(exc)
    payload["environment"] = environment
    temporary = result_path.with_name(f".{result_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(temporary, result_path)
    return code


class _StagedImports:
    """Resolve project names only in staging, including namespace packages."""

    def __init__(self, root: Path, sources: list[Path], prefixes: set[str]):
        self.root, self.sources, self.prefixes = root, sources, prefixes

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] not in self.prefixes:
            return None
        search = (
            self.sources
            if path is None
            else [
                Path(entry)
                for entry in path
                if _under(Path(entry).resolve(), self.root)
            ]
        )
        spec = importlib.machinery.PathFinder.find_spec(
            fullname, [str(p) for p in search]
        )
        if spec is None:
            raise ModuleNotFoundError(
                f"project module {fullname!r} is missing from staged tree",
                name=fullname,
            )
        return spec


def _environment(deps: list[Path]) -> dict[str, object]:
    import importlib.metadata

    return {
        "interpreter": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "dependency_roots": [str(path) for path in deps],
        "distributions": sorted(
            (
                {"name": dist.metadata["Name"], "version": dist.version}
                for dist in importlib.metadata.distributions()
                if dist.metadata.get("Name")
            ),
            key=lambda item: (item["name"], item["version"] or ""),
        ),
    }


def _run(argv: list[str]) -> int:
    if not argv:
        raise ValueError("Python argv must be non-empty")
    if argv[0] in {"pytest", "py.test"}:
        sys.argv = [argv[0], *argv[1:]]
        runpy.run_module("pytest", run_name="__main__", alter_sys=True)
        return 0
    first = Path(argv[0]).name.lower()
    if not (
        first.startswith("python")
        or Path(argv[0]).resolve() == Path(sys.executable).resolve()
    ):
        raise ValueError("Python check must start with pytest or interpreter")
    if len(argv) >= 3 and argv[1] == "-c":
        sys.argv = ["-c", *argv[3:]]
        exec(compile(argv[2], "<candidate-check>", "exec"), {"__name__": "__main__"})  # noqa: S102 - explicitly requested Python command
        return 0
    if len(argv) >= 3 and argv[1] == "-m":
        sys.argv = [argv[2], *argv[3:]]
        runpy.run_module(argv[2], run_name="__main__", alter_sys=True)
        return 0
    if len(argv) >= 2:
        script = Path(argv[1])
        script = script if script.is_absolute() else Path.cwd() / script
        sys.argv = [str(script), *argv[2:]]
        runpy.run_path(str(script.resolve(strict=True)), run_name="__main__")
        return 0
    raise ValueError("Python check must select module or script")


def _origins() -> list[dict[str, str]]:
    result = []
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            continue
        try:
            path = Path(raw).resolve(strict=True)
        except OSError:
            continue
        if path.is_file():
            result.append({"module": name, "origin": str(path), "sha256": _sha(path)})
    return result


def _validate(
    origins: list[dict[str, str]],
    root: Path,
    prefixes: set[str],
    deps: list[Path],
    stdlib_roots: list[Path],
    bootstrap_path: Path,
) -> None:
    approved_roots = [root, *deps, *stdlib_roots]
    for entry in origins:
        name = entry["module"]
        origin = Path(entry["origin"])
        if name.split(".", 1)[0] in prefixes and (not _under(origin, root)):
            raise RuntimeError(
                f"project module {name!r} loaded outside staged tree: {origin}"
            )
        if origin != bootstrap_path and not any(
            _under(origin, approved) for approved in approved_roots
        ):
            raise RuntimeError(
                f"module {name!r} loaded from an unapproved root: {origin}"
            )


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _error(exc: BaseException) -> dict[str, object]:
    return {
        "ok": False,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(limit=20),
    }


if __name__ == "__main__":
    raise SystemExit(main())
