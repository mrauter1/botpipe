from __future__ import annotations

import pytest

import botpipe
import botpipe.core as core
import botpipe.core.branch_groups as branch_groups
import botpipe.core.steps as core_steps
import botpipe.simple as simple


EXPECTED_ROOT_EXPORTS = (
    "Workflow",
    "step",
    "produce_verify_step",
    "python_step",
    "validation_step",
    "workflow_step",
    "Step",
    "PromptStep",
    "ProduceVerifyStep",
    "PythonStep",
    "ChildWorkflowStep",
    "parallel",
    "fan_out",
    "llm",
    "classify",
    "ControlRoutes",
    "Effects",
    "Prompt",
    "Md",
    "Json",
    "Text",
    "Raw",
    "Route",
    "Session",
    "Continuity",
    "FanIn",
    "Worklist",
    "WorklistEffect",
    "StateVar",
    "ValidationResult",
    "Event",
    "Outcome",
    "RequestInput",
    "Goto",
    "Fail",
    "FINISH",
    "AWAIT_INPUT",
    "FAIL",
    "SELF",
    "Policy",
    "ProviderName",
    "ModelEffort",
    "ModelVerbosity",
    "ReasoningSummary",
    "SandboxMode",
    "NetworkMode",
    "PermissionMode",
    "Botpipe",
    "WorkflowResult",
    "StepResult",
    "ArtifactMap",
    "ResultArtifact",
    "RunRecord",
    "RunsClient",
    "TaskRecord",
    "TasksClient",
    "RetentionPolicy",
    "RetentionInfo",
    "CleanupResult",
    "InputRequest",
    "HandledInput",
    "SDKDebugInfo",
    "BotpipeSDKError",
    "WorkflowInputError",
    "WorkflowParameterError",
    "InputRequired",
    "TooManyPauses",
    "InputResponseValidationError",
    "SDKExecutionError",
    "ConsoleInput",
    "StaticInput",
    "MappingInput",
    "BestSuppositionInput",
)

EXPECTED_CORE_EXPORTS = (
    "AWAIT_INPUT",
    "Artifact",
    "Continuity",
    "Context",
    "ControlRoutes",
    "FAIL",
    "Effects",
    "Fail",
    "FINISH",
    "GLOBAL",
    "Goto",
    "Prompt",
    "ProviderRetryPolicy",
    "RequestInput",
    "RuntimeInteractionPolicy",
    "Route",
    "Selector",
    "SELF",
    "Session",
    "ValidationResult",
    "Workflow",
    "WorkItem",
    "WorklistEffect",
    "Worklist",
)

EXPECTED_BRANCH_GROUP_EXPORTS = (
    "BranchGroupDeclarationSpec",
    "BranchMetadata",
    "BranchSessionStoreView",
    "BranchStepDeclarationSpec",
    "FanIn",
    "FanInHelperReference",
    "FanInMetadata",
    "StateCell",
    "branch_group_paths",
    "select_branch_group_outcome",
)

FORBIDDEN_PUBLIC_INTERNALS = (
    "WorkflowPlan",
    "StepPlan",
    "StepHeader",
    "StepSource",
    "ProviderTurnPlan",
    "RouteContract",
    "RouteDecision",
    "RouteAction",
    "ExecutionFrame",
    "ExecutionServices",
    "RunPaths",
    "RunIdentity",
    "ArtifactId",
    "ArtifactSpec",
    "PlaceholderRef",
    "ReferenceGraph",
    "BranchGroupPlan",
    "BranchPlan",
    "BranchResult",
    "BranchManifest",
    "WorkflowLocator",
    "SingleStepPlan",
)

REMOVED_PUBLIC_NAMES = (
    "PAUSE",
    "SU" + "CCESS",
    "Route" + "Info",
    "Policy" + "Override",
)


def _import_from(module_name: str, symbol: str) -> object:
    namespace: dict[str, object] = {}
    exec(f"from {module_name} import {symbol} as imported_symbol", namespace)
    return namespace["imported_symbol"]


def test_root_exports_are_exact_and_importable() -> None:
    assert tuple(botpipe.__all__) == EXPECTED_ROOT_EXPORTS

    for symbol in EXPECTED_ROOT_EXPORTS:
        assert _import_from("botpipe", symbol) is getattr(botpipe, symbol)

    assert botpipe.Botpipe is _import_from("botpipe", "Botpipe")
    assert botpipe.BotpipeSDKError is _import_from("botpipe", "BotpipeSDKError")
    assert botpipe.StateVar is simple.StateVar
    assert botpipe.Step is core_steps.Step
    assert botpipe.PromptStep is core_steps.PromptStep
    assert botpipe.ProduceVerifyStep is core_steps.ProduceVerifyStep
    assert botpipe.PythonStep is core_steps.PythonStep
    assert botpipe.ChildWorkflowStep is core_steps.ChildWorkflowStep


def test_core_exports_are_exact_and_importable() -> None:
    assert tuple(core.__all__) == EXPECTED_CORE_EXPORTS

    for symbol in EXPECTED_CORE_EXPORTS:
        assert _import_from("botpipe.core", symbol) is getattr(core, symbol)


def test_branch_group_exports_capture_phase_zero_surface() -> None:
    assert tuple(branch_groups.__all__) == EXPECTED_BRANCH_GROUP_EXPORTS

    for symbol in EXPECTED_BRANCH_GROUP_EXPORTS:
        assert _import_from("botpipe.core.branch_groups", symbol) is getattr(branch_groups, symbol)


def test_branch_group_exports_after_phase_two_remove_compiled_entries() -> None:
    assert "CompiledBranchGroupSpec" not in branch_groups.__all__
    assert "CompiledBranchStepSpec" not in branch_groups.__all__


def test_public_surfaces_do_not_export_internal_plan_runtime_types() -> None:
    for module_name, module in (
        ("botpipe", botpipe),
        ("botpipe.core", core),
        ("botpipe.core.branch_groups", branch_groups),
    ):
        for symbol in FORBIDDEN_PUBLIC_INTERNALS:
            assert not hasattr(module, symbol)
            with pytest.raises(ImportError):
                _import_from(module_name, symbol)


def test_deprecated_and_internal_names_are_not_publicly_exported() -> None:
    for symbol in REMOVED_PUBLIC_NAMES:
        assert symbol not in botpipe.__all__
    assert "RouteContract" not in botpipe.__all__
    assert "RouteContract" not in core.__all__
