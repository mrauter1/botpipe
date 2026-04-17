"""Workspace and path policy for the filesystem runtime."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


STATE_DIRNAME = ".autoloop"
LEGACY_STATE_DIRNAME = ".superloop"
PHASE_MODE_SINGLE = "single"
PHASE_MODE_UP_TO = "up-to"
PHASE_PLAN_VERSION = 1
PHASE_STATUS_PLANNED = "planned"
IMPLICIT_PHASE_ID = "implicit-phase"
MAX_PHASE_ID_UTF8_BYTES = 96
PHASE_DIR_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DEFAULT_REQUEST_TEXT = "No explicit initial request was provided for this run. Use repository artifacts and explicit clarifications only."
PAIR_ORDER = ("plan", "implement", "test")
PLAN_DECISIONS_PHASE_ID = "task-global"


class PhasePlanError(ValueError):
    """Raised when persisted phase-plan state is invalid."""


@dataclass(frozen=True, slots=True)
class PhasePlanCriterion:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class PhasePlanPhase:
    phase_id: str
    title: str
    objective: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    dependencies: tuple[str, ...]
    acceptance_criteria: tuple[PhasePlanCriterion, ...]
    deliverables: tuple[str, ...]
    risks: tuple[str, ...]
    rollback: tuple[str, ...]
    status: str = PHASE_STATUS_PLANNED


@dataclass(frozen=True, slots=True)
class PhasePlan:
    version: int
    task_id: str
    request_snapshot_ref: str
    phases: tuple[PhasePlanPhase, ...]
    explicit: bool = True

    def phase_by_id(self, phase_id: str) -> PhasePlanPhase | None:
        for phase in self.phases:
            if phase.phase_id == phase_id:
                return phase
        return None


@dataclass(frozen=True, slots=True)
class ResolvedPhaseSelection:
    phase_mode: str
    phase_ids: tuple[str, ...]
    phases: tuple[PhasePlanPhase, ...]
    explicit: bool

    @property
    def is_implicit(self) -> bool:
        return not self.explicit


@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    root: Path
    state_root: Path
    tasks_dir: Path
    task_dir: Path
    task_id: str
    task_root_rel: Path
    task_meta_file: Path
    task_request_file: Path
    raw_phase_log: Path
    decisions_file: Path
    legacy_context_file: Path
    runs_dir: Path
    plan_dir: Path
    implement_dir: Path
    test_dir: Path
    phases_dir: Path


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    run_id: str
    run_dir: Path
    raw_phase_log: Path
    events_file: Path
    request_file: Path
    sessions_dir: Path
    phase_sessions_dir: Path
    plan_session_file: Path
    checkpoint_file: Path
    phase_selection_file: Path


def validate_phase_id(phase_id: str) -> str:
    normalized = phase_id.strip()
    if not normalized:
        raise PhasePlanError("phase_id must be a non-empty string.")
    if len(normalized.encode("utf-8")) > MAX_PHASE_ID_UTF8_BYTES:
        raise PhasePlanError(f"phase_id {normalized!r} exceeds {MAX_PHASE_ID_UTF8_BYTES} UTF-8 bytes.")
    return normalized


def phase_dir_key(phase_id: str) -> str:
    normalized = validate_phase_id(phase_id)
    if PHASE_DIR_SAFE_RE.fullmatch(normalized):
        return normalized
    return f"_pid-{normalized.encode('utf-8').hex()}"


def primary_state_root(root: Path) -> Path:
    return root / STATE_DIRNAME


def legacy_state_root(root: Path) -> Path:
    return root / LEGACY_STATE_DIRNAME


def resolve_resume_state_root(root: Path, *, task_id: str | None = None, run_id: str | None = None) -> Path:
    primary_tasks = primary_state_root(root) / "tasks"
    legacy_tasks = legacy_state_root(root) / "tasks"
    if run_id is not None:
        primary_run_task = task_id_for_run(primary_tasks, run_id)
        if primary_run_task is not None and (task_id is None or primary_run_task == task_id):
            return primary_state_root(root)
        legacy_run_task = task_id_for_run(legacy_tasks, run_id)
        if legacy_run_task is not None and (task_id is None or legacy_run_task == task_id):
            return legacy_state_root(root)
    if task_id is not None and (primary_tasks / task_id).is_dir():
        return primary_state_root(root)
    if task_id is not None and (legacy_tasks / task_id).is_dir():
        return legacy_state_root(root)
    if latest_task_id(primary_tasks) is not None:
        return primary_state_root(root)
    if latest_task_id(legacy_tasks) is not None:
        return legacy_state_root(root)
    return primary_state_root(root)


def latest_task_id(tasks_dir: Path) -> str | None:
    if not tasks_dir.exists():
        return None
    task_dirs = [path for path in tasks_dir.iterdir() if path.is_dir()]
    if not task_dirs:
        return None
    return max(task_dirs, key=lambda path: path.stat().st_mtime).name


def task_id_for_run(tasks_dir: Path, run_id: str) -> str | None:
    if not tasks_dir.exists():
        return None
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir():
            continue
        if (task_dir / "runs" / run_id).is_dir():
            return task_dir.name
    return None


def create_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"


def repo_relative_path(root: Path, path: Path) -> Path:
    return Path(os.path.relpath(path, root))


def write_request_snapshot(request_file: Path, request_text: str | None) -> None:
    if request_file.exists():
        return
    body = _normalize_request_text(request_text) or DEFAULT_REQUEST_TEXT
    request_file.parent.mkdir(parents=True, exist_ok=True)
    request_file.write_text(body.rstrip() + "\n", encoding="utf-8")


def task_request_text(task_meta_file: Path, legacy_context_file: Path | None = None) -> str | None:
    payload = _load_task_meta(task_meta_file, task_meta_file.parent.name)
    request_text = _normalize_request_text(
        payload.get("request_text") if isinstance(payload.get("request_text"), str) else None
    )
    if request_text:
        return request_text
    if legacy_context_file is not None:
        return _extract_request_from_legacy_context(legacy_context_file)
    return None


def ensure_workspace(
    root: Path,
    task_id: str,
    product_intent: str | None = None,
    intent_mode: str = "replace",
    *,
    state_dir: Path | None = None,
) -> TaskWorkspace:
    resolved_root = root.resolve()
    resolved_state_root = (state_dir or primary_state_root(resolved_root)).resolve()
    tasks_dir = resolved_state_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_dir = tasks_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    task_root_rel = repo_relative_path(resolved_root, task_dir)

    raw_phase_log = task_dir / "raw_phase_log.md"
    if not raw_phase_log.exists():
        raw_phase_log.write_text("# Autoloop Raw Phase Log\n", encoding="utf-8")

    decisions_file = task_dir / "decisions.txt"
    decisions_file.touch(exist_ok=True)

    runs_dir = task_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    plan_dir = task_dir / "plan"
    implement_dir = task_dir / "implement"
    test_dir = task_dir / "test"
    phases_dir = task_dir / "phases"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (implement_dir / "phases").mkdir(parents=True, exist_ok=True)
    (test_dir / "phases").mkdir(parents=True, exist_ok=True)
    phases_dir.mkdir(parents=True, exist_ok=True)

    task_meta_file = task_dir / "task.json"
    legacy_context_file = task_dir / "context.md"
    task_request_file = task_dir / "request.md"

    task_meta = _load_task_meta(task_meta_file, task_id)
    existing_request = _normalize_request_text(
        task_meta.get("request_text") if isinstance(task_meta.get("request_text"), str) else None
    )
    if existing_request is None:
        existing_request = _extract_request_from_legacy_context(legacy_context_file)

    normalized_intent = _normalize_request_text(product_intent)
    if normalized_intent is not None:
        if intent_mode == "replace" or existing_request is None:
            existing_request = normalized_intent
        elif intent_mode == "append":
            stamp = datetime.now(timezone.utc).isoformat()
            existing_request = f"{existing_request}\n\n## Run Intent ({stamp})\n{normalized_intent}"
        elif intent_mode == "preserve" and existing_request is None:
            existing_request = normalized_intent

    task_meta["request_text"] = existing_request
    task_meta.setdefault("phase_plan_path", str(task_root_rel / "plan" / "phase_plan.yaml"))
    task_meta["request_updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_task_meta(task_meta_file, task_meta)

    task_body = _normalize_request_text(existing_request) or DEFAULT_REQUEST_TEXT
    task_request_file.write_text(task_body.rstrip() + "\n", encoding="utf-8")

    return TaskWorkspace(
        root=resolved_root,
        state_root=resolved_state_root,
        tasks_dir=tasks_dir,
        task_dir=task_dir,
        task_id=task_id,
        task_root_rel=task_root_rel,
        task_meta_file=task_meta_file,
        task_request_file=task_request_file,
        raw_phase_log=raw_phase_log,
        decisions_file=decisions_file,
        legacy_context_file=legacy_context_file,
        runs_dir=runs_dir,
        plan_dir=plan_dir,
        implement_dir=implement_dir,
        test_dir=test_dir,
        phases_dir=phases_dir,
    )


def create_run(
    workspace: TaskWorkspace,
    *,
    run_id: str | None = None,
    request_text: str | None = None,
) -> RunWorkspace:
    resolved_run_id = run_id or create_run_id()
    run_dir = workspace.runs_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_phase_log = run_dir / "raw_phase_log.md"
    raw_phase_log.write_text(f"# Autoloop Raw Phase Log ({resolved_run_id})\n", encoding="utf-8")

    events_file = run_dir / "events.jsonl"
    events_file.write_text("", encoding="utf-8")

    request_file = run_dir / "request.md"
    write_request_snapshot(request_file, request_text)

    sessions_dir = run_dir / "sessions"
    phase_sessions_dir = sessions_dir / "phases"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    phase_sessions_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_file = run_dir / "checkpoint.json"
    phase_selection_file = run_dir / "phase_selection.json"

    return RunWorkspace(
        run_id=resolved_run_id,
        run_dir=run_dir,
        raw_phase_log=raw_phase_log,
        events_file=events_file,
        request_file=request_file,
        sessions_dir=sessions_dir,
        phase_sessions_dir=phase_sessions_dir,
        plan_session_file=plan_session_path(run_dir),
        checkpoint_file=checkpoint_file,
        phase_selection_file=phase_selection_file,
    )


def open_existing_run(workspace: TaskWorkspace, run_id: str) -> RunWorkspace:
    run_dir = workspace.runs_dir / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run {run_id!r} does not exist under {workspace.runs_dir}")

    raw_phase_log = run_dir / "raw_phase_log.md"
    if not raw_phase_log.exists():
        raw_phase_log.write_text(f"# Autoloop Raw Phase Log ({run_id})\n", encoding="utf-8")
    events_file = run_dir / "events.jsonl"
    events_file.touch(exist_ok=True)
    request_file = run_dir / "request.md"
    if not request_file.exists():
        write_request_snapshot(request_file, task_request_text(workspace.task_meta_file, workspace.legacy_context_file))

    sessions_dir = run_dir / "sessions"
    phase_sessions_dir = sessions_dir / "phases"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    phase_sessions_dir.mkdir(parents=True, exist_ok=True)

    return RunWorkspace(
        run_id=run_id,
        run_dir=run_dir,
        raw_phase_log=raw_phase_log,
        events_file=events_file,
        request_file=request_file,
        sessions_dir=sessions_dir,
        phase_sessions_dir=phase_sessions_dir,
        plan_session_file=plan_session_path(run_dir),
        checkpoint_file=run_dir / "checkpoint.json",
        phase_selection_file=run_dir / "phase_selection.json",
    )


def plan_session_path(run_dir: Path) -> Path:
    return run_dir / "sessions" / "plan.json"


def phase_session_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "sessions" / "phases" / f"{phase_dir_key(phase_id)}.json"


def ensure_phase_plan_scaffold(workspace: TaskWorkspace, request_file: Path) -> Path:
    if yaml is None:
        raise PhasePlanError("phase_plan.yaml cannot be scaffolded without PyYAML installed.")
    plan_path = workspace.plan_dir / "phase_plan.yaml"
    phases: object = []
    if plan_path.exists():
        try:
            existing_payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - compatibility fallback
            existing_payload = None
        if isinstance(existing_payload, dict) and "phases" in existing_payload:
            phases = existing_payload.get("phases")

    scaffold = {
        "version": PHASE_PLAN_VERSION,
        "task_id": workspace.task_id,
        "request_snapshot_ref": str(request_file),
        "phases": [] if phases is None else phases,
    }
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(yaml.safe_dump(scaffold, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return plan_path


def build_implicit_phase_plan(task_id: str, request_file: Path) -> PhasePlan:
    request_text = request_file.read_text(encoding="utf-8").strip() if request_file.exists() else ""
    summary = request_text if request_text else DEFAULT_REQUEST_TEXT
    phase = PhasePlanPhase(
        phase_id=IMPLICIT_PHASE_ID,
        title="Implicit single phase",
        objective="Complete the requested work described in the immutable request snapshot.",
        in_scope=(summary,),
        out_of_scope=(),
        dependencies=(),
        acceptance_criteria=(PhasePlanCriterion(id="AC-1", text="Implement the requested work coherently."),),
        deliverables=("code", "tests", "docs"),
        risks=(),
        rollback=(),
    )
    return PhasePlan(
        version=PHASE_PLAN_VERSION,
        task_id=task_id,
        request_snapshot_ref=str(request_file),
        phases=(phase,),
        explicit=False,
    )


def load_phase_plan(path: Path, task_id: str) -> PhasePlan | None:
    if not path.exists():
        return None
    if yaml is None:
        raise PhasePlanError("phase_plan.yaml cannot be loaded without PyYAML installed.")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - library-specific parse failures
        raise PhasePlanError(f"{path} could not be parsed as YAML: {exc}") from exc
    return validate_phase_plan(payload, task_id)


def validate_phase_plan(payload: object, task_id: str) -> PhasePlan:
    if not isinstance(payload, dict):
        raise PhasePlanError("phase_plan.yaml must deserialize to a mapping.")
    phases_payload = payload.get("phases")
    if not isinstance(phases_payload, list) or not phases_payload:
        raise PhasePlanError("phase_plan.yaml must declare a non-empty phases list.")

    phases: list[PhasePlanPhase] = []
    seen_phase_ids: set[str] = set()
    for index, raw_phase in enumerate(phases_payload, start=1):
        if not isinstance(raw_phase, dict):
            raise PhasePlanError(f"phase #{index} must be a mapping.")
        phase_id = validate_phase_id(str(raw_phase.get("phase_id") or ""))
        if phase_id in seen_phase_ids:
            raise PhasePlanError(f"duplicate phase_id {phase_id!r} in phase_plan.yaml.")
        seen_phase_ids.add(phase_id)
        criteria_payload = raw_phase.get("acceptance_criteria") or []
        criteria: list[PhasePlanCriterion] = []
        for criterion_index, raw_criterion in enumerate(criteria_payload, start=1):
            if not isinstance(raw_criterion, dict):
                raise PhasePlanError(f"phase {phase_id!r} criterion #{criterion_index} must be a mapping.")
            criteria.append(
                PhasePlanCriterion(
                    id=str(raw_criterion.get("id") or f"AC-{criterion_index}"),
                    text=str(raw_criterion.get("text") or ""),
                )
            )
        phases.append(
            PhasePlanPhase(
                phase_id=phase_id,
                title=str(raw_phase.get("title") or phase_id),
                objective=str(raw_phase.get("objective") or ""),
                in_scope=_tuple_of_strings(raw_phase.get("in_scope")),
                out_of_scope=_tuple_of_strings(raw_phase.get("out_of_scope")),
                dependencies=_tuple_of_strings(raw_phase.get("dependencies")),
                acceptance_criteria=tuple(criteria),
                deliverables=_tuple_of_strings(raw_phase.get("deliverables")),
                risks=_tuple_of_strings(raw_phase.get("risks")),
                rollback=_tuple_of_strings(raw_phase.get("rollback")),
                status=str(raw_phase.get("status") or PHASE_STATUS_PLANNED),
            )
        )

    declared_task_id = str(payload.get("task_id") or task_id)
    if declared_task_id != task_id:
        raise PhasePlanError(f"phase_plan.yaml task_id {declared_task_id!r} does not match current task_id {task_id!r}.")
    return PhasePlan(
        version=int(payload.get("version") or PHASE_PLAN_VERSION),
        task_id=declared_task_id,
        request_snapshot_ref=str(payload.get("request_snapshot_ref") or ""),
        phases=tuple(phases),
        explicit=True,
    )


def resolve_phase_selection(plan: PhasePlan, phase_id: str | None, phase_mode: str) -> ResolvedPhaseSelection:
    normalized_phase_id = phase_id.strip() if isinstance(phase_id, str) and phase_id.strip() else None
    if not plan.explicit:
        if normalized_phase_id is not None:
            raise PhasePlanError("--phase-id requires an explicit phase_plan.yaml.")
        return ResolvedPhaseSelection(
            phase_mode=PHASE_MODE_SINGLE,
            phase_ids=(IMPLICIT_PHASE_ID,),
            phases=plan.phases,
            explicit=False,
        )

    if normalized_phase_id is None:
        return ResolvedPhaseSelection(
            phase_mode=phase_mode,
            phase_ids=tuple(phase.phase_id for phase in plan.phases),
            phases=plan.phases,
            explicit=True,
        )

    selected_phase = plan.phase_by_id(normalized_phase_id)
    if selected_phase is None:
        raise PhasePlanError(f"unknown --phase-id {normalized_phase_id!r} for current phase_plan.yaml.")
    ordered_phases = list(plan.phases)
    phase_index = ordered_phases.index(selected_phase)
    selected_phases = ordered_phases[: phase_index + 1] if phase_mode == PHASE_MODE_UP_TO else [selected_phase]
    return ResolvedPhaseSelection(
        phase_mode=phase_mode,
        phase_ids=tuple(phase.phase_id for phase in selected_phases),
        phases=tuple(selected_phases),
        explicit=True,
    )


def restore_phase_selection(plan: PhasePlan, phase_ids: Sequence[str], phase_mode: str | None = None) -> ResolvedPhaseSelection:
    if not phase_ids:
        raise PhasePlanError("stored phase selection is empty.")
    expected_order = [phase.phase_id for phase in plan.phases if phase.phase_id in set(phase_ids)]
    if expected_order != list(phase_ids):
        raise PhasePlanError("stored phase selection no longer matches phase plan order.")
    phases = []
    for phase_id in phase_ids:
        phase = plan.phase_by_id(phase_id)
        if phase is None:
            raise PhasePlanError(f"stored phase selection references unknown phase_id {phase_id!r}.")
        phases.append(phase)
    return ResolvedPhaseSelection(
        phase_mode=phase_mode or (PHASE_MODE_SINGLE if len(phases) == 1 else PHASE_MODE_UP_TO),
        phase_ids=tuple(phase_ids),
        phases=tuple(phases),
        explicit=plan.explicit,
    )


def save_phase_selection(path: Path, selection: ResolvedPhaseSelection) -> None:
    payload = {
        "phase_mode": selection.phase_mode,
        "phase_ids": list(selection.phase_ids),
        "explicit": selection.explicit,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_phase_selection(path: Path, plan: PhasePlan) -> ResolvedPhaseSelection | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise PhasePlanError(f"{path} could not be parsed as JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PhasePlanError(f"{path} must contain a JSON object.")
    phase_ids = payload.get("phase_ids")
    if not isinstance(phase_ids, list) or not all(isinstance(item, str) for item in phase_ids):
        raise PhasePlanError(f"{path} contains an invalid phase_ids list.")
    phase_mode = payload.get("phase_mode")
    if phase_mode is not None and not isinstance(phase_mode, str):
        raise PhasePlanError(f"{path} contains an invalid phase_mode value.")
    return restore_phase_selection(plan, phase_ids, phase_mode=phase_mode)


def _normalize_request_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def _extract_request_from_legacy_context(context_file: Path) -> str | None:
    if not context_file.exists():
        return None
    text = context_file.read_text(encoding="utf-8").strip()
    if not text:
        return None
    text = re.split(r"\n### Clarification\b", text, maxsplit=1)[0].strip()
    if text.startswith("# Product Context"):
        text = text[len("# Product Context") :].strip()
    return text or None


def _load_task_meta(task_meta_file: Path, task_id: str) -> dict[str, Any]:
    if task_meta_file.exists():
        try:
            payload = json.loads(task_meta_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, OSError):
            pass
    return {"task_id": task_id, "created_at": datetime.now(timezone.utc).isoformat()}


def _write_task_meta(task_meta_file: Path, payload: dict[str, Any]) -> None:
    task_meta_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tuple_of_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)
