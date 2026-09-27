"""Frozen cases and real trials, using the runtime's existing recovery ledger."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import time
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from botpipe import (
    BudgetExceeded,
    UncertainOperation,
    activity,
    current_run,
    provider_budget,
)
from botpipe.discovery import resolve_workflow, validate_workflow_inputs
from botpipe.storage import sync_directory
from botpipe_optimizer.execution_trees import (
    assert_execution_arm_unchanged,
    materialize_execution_arm,
)
from botpipe_optimizer.trial_models import TrialCase, TrialResult, TrialSettings
from labs.workflows.optimizer_integration import _atomic_json, _restore_frozen_bundle

# A private subprocess adapter seam for behavioral tests; production uses Codex.
_TRIAL_PROVIDER_FACTORY: str | None = None


class TrialPlanError(ValueError):
    """A model-proposed case or rubric can be repaired before it is frozen."""


class TrialIntegrityError(ValueError):
    """A frozen input or path boundary was violated; never repair by guessing."""


def _json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode()


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or path == PurePosixPath(".")
    ):
        raise TrialIntegrityError(
            f"trial asset path must stay inside its root: {value!r}"
        )
    return path.as_posix()


def _ordinary(root: Path, relative: str) -> Path:
    relative = _relative(relative)
    raw = root / relative
    if any(path.is_symlink() for path in (raw, *raw.parents)):
        raise TrialIntegrityError(f"trial input contains a symlink: {relative}")
    if not raw.resolve().is_relative_to(root.resolve()):
        raise TrialIntegrityError(f"trial input escaped its root: {relative}")
    return raw


def _inventory(
    root: Path, settings: TrialSettings, *, excluded: tuple[Path, ...] = ()
) -> dict[str, dict]:
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise TrialIntegrityError("trial fixture must not contain a symlink")
    if not root.is_dir():
        raise FileNotFoundError(f"trial fixture directory is unavailable: {root}")
    files: dict[str, dict] = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        if any((parent / name).is_symlink() for name in dirs):
            raise TrialIntegrityError("trial fixture contains a symlink")
        dirs[:] = sorted(
            name
            for name in dirs
            if not any(
                (parent / name).resolve().is_relative_to(item) for item in excluded
            )
        )
        for name in sorted(names):
            path = parent / name
            if any(path.resolve().is_relative_to(item) for item in excluded):
                continue
            if path.is_symlink() or not path.is_file():
                raise TrialIntegrityError("trial fixture requires ordinary files")
            total += path.stat().st_size
            if (
                len(files) >= settings.max_fixture_files
                or total > settings.max_fixture_bytes
            ):
                raise TrialPlanError(
                    "trial fixture exceeds the declared file or byte limit"
                )
            files[path.relative_to(root).as_posix()] = {
                "sha256": sha256(path.read_bytes()).hexdigest(),
                "executable": bool(path.stat().st_mode & 0o111),
            }
    return files


def verify_trial_plan(plan: dict[str, Any]) -> None:
    record = {key: value for key, value in plan.items() if key != "plan_id"}
    if sha256(_json(record)).hexdigest() != plan["plan_id"]:
        raise TrialIntegrityError("frozen trial plan changed")
    root = Path(plan["root"])
    manifest = _ordinary(root, "plan.json")
    if not manifest.is_file() or json.loads(manifest.read_text()) != plan:
        raise TrialIntegrityError("frozen trial plan file changed")
    settings = TrialSettings.model_validate(plan["settings"])
    for case in plan["cases"]:
        if not case["available"]:
            continue
        path = _ordinary(root, f"inputs/{case['case']['case_id']}")
        if _inventory(path, settings) != case["files"]:
            raise TrialIntegrityError("frozen trial input bytes changed")


def freeze_trial_plan(
    *,
    params,
    assessment,
    analysis_root: Path,
    analysis_hashes: dict[str, str],
    source_manifest: dict,
) -> dict | None:
    """Bind cases first, then journal their bytes and criteria before implementation."""
    if not params.execute_trials:
        return None
    cases = params.trial_cases or assessment.trial_cases
    names = [criterion.name for criterion in assessment.rubric]
    if len(names) != len(set(names)):
        raise TrialPlanError("rubric criterion names must be unique")
    if len({case.case_id for case in cases}) != len(cases):
        raise TrialPlanError("trial case IDs must be unique")
    selected = resolve_workflow(params.selected_workflow, current_run().workspace)
    for case in cases:
        try:
            validate_workflow_inputs(selected, tuple(case.args), case.kwargs)
            _json(case.model_dump(mode="json"))
        except (TypeError, ValueError) as exc:
            raise TrialPlanError(
                f"invalid inputs for case {case.case_id}: {exc}"
            ) from exc
        for destination, source in case.assets.items():
            _relative(destination)
            _relative(source)
        for path in [*case.judge_input_paths, *case.output_paths]:
            _relative(path)
    plan = _freeze_trial_plan(
        cases=[case.model_dump(mode="json") for case in cases],
        rubric=[criterion.model_dump(mode="json") for criterion in assessment.rubric],
        intent=assessment.workflow_intent,
        comparison_rule=assessment.comparison_rule,
        fixture_path=params.trial_fixture_path,
        settings=params.trial_settings.model_dump(mode="json"),
        analysis_root=str(analysis_root),
        analysis_hashes=analysis_hashes,
        source_id=source_manifest["surface_id"],
    )
    verify_trial_plan(plan)
    return plan


@activity(retry_safe=True, name="freeze rubric and trial cases")
def _freeze_trial_plan(
    *,
    cases: list[dict],
    rubric: list[dict],
    intent: str,
    comparison_rule: str,
    fixture_path: str | None,
    settings: dict,
    analysis_root: str,
    analysis_hashes: dict,
    source_id: str,
) -> dict:
    run = current_run()
    root = run.folder / "rubric-trial-plan"
    if (root / "plan.json").exists():
        plan = json.loads((root / "plan.json").read_text())
        verify_trial_plan(plan)
        return plan
    with tempfile.TemporaryDirectory(
        prefix=".trial-inputs-", dir=run.folder
    ) as temporary:
        staging = Path(temporary) / "plan"
        plan = _capture_trial_inputs(
            root=staging,
            final_root=root,
            cases=cases,
            rubric=rubric,
            intent=intent,
            comparison_rule=comparison_rule,
            fixture_path=fixture_path,
            settings=settings,
            analysis_root=analysis_root,
            analysis_hashes=analysis_hashes,
            source_id=source_id,
        )
        os.replace(staging, root)
        sync_directory(root.parent)
    return plan


def _capture_trial_inputs(
    *,
    root: Path,
    final_root: Path,
    cases: list[dict],
    rubric: list[dict],
    intent: str,
    comparison_rule: str,
    fixture_path: str | None,
    settings: dict,
    analysis_root: str,
    analysis_hashes: dict,
    source_id: str,
) -> dict:
    run = current_run()
    limits = TrialSettings.model_validate(settings)
    root.mkdir(parents=True, exist_ok=True)
    frozen_cases = []
    fixture = None
    if fixture_path is not None:
        raw = Path(fixture_path).expanduser()
        fixture = raw if raw.is_absolute() else run.workspace / raw
    # Runtime state is not a starting workspace input and can contain this snapshot.
    excluded = (run.client.state_dir.resolve(), root.resolve())
    for raw_case in cases:
        case = TrialCase.model_validate(raw_case)
        destination = root / "inputs" / case.case_id
        destination.mkdir(parents=True, exist_ok=True)
        record = {"case": raw_case, "available": True, "reason": None, "files": {}}
        try:
            if case.workspace == "fixture":
                if fixture is None:
                    raise FileNotFoundError(
                        "case requires an explicit trial_fixture_path; history does not capture the initial workspace"
                    )
                before = _inventory(fixture, limits, excluded=excluded)
                for relative in before:
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(_ordinary(fixture, relative), target)
                if (
                    _inventory(fixture, limits, excluded=excluded) != before
                    or _inventory(destination, limits) != before
                ):
                    raise TrialIntegrityError(
                        "fixture changed while capturing its bytes"
                    )
            existing = _inventory(destination, limits)
            size = sum((destination / path).stat().st_size for path in existing)
            file_count = len(existing)
            for relative, evidence_path in case.assets.items():
                relative, evidence_path = _relative(relative), _relative(evidence_path)
                source = _ordinary(Path(analysis_root), evidence_path)
                if evidence_path not in analysis_hashes or not source.is_file():
                    raise FileNotFoundError(
                        f"captured input unavailable: {evidence_path}"
                    )
                size += source.stat().st_size
                file_count += 1
                if (
                    file_count > limits.max_fixture_files
                    or size > limits.max_fixture_bytes
                ):
                    raise TrialPlanError(
                        "captured assets exceed the declared fixture limit"
                    )
                data = source.read_bytes()
                if sha256(data).hexdigest() != analysis_hashes[evidence_path]:
                    raise TrialIntegrityError("captured trial input changed")
                target = _ordinary(destination, relative)
                if target.exists():
                    raise TrialPlanError(
                        f"asset would overwrite a fixture input: {relative}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for relative in case.judge_input_paths:
                if not _ordinary(destination, relative).is_file():
                    raise FileNotFoundError(
                        f"declared judge input is unavailable: {relative}"
                    )
            record["files"] = _inventory(destination, limits)
            for relative in record["files"]:
                path = destination / relative
                path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
        except FileNotFoundError as exc:
            record.update(available=False, reason=str(exc))
        frozen_cases.append(record)
    plan = {
        "schema": "botpipe.rubric-trial-plan/v1",
        "root": str(final_root),
        "source_id": source_id,
        "intent": intent,
        "rubric": rubric,
        "comparison_rule": comparison_rule,
        "aggregation_rule": "A gain on at least one evaluated case, no losses, and all required obligations met. Mixed or missing evidence is inconclusive.",
        "cases": frozen_cases,
        "settings": settings,
        "provider_name": run.client.provider_name,
        "provider_config": dict(run.client.provider_config),
        "policy": run.policy.to_dict(),
        "case_scope": "development cases fixed before candidate implementation; no claim about untested inputs",
    }
    plan["plan_id"] = sha256(_json(plan)).hexdigest()
    _atomic_json(root / "plan.json", plan)
    (root / "plan.json").chmod(0o444)
    return plan


@activity(retry_safe=True, name="prepare durable trial code copies")
def prepare_trial_arms(
    *, candidate_workspace, frozen_candidate: dict, staging_parent: str
) -> dict:
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
    )

    root = Path(staging_parent)
    bundle = _restore_frozen_bundle(frozen_candidate)
    changed = candidate_manifest(candidate_workspace)
    surface = candidate_surface_manifest(candidate_workspace, bundle)
    # The activity journal owns these paths. If capture is interrupted before it
    # commits, no trial has started and new copies are safe; after commit, replay
    # restores these exact paths without a second cache or replay authority.
    result = {}
    for name, manifest, removed in (
        ("baseline", bundle.baseline_surface_manifest, ()),
        ("candidate", surface, changed.removed_paths),
    ):
        arm = materialize_execution_arm(
            bundle.snapshot, root, candidate_manifest=manifest, removed_paths=removed
        )
        result[name] = json.loads(json.dumps(asdict(arm), default=str))
    return result


def verify_trial_arms(arms: dict) -> None:
    for value in arms.values():
        assert_execution_arm_unchanged(
            value["manifest"], Path(value["root"]), phase="rubric trials"
        )


@activity(retry_safe=True, name="start trial execution allowance")
def _trial_deadline(seconds: float) -> float:
    return time.time() + seconds


@activity(retry_safe=True, name="admit complete trial pair")
def _admit_pair(deadline: float, required_seconds: float) -> bool:
    return time.time() + required_seconds <= deadline


@activity(retry_safe=True, name="execute or resume workflow trial")
def _execute_trial(
    *,
    code_root: str,
    reference: str,
    case: dict,
    fixture_root: str,
    output_root: str,
    settings: dict,
    provider_config: dict,
    policy: dict,
    provider_factory: str | None,
    phase_deadline: float,
) -> TrialResult:
    from botpipe_optimizer.trials import run_trial

    destination = Path(output_root)
    # An initialization marker alone does not prove a workflow was dispatched.
    started = any((destination / "state").glob("tasks/*/runs/*/ledger.jsonl"))
    complete = (destination / "terminal-result.json").is_file()
    if (
        not (started or complete)
        and time.time() + settings["timeout_seconds"] > phase_deadline
    ):
        return TrialResult(
            case_id=case["case_id"],
            execution="infrastructure_error",
            outcome="phase_budget_exhausted",
            error="The overall trial allowance cannot start this arm with its full cap.",
        )
    result = run_trial(
        code_root=Path(code_root),
        workflow_reference=reference,
        case=TrialCase.model_validate(case),
        fixture_root=Path(fixture_root),
        output_root=Path(output_root),
        settings=TrialSettings.model_validate(settings),
        provider_config=provider_config,
        policy=policy,
        provider_factory=provider_factory,
    )
    if result.execution == "interrupted":
        raise UncertainOperation(
            "Trial interrupted; resume this improvement run to continue its existing inner ledger.",
            current_run().operation_id,
        )
    return result


def _bit(seed: str, purpose: str) -> bool:
    return bool(sha256(f"{seed}:{purpose}".encode()).digest()[0] & 1)


def _judge_case(plan: dict, case: dict, limit: int) -> dict:
    """Include declared input bytes, never ask a tool-free judge to open a path."""
    root = Path(plan["root"]) / "inputs" / case["case_id"]
    references, omissions = [], []
    remaining = limit
    for relative in sorted(
        {*case.get("assets", {}), *case.get("judge_input_paths", [])}
    ):
        path = _ordinary(root, relative)
        if not path.is_file() or path.stat().st_size > remaining:
            omissions.append(
                f"Required input {relative} is unavailable or exceeds the packet limit."
            )
            continue
        data = path.read_bytes()
        remaining -= len(data)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            omissions.append(
                f"Required input {relative} is binary and cannot be judged inline."
            )
            continue
        references.append({"path": relative, "content": content})
    return {
        "intent": plan["intent"],
        **case,
        "references": references,
        "omissions": omissions,
    }


def evaluate_trial_plan(
    *, plan: dict, arms: dict, reference: str, max_repairs: int
) -> dict:
    from botpipe_optimizer.judging import (
        aggregate_judgments,
        build_judge_packet,
        judge_pair,
    )

    verify_trial_plan(plan)
    verify_trial_arms(arms)
    run = current_run()
    if plan["provider_name"] != "codex" and _TRIAL_PROVIDER_FACTORY is None:
        return {
            "schema": "botpipe.rubric-evaluation/v1",
            "evaluation": "rubric_trials",
            "plan_id": plan["plan_id"],
            "comparison": {
                "state": "inconclusive",
                "reason": "Native trial processes require Codex; the configured provider cannot be reconstructed in a subprocess.",
            },
            "trials": [],
            "pairs": [],
            "scope": plan["case_scope"],
            "automatic_promotion": False,
        }
    settings = TrialSettings.model_validate(plan["settings"])
    deadline = _trial_deadline(settings.max_elapsed_seconds)
    trials, pairs = [], []
    for entry in plan["cases"]:
        case = entry["case"]
        for repetition in range(1, settings.repetitions + 1):
            pair = {
                "case_id": case["case_id"],
                "repetition": repetition,
                "rubric": plan["rubric"],
                "judgments": [],
            }
            pairs.append(pair)
            if not entry["available"]:
                pair["reason"] = entry["reason"]
                continue
            if not _admit_pair(deadline, 2 * settings.timeout_seconds):
                pair["reason"] = (
                    "Overall trial allowance cannot admit another complete pair with equal caps."
                )
                continue
            seed = f"{run.run_id}:{case['case_id']}:{repetition}"
            order = ["baseline", "candidate"]
            if _bit(seed, "execution-order"):
                order.reverse()
            results = {}
            for arm_name in order:
                verify_trial_plan(plan)
                verify_trial_arms(arms)
                results[arm_name] = _execute_trial(
                    code_root=arms[arm_name]["root"],
                    reference=reference,
                    case=case,
                    fixture_root=str(Path(plan["root"]) / "inputs" / case["case_id"]),
                    output_root=str(
                        run.folder
                        / "trials"
                        / case["case_id"]
                        / str(repetition)
                        / sha256(f"{seed}:trial:{arm_name}".encode()).hexdigest()[:16]
                    ),
                    settings=plan["settings"],
                    provider_config=plan["provider_config"],
                    policy=plan["policy"],
                    provider_factory=_TRIAL_PROVIDER_FACTORY,
                    phase_deadline=deadline,
                )
                verify_trial_arms(arms)
            trials.append(
                {
                    "case_id": case["case_id"],
                    "repetition": repetition,
                    "execution_order": order,
                    "results": {
                        name: result.model_dump(mode="json")
                        for name, result in results.items()
                    },
                }
            )
            if any(value.execution != "complete" for value in results.values()):
                pair["reason"] = (
                    "Trial infrastructure did not produce a complete behavioral pair."
                )
                continue
            candidate_label = "A" if _bit(seed, "judge-order") else "B"
            pair["candidate_label"] = candidate_label
            pair["case"] = _judge_case(plan, case, settings.max_packet_bytes)
            pair["results"] = results
    # This deadline starts after execution, so trials cannot starve later judgments.
    with provider_budget(
        max_turns=settings.max_judge_turns,
        max_seconds=settings.max_judge_seconds,
        turn_timeout_seconds=settings.judge_timeout_seconds,
    ) as budget:
        exhausted = False
        for pair in pairs:
            if "results" not in pair:
                pair["judgments"] = [
                    {
                        "candidate_label": "A",
                        "result": {"status": "inconclusive", "reason": pair["reason"]},
                    }
                ]
                continue
            results = pair.pop("results")
            for reverse in range(2 if settings.reverse_order_judgment else 1):
                candidate_label = pair["candidate_label"]
                if reverse:
                    candidate_label = "B" if candidate_label == "A" else "A"
                packet = build_judge_packet(
                    case=pair["case"],
                    rubric=plan["rubric"],
                    comparison_rule=plan["comparison_rule"],
                    a=results["candidate" if candidate_label == "A" else "baseline"],
                    b=results["baseline" if candidate_label == "A" else "candidate"],
                    max_bytes=settings.max_packet_bytes,
                )
                verify_trial_plan(plan)
                try:
                    judged = (
                        {
                            "status": "inconclusive",
                            "reason": "Judge allowance exhausted.",
                        }
                        if exhausted
                        else judge_pair(
                            packet=packet,
                            max_repairs=max_repairs,
                            timeout=settings.judge_timeout_seconds,
                        )
                    )
                except BudgetExceeded:
                    exhausted = True
                    judged = {
                        "status": "inconclusive",
                        "reason": "Judge allowance exhausted.",
                    }
                verify_trial_plan(plan)
                pair["judgments"].append(
                    {"candidate_label": candidate_label, "result": judged}
                )
        judge_budget = budget.snapshot()
    verdict = aggregate_judgments(pairs)
    verify_trial_plan(plan)
    verify_trial_arms(arms)
    return {
        "schema": "botpipe.rubric-evaluation/v1",
        "evaluation": "rubric_trials",
        "plan_id": plan["plan_id"],
        "comparison": verdict,
        "trials": trials,
        "pairs": pairs,
        "judge_budget": judge_budget,
        "scope": plan["case_scope"],
        "automatic_promotion": False,
    }
