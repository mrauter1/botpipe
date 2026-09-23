"""Journaled optimizer-v2 handoff and evaluation helpers for labs consumers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from botpipe import UncertainOperation, activity, current_run
from botpipe.storage import sync_directory


def _resolve_file(workspace: str | Path, value: str, label: str) -> Path:
    raw = Path(value).expanduser()
    path = raw if raw.is_absolute() else Path(workspace) / raw
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return resolved


def _manifest_files(payload: Mapping[str, Any]) -> dict[str, str]:
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("optimizer baseline manifest must define files")
    result: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, Mapping):
            raise TypeError("optimizer baseline manifest files must be objects")
        relative = entry.get("path", entry.get("relative_path"))
        digest = entry.get("sha256", entry.get("surface_sha256"))
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("optimizer baseline file path is missing")
        if not isinstance(digest, str) or not digest.strip():
            raise ValueError("optimizer baseline file digest is missing")
        if relative in result:
            raise ValueError("optimizer baseline file paths must be unique")
        result[relative] = digest
    return result


@activity(retry_safe=True, name="load optimizer candidate handoff")
def load_optimizer_candidate_handoff(
    *,
    workspace: str,
    optimization_receipt_path: str,
    candidate_id: str,
    expected_selected_workflow: str,
    allowed_kinds: Sequence[str],
    selected_workflow_reference: str | None = None,
    selected_workflow_source_path: str | None = None,
    max_evidence_bytes: int = 50 * 1024 * 1024,
    max_snapshot_bytes: int = 50 * 1024 * 1024,
) -> dict[str, Any]:
    """Validate one accepted optimizer receipt and return its immutable handoff."""

    from botpipe.discovery import resolve_workflow
    from botpipe.surface_identity import derive_workflow_surface_manifest
    from botpipe_optimizer.recommendations import load_optimization_candidate

    receipt_path = _resolve_file(
        workspace, optimization_receipt_path, "optimization_receipt_path"
    )
    selection = load_optimization_candidate(
        optimization_receipt_path=receipt_path,
        candidate_id=candidate_id,
        expected_selected_workflow=expected_selected_workflow,
        allowed_kinds=tuple(allowed_kinds),
        max_evidence_bytes=max_evidence_bytes,
        max_snapshot_bytes=max_snapshot_bytes,
    )
    current_surface = derive_workflow_surface_manifest(
        Path(workspace),
        resolve_workflow(
            selected_workflow_reference or expected_selected_workflow, workspace
        ),
    )
    if current_surface["surface_id"] != selection.receipt.baseline_surface_manifest_id:
        raise ValueError(
            "optimizer baseline surface is stale relative to selected workflow"
        )
    baseline = json.loads(selection.baseline_surface_manifest_path.read_text())
    if not isinstance(baseline, dict):
        raise TypeError("optimizer baseline manifest must contain an object")
    files = _manifest_files(baseline)
    return {
        "receipt_path": str(receipt_path),
        "receipt": selection.receipt.model_dump(mode="json", by_alias=True),
        "candidate_set": selection.candidate_set.model_dump(mode="json", by_alias=True),
        "candidate": selection.candidate.model_dump(mode="json"),
        "candidate_id": selection.candidate.candidate_id,
        "candidate_kind": selection.candidate.kind,
        "candidate_set_id": selection.candidate_set.candidate_set_id,
        "evidence_snapshot_path": str(selection.evidence_snapshot_path),
        "baseline_surface_manifest_path": str(selection.baseline_surface_manifest_path),
        "refinement_handoff_path": str(selection.refinement_handoff_path),
        "baseline_surface_manifest": baseline,
        "baseline_files": files,
        "candidate_paths": sorted(files),
        "selected_workflow_source_path": selected_workflow_source_path,
        "improvement": "not_evaluated",
    }


def validate_materialized_handoff(
    handoff: Mapping[str, Any], authoritative_hashes: Mapping[str, str]
) -> None:
    """Bind a materialized candidate workspace to the recorded baseline bytes."""

    raw = handoff.get("baseline_files")
    if not isinstance(raw, Mapping):
        raise TypeError("optimizer handoff baseline_files must be an object")
    expected = {str(path): str(digest) for path, digest in raw.items()}
    actual = {str(path): str(digest) for path, digest in authoritative_hashes.items()}
    if actual != expected:
        raise ValueError(
            "optimizer baseline surface is stale relative to the selected workflow"
        )


def evaluation_suite_identity(
    validated_manifest: Mapping[str, Any], *, source_candidate_id: str | None
) -> str:
    """Derive the identity of a validated suite, including its candidate source."""

    payload = {
        "schema": "botpipe.workflow_eval_suite/v2",
        "source_candidate_id": source_candidate_id,
        "validated_manifest": dict(validated_manifest),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return f"evaluation_suite_{hashlib.sha256(encoded).hexdigest()}"


def staged_workflow_reference(
    reference: str, *, relative_source: str, function: str | None
) -> str:
    """Translate file selectors to the matching path inside an execution arm."""

    location, separator, selected_function = reference.rpartition(":")
    candidate = location if separator else reference
    if Path(candidate).suffix == ".py" or Path(candidate).is_absolute():
        function_name = selected_function or (function or "").split(".", 1)[0]
        return (
            f"{relative_source}:{function_name}" if function_name else relative_source
        )
    return reference


@activity(retry_safe=True, name="freeze candidate baseline")
def freeze_candidate_baseline(
    *,
    candidate_workspace: Any,
    selected_workflow: str,
    staging_parent: str,
    workspace: str,
) -> dict[str, Any]:
    """Capture the authoritative project and editable surface before model edits."""

    from botpipe.discovery import resolve_workflow
    from botpipe.surface_identity import (
        derive_workflow_surface_manifest,
        workflow_surface_location,
    )
    from botpipe_optimizer.candidates import freeze_candidate_workspace

    workspace_root = Path(workspace).resolve()
    resolved = resolve_workflow(selected_workflow, workspace)
    source_root, selected, _ = workflow_surface_location(workspace_root, resolved)
    source_manifest = derive_workflow_surface_manifest(workspace_root, resolved)
    selected_package_root = None
    selected_package_import_path = None
    execution_source_root = None
    if source_root != workspace_root:
        relative = selected.relative_to(source_root)
        selected_package_import_path = relative.parts[0]
        selected_package_root = source_root / selected_package_import_path
        execution_source_root = workspace_root
    bundle = freeze_candidate_workspace(
        candidate_workspace,
        Path(staging_parent),
        boundary=source_manifest["boundary"],
        execution_source_root=execution_source_root,
        selected_package_root=selected_package_root,
        selected_package_import_path=selected_package_import_path,
    )
    if bundle.baseline_surface_manifest["surface_id"] != source_manifest["surface_id"]:
        raise ValueError(
            "candidate baseline does not match the selected workflow surface"
        )
    snapshot = bundle.snapshot
    return {
        "snapshot": {
            "root": str(snapshot.root),
            "execution_tree_id": snapshot.execution_tree_id,
            "manifest": dict(snapshot.manifest),
            "source_records": [dict(item) for item in snapshot.source_records],
            "owned_parent": str(snapshot.owned_parent),
            "ownership_token": snapshot.ownership_token,
        },
        "baseline_surface_manifest": dict(bundle.baseline_surface_manifest),
        "boundary": dict(bundle.boundary),
    }


def _restore_frozen_bundle(value: Mapping[str, Any]):
    from botpipe_optimizer.candidates import FrozenCandidateBundle
    from botpipe_optimizer.execution_trees import FrozenExecutionTree

    raw = value.get("snapshot")
    if not isinstance(raw, Mapping):
        raise TypeError("frozen candidate snapshot is missing")
    snapshot = FrozenExecutionTree(
        root=Path(str(raw["root"])),
        execution_tree_id=str(raw["execution_tree_id"]),
        manifest=dict(raw["manifest"]),
        source_records=tuple(dict(item) for item in raw["source_records"]),
        owned_parent=Path(str(raw["owned_parent"])),
        ownership_token=str(raw["ownership_token"]),
    )
    return FrozenCandidateBundle(
        snapshot=snapshot,
        baseline_surface_manifest=dict(value["baseline_surface_manifest"]),
        boundary=dict(value["boundary"]),
    )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(dict(value), stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _revalidate_frozen_evaluation(
    value: Mapping[str, Any], *, staging_parent: str, invocation_id: str
) -> dict[str, Any]:
    """Verify that a replayed pre-build evaluation snapshot is still exact."""

    from botpipe_optimizer.paired_evaluation import (
        _assert_frozen,
        load_evaluation_spec,
    )

    result = dict(value)
    if result.get("invocation_id") != invocation_id:
        raise ValueError("frozen evaluation invocation identity is stale")
    parent = Path(staging_parent).resolve()
    freeze_root = Path(str(result.get("freeze_root", "")))
    if (
        not freeze_root.is_absolute()
        or freeze_root.is_symlink()
        or not freeze_root.is_dir()
        or not freeze_root.resolve().is_relative_to(parent)
    ):
        raise ValueError("frozen evaluation root is unavailable or outside staging")
    frozen_inputs = result.get("frozen_inputs")
    if not isinstance(frozen_inputs, Mapping):
        raise TypeError("frozen evaluation input identities are missing")
    inputs_root = freeze_root / "inputs"
    frozen = {
        "spec_path": inputs_root / "evaluation-spec.json",
        "evaluator_path": Path(str(result.get("evaluator_path", ""))),
        "case_input_path": Path(str(result.get("case_input_path", ""))),
        **dict(frozen_inputs),
    }
    if any(
        not Path(frozen[key]).resolve().is_relative_to(freeze_root.resolve())
        for key in ("spec_path", "evaluator_path", "case_input_path")
    ):
        raise ValueError("frozen evaluation inputs escaped their owned directory")
    _assert_frozen(frozen)
    source_spec, source_spec_id = load_evaluation_spec(frozen["spec_path"])
    if source_spec_id != result.get("source_spec_id"):
        raise ValueError("frozen source evaluation specification changed")
    spec_path = Path(str(result.get("evaluation_spec_path", "")))
    if (
        spec_path.is_symlink()
        or spec_path.resolve() != (freeze_root / "evaluation-spec.json").resolve()
        or _file_sha256(spec_path) != result.get("evaluation_spec_file_id")
    ):
        raise ValueError("frozen portable evaluation specification changed")
    portable, portable_id = load_evaluation_spec(spec_path)
    if portable_id != result.get("evaluation_spec_id"):
        raise ValueError("frozen evaluation specification identity is stale")
    if (
        portable.evaluator_path != str(frozen["evaluator_path"])
        or portable.case_input_path != str(frozen["case_input_path"])
        or portable.evaluator_content_id != source_spec.evaluator_content_id
        or portable.case_input_content_id != source_spec.case_input_content_id
    ):
        raise ValueError("frozen evaluation specification inputs are stale")
    return result


@activity(retry_safe=True, name="freeze improvement evaluation inputs")
def _freeze_improvement_evaluation_activity(
    *,
    workspace: str,
    evaluation_spec_path: str,
    staging_parent: str,
    invocation_id: str,
) -> dict[str, Any]:
    """Copy an evaluation plan and all executable inputs before candidate work."""

    from botpipe_optimizer.paired_evaluation import _freeze, load_evaluation_spec

    parent = Path(staging_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(invocation_id.encode()).hexdigest()
    destination = parent / f"frozen-improvement-evaluation-{suffix}"
    if destination.exists():
        record = _read_json(destination / "freeze-record.json")
        return _revalidate_frozen_evaluation(
            record, staging_parent=staging_parent, invocation_id=invocation_id
        )

    source_path = _resolve_file(workspace, evaluation_spec_path, "evaluation_spec_path")
    spec, source_spec_id = load_evaluation_spec(source_path)
    temporary = Path(tempfile.mkdtemp(prefix=".freeze-evaluation-", dir=parent))
    try:
        raw_frozen = _freeze(spec, source_path, temporary / "inputs")
        final_inputs = destination / "inputs"
        evaluator_path = final_inputs / raw_frozen["evaluator_path"].name
        case_input_path = final_inputs / raw_frozen["case_input_path"].name
        portable_payload = spec.model_dump(mode="json", by_alias=True)
        original_evaluator_path = portable_payload["evaluator_path"]
        portable_payload["evaluator_path"] = str(evaluator_path)
        portable_payload["case_input_path"] = str(case_input_path)
        portable_payload["evaluator_argv"] = [
            str(evaluator_path) if item == original_evaluator_path else item
            for item in portable_payload["evaluator_argv"]
        ]
        portable_path = temporary / "evaluation-spec.json"
        _atomic_json(portable_path, portable_payload)
        _, portable_id = load_evaluation_spec(portable_path)
        record = {
            "invocation_id": invocation_id,
            "freeze_root": str(destination),
            "evaluation_spec_path": str(destination / "evaluation-spec.json"),
            "evaluation_spec_id": portable_id,
            "evaluation_spec_file_id": _file_sha256(portable_path),
            "source_spec_id": source_spec_id,
            "evaluator_path": str(evaluator_path),
            "case_input_path": str(case_input_path),
            "frozen_inputs": {
                "spec_file_id": raw_frozen["spec_file_id"],
                "evaluator_id": raw_frozen["evaluator_id"],
                "case_input_id": raw_frozen["case_input_id"],
                "evaluator_executable": raw_frozen["evaluator_executable"],
            },
        }
        _atomic_json(temporary / "freeze-record.json", record)
        os.replace(temporary, destination)
        sync_directory(parent)
        return _revalidate_frozen_evaluation(
            record, staging_parent=staging_parent, invocation_id=invocation_id
        )
    finally:
        if temporary.exists():
            import shutil

            shutil.rmtree(temporary)


def freeze_improvement_evaluation(
    *,
    workspace: str,
    evaluation_spec_path: str,
    staging_parent: str,
    invocation_id: str,
) -> dict[str, Any]:
    """Freeze evaluator goalposts and revalidate their bytes on every replay."""

    result = _freeze_improvement_evaluation_activity(
        workspace=workspace,
        evaluation_spec_path=evaluation_spec_path,
        staging_parent=staging_parent,
        invocation_id=invocation_id,
    )
    return _revalidate_frozen_evaluation(
        result, staging_parent=staging_parent, invocation_id=invocation_id
    )


def _attempt_id(
    invocation_id: str,
    spec_id: str,
    baseline_surface_id: str,
    candidate_surface_id: str,
    baseline_tree_id: str,
    candidate_tree_id: str,
) -> str:
    value = {
        "invocation_id": invocation_id,
        "spec_id": spec_id,
        "baseline_surface_id": baseline_surface_id,
        "candidate_surface_id": candidate_surface_id,
        "baseline_execution_tree_id": baseline_tree_id,
        "candidate_execution_tree_id": candidate_tree_id,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@activity(name="validate frozen candidate and optional paired evaluation")
def _validate_candidate_and_compare_activity(
    *,
    candidate_workspace: Any,
    frozen_candidate: Mapping[str, Any],
    selected_workflow: str,
    staging_parent: str,
    target_test_argv: Sequence[str],
    validation_timeout: float,
    evaluation_spec_path: str | None = None,
    workspace: str,
    invocation_id: str,
) -> dict[str, Any]:
    """Validate one frozen candidate and optionally execute one frozen pair."""

    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
        validate_candidate,
    )
    from botpipe_optimizer.execution_trees import (
        ExecutionArm,
        assert_execution_arm_unchanged,
        cleanup_owned_directory,
        materialize_execution_arm,
        snapshot_execution_arm,
    )
    from botpipe_optimizer.paired_evaluation import (
        finalize_paired_evaluation_record,
        load_evaluation_spec,
        run_paired_evaluation,
        validate_paired_evaluation_record,
    )

    bundle = _restore_frozen_bundle(frozen_candidate)
    baseline_arm = candidate_arm = None
    try:
        validation = validate_candidate(
            candidate_workspace,
            bundle,
            workflow_refs=(selected_workflow,),
            staging_parent=Path(staging_parent),
            target_test_argv=tuple(target_test_argv),
            test_timeout_seconds=validation_timeout,
        )
        manifest = candidate_manifest(candidate_workspace)
        candidate_surface = candidate_surface_manifest(candidate_workspace, bundle)
        paired: dict[str, Any] = {
            "schema": "botpipe.optimizer.paired_evaluation/v1",
            "evaluation": "not_evaluated",
            "execution_state": "not_run",
            "comparison": {"state": "not_evaluated"},
            "automatic_promotion": False,
        }
        if validation.success and manifest.changed_paths and evaluation_spec_path:
            spec_path = _resolve_file(
                workspace, evaluation_spec_path, "evaluation_spec_path"
            )
            raw_baseline_arm = materialize_execution_arm(
                bundle.snapshot,
                Path(staging_parent),
                candidate_manifest=bundle.baseline_surface_manifest,
            )
            baseline_arm = ExecutionArm(
                root=raw_baseline_arm.root,
                execution_tree_id=raw_baseline_arm.execution_tree_id,
                manifest=raw_baseline_arm.manifest,
                surface_id=str(bundle.baseline_surface_manifest["surface_id"]),
                owned_parent=raw_baseline_arm.owned_parent,
                ownership_token=raw_baseline_arm.ownership_token,
            )
            candidate_arm = materialize_execution_arm(
                bundle.snapshot,
                Path(staging_parent),
                candidate_manifest=candidate_surface,
                removed_paths=manifest.removed_paths,
            )
            _, spec_id = load_evaluation_spec(spec_path)
            attempt_id = _attempt_id(
                invocation_id,
                spec_id,
                str(baseline_arm.surface_id),
                str(candidate_arm.surface_id),
                baseline_arm.execution_tree_id,
                candidate_arm.execution_tree_id,
            )
            parent = Path(staging_parent)
            suffix = hashlib.sha256(invocation_id.encode()).hexdigest()
            attempt_path = parent / f"paired-evaluation-attempt-{suffix}.json"
            cache_path = parent / f"paired-evaluation-cache-{suffix}.json"
            output_root = parent / f"paired-evaluation-output-{suffix}"
            if cache_path.is_file():
                paired = validate_paired_evaluation_record(
                    _read_json(cache_path),
                    evaluation_spec_path=spec_path,
                    baseline_surface_id=str(baseline_arm.surface_id),
                    candidate_surface_id=str(candidate_arm.surface_id),
                    baseline_execution_tree_id=baseline_arm.execution_tree_id,
                    candidate_execution_tree_id=candidate_arm.execution_tree_id,
                    allowed_output_parent=parent,
                    expected_invocation_id=invocation_id,
                )
                if paired.get("evaluation_attempt_id") != attempt_id:
                    raise ValueError("paired evaluation attempt identity is stale")
            elif attempt_path.is_file():
                attempt = _read_json(attempt_path)
                if (
                    attempt.get("attempt_id") != attempt_id
                    or attempt.get("invocation_id") != invocation_id
                ):
                    raise ValueError(
                        "paired evaluation inputs changed; start a new improvement run"
                    )
                raise UncertainOperation(
                    "Paired evaluation outcome is unresolved; recover its result before "
                    "continuing. Retrying will not relaunch evaluator arms.",
                    current_run().operation_id,
                )
            else:
                _atomic_json(
                    attempt_path,
                    {
                        "schema": "botpipe.optimizer.paired_evaluation_attempt/v1",
                        "attempt_id": attempt_id,
                        "invocation_id": invocation_id,
                        "spec_id": spec_id,
                        "execution_output_root": str(output_root.resolve()),
                        "state": "started",
                    },
                )
                paired = finalize_paired_evaluation_record(
                    {
                        **run_paired_evaluation(
                            evaluation_spec_path=spec_path,
                            baseline_arm=baseline_arm,
                            candidate_arm=candidate_arm,
                            output_root=output_root,
                            snapshot_arm=snapshot_execution_arm,
                            assert_arm_unchanged=assert_execution_arm_unchanged,
                        ),
                        "invocation_id": invocation_id,
                        "evaluation_attempt_id": attempt_id,
                    }
                )
                _atomic_json(cache_path, paired)
                _atomic_json(
                    attempt_path,
                    {
                        **_read_json(attempt_path),
                        "state": "complete",
                        "paired_evaluation_id": paired["paired_evaluation_id"],
                    },
                )
            if paired.get("automatic_promotion") is not False:
                raise ValueError(
                    "paired evaluation must never auto-promote a candidate"
                )
            comparison = paired.get("comparison")
            if not isinstance(comparison, Mapping):
                raise ValueError("paired evaluation comparison is missing")
            validation = validation.with_evaluation(comparison)
        return {
            "validation": validation.model_dump(mode="json"),
            "candidate_manifest": {
                "changed_paths": list(manifest.changed_paths),
                "added_paths": list(manifest.added_paths),
                "removed_paths": list(manifest.removed_paths),
            },
            "paired_evaluation": paired,
        }
    finally:
        for arm in (candidate_arm, baseline_arm):
            if arm is not None and arm.root.exists():
                cleanup_owned_directory(
                    arm.root,
                    owned_parent=arm.owned_parent,
                    ownership_token=arm.ownership_token,
                )


def revalidate_candidate_comparison(
    result: Mapping[str, Any],
    *,
    candidate_workspace: Any,
    frozen_candidate: Mapping[str, Any],
    evaluation_spec_path: str | None,
    workspace: str,
    staging_parent: str,
    invocation_id: str,
) -> dict[str, Any]:
    """Check source identities and saved evidence without repeating execution."""

    value = dict(result)
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
    )
    from botpipe_optimizer.execution_trees import verify_frozen_execution_tree
    from botpipe_optimizer.paired_evaluation import (
        load_evaluation_spec,
        validate_paired_evaluation_record,
    )

    bundle = _restore_frozen_bundle(frozen_candidate)
    verify_frozen_execution_tree(bundle.snapshot)
    candidate_surface = candidate_surface_manifest(candidate_workspace, bundle)
    manifest = candidate_manifest(candidate_workspace)
    validation = value.get("validation")
    saved_manifest = value.get("candidate_manifest")
    paired = value.get("paired_evaluation")
    if (
        not isinstance(validation, Mapping)
        or not isinstance(saved_manifest, Mapping)
        or not isinstance(paired, Mapping)
    ):
        raise TypeError("saved candidate evaluation is incomplete")
    expected_manifest = {
        "changed_paths": list(manifest.changed_paths),
        "added_paths": list(manifest.added_paths),
        "removed_paths": list(manifest.removed_paths),
    }
    if dict(saved_manifest) != expected_manifest:
        raise ValueError("saved candidate manifest is stale")
    baseline_surface_id = str(bundle.baseline_surface_manifest["surface_id"])
    candidate_surface_id = str(candidate_surface["surface_id"])
    if validation.get("baseline_surface_id") != baseline_surface_id:
        raise ValueError("saved validation baseline surface is stale")
    if validation.get("candidate_surface_id") != candidate_surface_id:
        raise ValueError("saved validation candidate surface is stale")
    if paired.get("evaluation") == "not_evaluated":
        expected = {
            "schema": "botpipe.optimizer.paired_evaluation/v1",
            "evaluation": "not_evaluated",
            "execution_state": "not_run",
            "comparison": {"state": "not_evaluated"},
            "automatic_promotion": False,
        }
        if dict(paired) != expected:
            raise ValueError("saved unevaluated comparison is invalid")
        return value
    arms = paired.get("arms")
    if not isinstance(arms, Mapping):
        raise TypeError("saved paired evaluation arms are missing")
    baseline_arm = arms.get("baseline")
    candidate_arm = arms.get("candidate")
    if not isinstance(baseline_arm, Mapping) or not isinstance(candidate_arm, Mapping):
        raise TypeError("saved paired evaluation must define both arms")
    baseline_tree_id = str(baseline_arm.get("execution_tree_id") or "")
    candidate_tree_id = str(candidate_arm.get("execution_tree_id") or "")
    if validation.get("baseline_execution_tree_id") != baseline_tree_id:
        raise ValueError("saved paired baseline execution tree is stale")
    if validation.get("candidate_execution_tree_id") != candidate_tree_id:
        raise ValueError("saved paired candidate execution tree is stale")
    spec_path = _resolve_file(workspace, evaluation_spec_path, "evaluation_spec_path")
    _, spec_id = load_evaluation_spec(spec_path)
    expected_attempt = _attempt_id(
        invocation_id,
        spec_id,
        baseline_surface_id,
        candidate_surface_id,
        baseline_tree_id,
        candidate_tree_id,
    )
    if paired.get("evaluation_attempt_id") != expected_attempt:
        raise ValueError("saved paired evaluation attempt identity is stale")
    checked = validate_paired_evaluation_record(
        paired,
        evaluation_spec_path=spec_path,
        baseline_surface_id=baseline_surface_id,
        candidate_surface_id=candidate_surface_id,
        baseline_execution_tree_id=baseline_tree_id,
        candidate_execution_tree_id=candidate_tree_id,
        allowed_output_parent=Path(staging_parent),
        expected_invocation_id=invocation_id,
    )
    value["paired_evaluation"] = checked
    return value


def validate_candidate_and_compare(
    *,
    candidate_workspace: Any,
    frozen_candidate: Mapping[str, Any],
    selected_workflow: str,
    staging_parent: str,
    target_test_argv: Sequence[str],
    validation_timeout: float,
    evaluation_spec_path: str | None = None,
    workspace: str,
    invocation_id: str,
) -> dict[str, Any]:
    """Run once through an activity, then revalidate saved results on every replay."""

    result = _validate_candidate_and_compare_activity(
        candidate_workspace=candidate_workspace,
        frozen_candidate=frozen_candidate,
        selected_workflow=selected_workflow,
        staging_parent=staging_parent,
        target_test_argv=target_test_argv,
        validation_timeout=validation_timeout,
        evaluation_spec_path=evaluation_spec_path,
        workspace=workspace,
        invocation_id=invocation_id,
    )
    return revalidate_candidate_comparison(
        result,
        candidate_workspace=candidate_workspace,
        frozen_candidate=frozen_candidate,
        evaluation_spec_path=evaluation_spec_path,
        workspace=workspace,
        staging_parent=staging_parent,
        invocation_id=invocation_id,
    )


__all__ = [
    "evaluation_suite_identity",
    "freeze_candidate_baseline",
    "freeze_improvement_evaluation",
    "load_optimizer_candidate_handoff",
    "revalidate_candidate_comparison",
    "staged_workflow_reference",
    "validate_candidate_and_compare",
    "validate_materialized_handoff",
]
