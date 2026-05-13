from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "botpipe",
    REPO_ROOT / "botpipe_optimizer",
)
REMOVED_INTERNAL_TOKENS = (
    "Compiled" + "Workflow",
    "Compiled" + "Step",
    "Compiled" + "Route",
    "Compiled" + "Artifact",
    "Compiled" + "BranchGroupSpec",
    "Compiled" + "BranchStepSpec",
    "plan_" + "adapters",
    "workflow_plan_" + "from_compiled",
    "compiled_" + "workflow_from_plan",
    "step_plan_" + "from_compiled_step",
    "compiled_" + "step_from_step_plan",
    "route_contract_" + "from_compiled",
    "route_contract_" + "from_compiled_route",
    "compiled_" + "route_from_route_contract",
    "_COMPILED_" + "WORKFLOW_CACHE",
    "compile_" + "workflow_plan",
    "_compiled_" + "step",
    "_DirectRuntime" + "Control",
    "RouteFinalization" + "Result",
    "original_" + "step",
    "_required_" + "writes_explicit",
    "_Default" + "ProviderPolicyResolver",
)
FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES = frozenset({"_route_table", "_effective_route_table"})
REMOVED_ENGINE_PROVIDER_VALIDATION_HELPERS = frozenset(
    {
        "_validate_outcome",
        "_validate_outcome_route_fields",
        "_provider_available_routes_for_step",
    }
)
REMOVED_ENGINE_ROUTE_RUNTIME_HELPERS = frozenset(
    {
        "_validate_hook_event_override",
        "_build_hook_redirect_record",
        "_ensure_hook_redirect_limit",
        "_event_context_payload",
        "_build_pending_input",
        "_serialize_pending_input_schema",
        "_resolve_goto_target",
        "_normalize_direct_runtime_control",
        "_matching_pending_handoffs",
        "_schedule_route_handoffs",
        "_schedule_direct_control_handoffs",
        "_handoff_scope_for_target",
        "_route_table_for_step",
        "_compiled_route_for_step",
        "_validate_event",
        "_event_from_outcome",
    }
)
REMOVED_ENGINE_ARTIFACT_SESSION_HELPERS = frozenset(
    {
        "_select_session",
        "_persist_session",
        "_resolve_artifacts",
        "_resolve_session",
        "_append_logs",
        "_ensure_required_artifacts",
        "_ensure_named_artifacts_exist",
        "_artifact_reference_display_name",
        "_enforce_artifact_contracts",
        "_required_output_artifacts",
        "_should_validate_optional_output",
        "_validate_output_artifact",
        "_raise_artifact_validation_error",
        "_format_artifact_validation_error",
        "_resolve_workspace_read_path",
        "_artifact_lookup_name",
        "_resolve_pair_review_session",
        "_artifact_schema_name",
        "_artifact_display_name",
        "_runtime_artifact_spec",
        "_run_workflow_step",
        "_resolve_workflow_step_message",
        "_workflow_step_message_handle",
        "_write_workflow_step_outputs",
        "_workflow_step_output_payload",
        "_workflow_step_output_summary",
        "_map_workflow_step_result",
        "_ensure_child_workflow_route_declared",
    }
)
REMOVED_ENGINE_STATE_EVENT_HELPERS = frozenset(
    {
        "_normalize_state",
        "_event_with_route",
        "_clone_binding",
        "_clone_checkpoint",
        "_pending_question_for_terminal",
        "_snapshot_hook_context",
        "_restore_hook_context",
        "_clone_model_or_dict",
        "_restore_model_or_dict",
        "_restore_base_model",
        "_annotate_execution_error",
        "_annotate_retry_exhaustion",
        "_ensure_retry_failure_context",
        "_retry_policy_allows",
        "_provider_retry_kind",
        "_retry_kind_for_exception",
        "_next_retry_feedback",
        "_update_final_step_runtime_state",
        "_update_final_item_runtime_state",
        "_emit_runtime_event",
        "_emit_hook_event",
        "_provider_attempt_flags",
        "_build_step_finalization_record",
        "_step_result_from_direct_control",
        "_step_result_from_route_finalization",
        "_provider_exec_result",
        "_emit_provider_attempt_event",
        "_emit_provider_attempt_finished",
        "_emit_provider_attempt_failed",
        "_serialize_token_usage",
        "_exception_failure_context",
    }
)
ENGINE_BOUNDARY_FILES = (
    REPO_ROOT / "botpipe" / "core" / "engine_collaborators.py",
    REPO_ROOT / "botpipe" / "core" / "branch_groups" / "runtime.py",
    REPO_ROOT / "botpipe" / "core" / "execution_services.py",
    REPO_ROOT / "botpipe" / "core" / "execution_runtime_services.py",
)
ENGINE_FILE = REPO_ROOT / "botpipe" / "core" / "engine.py"
BRANCH_GROUP_RUNTIME_FILE = REPO_ROOT / "botpipe" / "core" / "branch_groups" / "runtime.py"
FORBIDDEN_BRANCH_GROUP_RUNTIME_CONTEXT_RESYNC_HELPERS = frozenset(
    {
        "_sync_values",
        "_sync_step_state",
        "_sync_meta",
    }
)
REMOVED_INTERNAL_PATHS = (
    REPO_ROOT / "botpipe" / "core" / ("plan_" + "adapters.py"),
    REPO_ROOT / "botpipe" / "extensions" / "git" / "runtime.py",
)


def test_removed_internal_compatibility_files_are_gone() -> None:
    for path in REMOVED_INTERNAL_PATHS:
        assert not path.exists(), path.relative_to(REPO_ROOT).as_posix()


def test_maintained_python_sources_do_not_reference_removed_internal_compatibility_symbols() -> None:
    violations: list[str] = []

    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for token in REMOVED_INTERNAL_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} contains {token!r}")

    assert violations == []


def test_maintained_python_sources_do_not_reintroduce_step_owned_route_table_symbols() -> None:
    violations: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            match node:
                case ast.Name(id=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.Attribute(attr=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.Constant(value=name) if isinstance(name, str) and name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.FunctionDef(name=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.AsyncFunctionDef(name=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))

    assert violations == []


def test_execution_collaborators_do_not_reintroduce_engine_reach_through() -> None:
    violations: list[str] = []

    for path in ENGINE_BOUNDARY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            match node:
                case ast.arg(arg="engine"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces engine constructor/service injection")
                case ast.Attribute(value=ast.Name(id="self"), attr="_engine"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces stored Engine state")
                case ast.Attribute(value=ast.Name(id="engine"), attr=attr) if attr.startswith("_"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces Engine private helper access engine.{attr}")
                case ast.Attribute(value=ast.Attribute(value=ast.Name(id="self"), attr="_engine"), attr=attr) if attr.startswith("_"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces Engine private helper access self._engine.{attr}")

    assert violations == []


def test_branch_group_runtime_does_not_reintroduce_redundant_context_resync_calls() -> None:
    violations: list[str] = []

    tree = ast.parse(BRANCH_GROUP_RUNTIME_FILE.read_text(encoding="utf-8"), filename=str(BRANCH_GROUP_RUNTIME_FILE))
    for node in ast.walk(tree):
        match node:
            case ast.Call(func=ast.Attribute(attr=name)) if name in FORBIDDEN_BRANCH_GROUP_RUNTIME_CONTEXT_RESYNC_HELPERS:
                violations.append(_symbol_violation(BRANCH_GROUP_RUNTIME_FILE, node, name))

    assert violations == []


def test_engine_does_not_reintroduce_removed_provider_validation_helpers() -> None:
    violations: list[str] = []

    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"), filename=str(ENGINE_FILE))
    for node in ast.walk(tree):
        match node:
            case ast.FunctionDef(name=name) if name in REMOVED_ENGINE_PROVIDER_VALIDATION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.AsyncFunctionDef(name=name) if name in REMOVED_ENGINE_PROVIDER_VALIDATION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.Attribute(value=ast.Name(id="self"), attr=name) if name in REMOVED_ENGINE_PROVIDER_VALIDATION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))

    assert violations == []


def test_engine_does_not_reintroduce_removed_route_runtime_helpers() -> None:
    violations: list[str] = []

    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"), filename=str(ENGINE_FILE))
    for node in ast.walk(tree):
        match node:
            case ast.FunctionDef(name=name) if name in REMOVED_ENGINE_ROUTE_RUNTIME_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.AsyncFunctionDef(name=name) if name in REMOVED_ENGINE_ROUTE_RUNTIME_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.Attribute(value=ast.Name(id="self"), attr=name) if name in REMOVED_ENGINE_ROUTE_RUNTIME_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))

    assert violations == []


def test_engine_does_not_reintroduce_removed_artifact_session_helpers() -> None:
    violations: list[str] = []

    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"), filename=str(ENGINE_FILE))
    for node in ast.walk(tree):
        match node:
            case ast.FunctionDef(name=name) if name in REMOVED_ENGINE_ARTIFACT_SESSION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.AsyncFunctionDef(name=name) if name in REMOVED_ENGINE_ARTIFACT_SESSION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.Attribute(value=ast.Name(id="self"), attr=name) if name in REMOVED_ENGINE_ARTIFACT_SESSION_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))

    assert violations == []


def test_engine_does_not_reintroduce_removed_state_event_helpers() -> None:
    violations: list[str] = []

    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"), filename=str(ENGINE_FILE))
    for node in ast.walk(tree):
        match node:
            case ast.FunctionDef(name=name) if name in REMOVED_ENGINE_STATE_EVENT_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.AsyncFunctionDef(name=name) if name in REMOVED_ENGINE_STATE_EVENT_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))
            case ast.Attribute(value=ast.Name(id="self"), attr=name) if name in REMOVED_ENGINE_STATE_EVENT_HELPERS:
                violations.append(_symbol_violation(ENGINE_FILE, node, name))

    assert violations == []


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _symbol_violation(path: Path, node: ast.AST, name: str) -> str:
    lineno = getattr(node, "lineno", "?")
    return f"{path.relative_to(REPO_ROOT)}:{lineno} reintroduces forbidden route-ownership symbol {name!r}"
