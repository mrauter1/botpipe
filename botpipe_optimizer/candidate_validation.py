"""Isolated compilation and checks for frozen workflow candidates."""
from __future__ import annotations
import importlib.metadata, json, os, shlex, sys, tempfile
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .execution_trees import ExecutionArm, FrozenExecutionTree, assert_execution_arm_unchanged, cleanup_owned_directory, materialize_execution_arm, snapshot_execution_arm, verify_frozen_execution_tree
from .processes import ProcessResult, run_bounded_process
VALIDATION_RESULT_SCHEMA = 'botpipe.validation-result.v2'

class CheckResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    phase: str
    kind: Literal['compile_probe', 'python_check', 'external_check']
    argv: tuple[str, ...]
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    elapsed_seconds: float = Field(ge=0)
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    result: Mapping[str, Any] | None = None

class ValidationResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, populate_by_name=True)
    schema_version: Literal['botpipe.validation-result.v2'] = Field(
        default=VALIDATION_RESULT_SCHEMA,
        alias='schema',
    )
    success: bool
    baseline_surface_id: str
    candidate_surface_id: str
    baseline_execution_tree_id: str
    candidate_execution_tree_id: str
    validated_root: str
    derived_changes: tuple[str, ...]
    compiled_workflows: tuple[Mapping[str, Any], ...] = ()
    checks: tuple[CheckResult, ...]
    environment: Mapping[str, Any]
    errors: tuple[str, ...] = ()
    evaluation_comparison: Mapping[str, Any] | None = None

    def with_evaluation(self, comparison: Mapping[str, Any]) -> 'ValidationResult':
        if not self.success:
            raise ValueError('evaluation cannot attach to unsuccessful validation')
        if self.evaluation_comparison is not None:
            raise ValueError('evaluation already attached')
        if not isinstance(comparison, Mapping) or not comparison:
            raise ValueError('comparison must be non-empty')
        return self.model_copy(update={'evaluation_comparison': dict(comparison)})

def validate_frozen_candidate(
    snapshot: FrozenExecutionTree,
    *,
    baseline_surface_manifest: Mapping[str, Any],
    candidate_surface_manifest: Mapping[str, Any],
    expected_baseline_root: Path,
    expected_candidate_root: Path,
    expected_boundary: Mapping[str, Any],
    baseline_surface_kind: str,
    candidate_surface_kind: str,
    workflow_refs: Sequence[str],
    staging_parent: Path,
    allowed_added_path_prefixes: Sequence[str] = (),
    allowed_added_exact_paths: Sequence[str] = (),
    target_test_argv: Sequence[str] | None = None,
    target_test_command: str | None = None,
    interpreter: Path | str = sys.executable,
    dependency_roots: Sequence[Path] | None = None,
    compile_timeout_seconds: float = 60,
    test_timeout_seconds: float = 600,
    max_stream_bytes: int = 1024 * 1024,
    termination_grace_seconds: float = 5,
) -> ValidationResult:
    from .candidate_surfaces import validate_surface_manifest

    verify_frozen_execution_tree(snapshot)
    baseline_surface_manifest = validate_surface_manifest(
        baseline_surface_manifest,
        expected_root=expected_baseline_root,
        expected_boundary=expected_boundary,
        expected_surface_kind=baseline_surface_kind,
    )
    candidate_surface_manifest = validate_surface_manifest(
        candidate_surface_manifest,
        expected_root=expected_candidate_root,
        expected_boundary=expected_boundary,
        expected_surface_kind=candidate_surface_kind,
        baseline_manifest=baseline_surface_manifest,
        allowed_added_path_prefixes=allowed_added_path_prefixes,
        allowed_added_exact_paths=allowed_added_exact_paths,
    )
    raw = Path(_text(candidate_surface_manifest.get('root', candidate_surface_manifest.get('surface_root'))))
    if raw.is_symlink() or raw.resolve(strict=True) != Path(expected_candidate_root).resolve(strict=True):
        raise ValueError('candidate manifest root must match expected_candidate_root')
    refs = tuple((_text(x) for x in workflow_refs))
    if not refs or len(set(refs)) != len(refs):
        raise ValueError('workflow_refs must be unique and non-empty')
    argv = normalize_target_argv(target_test_argv=target_test_argv, target_test_command=target_test_command, interpreter=str(interpreter))
    baseline_id = _text(baseline_surface_manifest.get('surface_id'))
    candidate_id = _text(candidate_surface_manifest.get('surface_id'))
    base = _digests(baseline_surface_manifest)
    cand = _digests(candidate_surface_manifest)
    changes = tuple(sorted((x for x in cand if x not in base or cand[x] != base[x])))
    parent = Path(staging_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    baseline_arm = candidate_arm = None
    try:
        baseline_arm = materialize_execution_arm(snapshot, parent)
        candidate_arm = materialize_execution_arm(snapshot, parent, candidate_manifest=candidate_surface_manifest)
        expected = snapshot_execution_arm(candidate_arm)
        deps = tuple((Path(x).resolve(strict=True) for x in (dependency_roots if dependency_roots is not None else _dependency_roots(snapshot.root))))
        prefixes = _prefixes(candidate_arm.root)
        checks = []
        errors = []
        compile_check = _bootstrap(candidate_arm, parent, Path(interpreter), deps, prefixes, {'mode': 'compile', 'workflow_refs': list(refs)}, compile_timeout_seconds, max_stream_bytes, termination_grace_seconds, 'compile')
        checks.append(compile_check)
        assert_execution_arm_unchanged(expected, candidate_arm.root, phase='compile')
        compiled = _compiled(compile_check, refs, candidate_arm.root)
        if compile_check.exit_code != 0 or compile_check.timed_out or compile_check.cancelled or (not compiled):
            errors.append(_failure(compile_check))
        if not errors and argv is not None:
            if _python(argv, str(interpreter)):
                check = _bootstrap(candidate_arm, parent, Path(interpreter), deps, prefixes, {'mode': 'python', 'argv': list(argv)}, test_timeout_seconds, max_stream_bytes, termination_grace_seconds, 'test')
            else:
                check = _check(run_bounded_process(argv, cwd=candidate_arm.root, timeout_seconds=test_timeout_seconds, max_stream_bytes=max_stream_bytes, termination_grace_seconds=termination_grace_seconds, env=_env()), 'test', 'external_check')
            checks.append(check)
            assert_execution_arm_unchanged(expected, candidate_arm.root, phase='test')
            if check.exit_code != 0 or check.timed_out or check.cancelled:
                errors.append(_failure(check))
        verify_frozen_execution_tree(snapshot)
        current_baseline = validate_surface_manifest(
            baseline_surface_manifest,
            expected_root=expected_baseline_root,
            expected_boundary=expected_boundary,
            expected_surface_kind=baseline_surface_kind,
        )
        current_candidate = validate_surface_manifest(
            candidate_surface_manifest,
            expected_root=expected_candidate_root,
            expected_boundary=expected_boundary,
            expected_surface_kind=candidate_surface_kind,
            baseline_manifest=current_baseline,
            allowed_added_path_prefixes=allowed_added_path_prefixes,
            allowed_added_exact_paths=allowed_added_exact_paths,
        )
        if current_baseline['surface_id'] != baseline_id or current_candidate['surface_id'] != candidate_id:
            raise ValueError('surface changed during validation')
        return ValidationResult(success=not errors, baseline_surface_id=baseline_id, candidate_surface_id=candidate_id, baseline_execution_tree_id=baseline_arm.execution_tree_id, candidate_execution_tree_id=candidate_arm.execution_tree_id, validated_root=str(raw.resolve()), derived_changes=changes, compiled_workflows=tuple(compiled), checks=tuple(checks), environment=_environment(Path(interpreter), deps), errors=tuple(errors))
    finally:
        for arm in (candidate_arm, baseline_arm):
            if arm is not None and arm.root.exists():
                cleanup_owned_directory(arm.root, owned_parent=arm.owned_parent, ownership_token=arm.ownership_token)

def normalize_target_argv(*, target_test_argv: Sequence[str] | None, target_test_command: str | None, interpreter: str) -> tuple[str, ...] | None:
    if target_test_argv is not None and target_test_command is not None:
        raise ValueError('target_test_argv and target_test_command conflict')
    if target_test_argv is None and target_test_command is None:
        return None
    if target_test_argv is not None:
        if isinstance(target_test_argv, (str, bytes)) or not target_test_argv:
            raise ValueError('target_test_argv must be non-empty')
        result = tuple((_text(x) for x in target_test_argv))
    else:
        if os.name == 'nt':
            raise ValueError('target_test_argv required on Windows')
        result = tuple(shlex.split(_text(target_test_command)))
    return (interpreter, '-m', 'pytest', *result[1:]) if result[0] in {'pytest', 'py.test'} else result

def _bootstrap(arm: ExecutionArm, parent: Path, interpreter: Path, deps: Sequence[Path], prefixes: Sequence[str], payload: Mapping[str, Any], timeout: float, max_bytes: int, grace: float, phase: str) -> CheckResult:
    with tempfile.TemporaryDirectory(prefix='validation-probe-', dir=parent) as temporary:
        temp = Path(temporary)
        config = temp / 'config.json'
        result = temp / 'result.json'
        config.write_text(json.dumps({'staged_root': str(arm.root), 'dependency_roots': [str(x) for x in deps], 'project_prefixes': list(prefixes), **dict(payload)}, sort_keys=True), encoding='utf-8')
        bootstrap = Path(__file__).with_name('_isolation_bootstrap.py').resolve(strict=True)
        process = run_bounded_process([str(interpreter), '-I', '-S', str(bootstrap), str(config), str(result)], cwd=arm.root, timeout_seconds=timeout, max_stream_bytes=max_bytes, termination_grace_seconds=grace, env=_env())
        data = None
        if result.is_file():
            try:
                raw = json.loads(result.read_text(encoding='utf-8'))
                data = dict(raw) if isinstance(raw, Mapping) else None
            except (OSError, ValueError):
                pass
        return _check(process, phase, 'compile_probe' if phase == 'compile' else 'python_check', data)

def _check(process: ProcessResult, phase: str, kind: Literal['compile_probe', 'python_check', 'external_check'], result: Mapping[str, Any] | None=None) -> CheckResult:
    return CheckResult(phase=phase, kind=kind, result=result, **process.to_dict())

def _compiled(check: CheckResult, refs: Sequence[str], root: Path) -> list[Mapping[str, Any]]:
    if check.result is None or check.result.get('ok') is not True:
        return []
    values = check.result.get('compiled_workflows')
    if not isinstance(values, list) or len(values) != len(refs):
        return []
    normalized = []
    seen = []
    for value in values:
        if not isinstance(value, Mapping):
            return []
        reference = value.get('requested_reference')
        source = value.get('source_path')
        digest = value.get('source_sha256')
        if not all((isinstance(x, str) and x for x in (reference, value.get('workflow_name'), source, digest))):
            return []
        path = Path(source).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError:
            return []
        if _sha(path) != digest:
            return []
        seen.append(reference)
        normalized.append(dict(value))
    return normalized if tuple(seen) == tuple(refs) and len(set(seen)) == len(seen) else []

def _dependency_roots(source: Path) -> tuple[Path, ...]:
    return tuple(sorted({Path(x).resolve() for x in sys.path if x and Path(x).is_dir() and ('site-packages' in Path(x).parts or 'dist-packages' in Path(x).parts) and (Path(x).resolve() != source.resolve())}, key=str))

def _prefixes(root: Path) -> tuple[str, ...]:
    return tuple((x.name if x.is_dir() else x.stem for x in sorted(root.iterdir()) if not x.name.startswith('.') and (x.is_dir() and (x / '__init__.py').is_file() or (x.is_file() and x.suffix == '.py'))))

def _environment(interpreter: Path, deps: Sequence[Path]) -> dict[str, Any]:
    return {'interpreter': str(interpreter.resolve()), 'python_version': sys.version, 'implementation': sys.implementation.name, 'platform': sys.platform, 'dependency_roots': [str(x) for x in deps], 'distributions': [{'name': d.metadata.get('Name'), 'version': d.version} for d in importlib.metadata.distributions() if d.metadata.get('Name')]}

def _env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONUSERBASE'):
        env.pop(key, None)
    env['PYTHONNOUSERSITE'] = '1'
    return env

def _digests(manifest: Mapping[str, Any]) -> dict[str, str]:
    values = manifest.get('files')
    if not isinstance(values, list):
        raise ValueError('manifest files required')
    result = {}
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError('manifest file entries must be objects')
        path = _text(value.get('relative_path', value.get('path')))
        digest = _text(value.get('surface_sha256', value.get('sha256')))
        if path in result:
            raise ValueError('duplicate manifest path')
        result[path] = digest
    return result

def _python(argv: Sequence[str], interpreter: str) -> bool:
    return Path(argv[0]).name.lower().startswith('python') or Path(argv[0]).resolve() == Path(interpreter).resolve()

def _failure(check: CheckResult) -> str:
    return f'{check.phase} timed out' if check.timed_out else f'{check.phase} was cancelled' if check.cancelled else f'{check.phase} failed with exit code {check.exit_code}'

def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('expected non-empty string')
    return value.strip()

def _sha(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
__all__ = ['CheckResult', 'ValidationResult', 'normalize_target_argv', 'validate_frozen_candidate']
