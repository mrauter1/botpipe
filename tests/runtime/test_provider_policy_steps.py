from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

import autoloop.simple as simple
from autoloop.core.compiler import compile_workflow
from autoloop.core.engine import Engine
from autoloop.core.primitives import FINISH, Event, Outcome
from autoloop.core.provider_policy import (
    PermissionPolicy,
    ProviderPolicy,
    ProviderPolicyError,
    ProviderPolicyOverride,
    SandboxPolicy,
    StrictProviderPolicy,
    StrictSandboxPolicy,
)
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from autoloop.runtime.config import (
    GitTrackingRuntimeConfig,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
    TracingRuntimeConfig,
)
from autoloop.runtime.provider_policy_resolver import ProviderPolicyResolver
from autoloop.runtime.runner import RunnerOptions, execute_workflow_package


def _runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        git_tracking=GitTrackingRuntimeConfig(enabled=False),
        tracing=TracingRuntimeConfig(enabled=False),
    )


def _provider_policy_runtime_config(
    *,
    default: ProviderPolicy | None = None,
    strict: StrictProviderPolicy | None = None,
) -> ProviderPolicyRuntimeConfig:
    if default is None and strict is None:
        return ProviderPolicyRuntimeConfig()
    payload: dict[str, object] = {}
    if default is not None:
        payload["default"] = default
    if strict is not None:
        payload["strict"] = strict
    return ProviderPolicyRuntimeConfig(**payload)


def _run_with_runner(
    tmp_path: Path,
    workflow_cls: type[object],
    provider: ScriptedLLMProvider,
    *,
    task_id: str,
    provider_policy: ProviderPolicyRuntimeConfig | None = None,
):
    return execute_workflow_package(
        workflow_cls,
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id=task_id,
            message="Run it.",
            runtime_config=_runtime_config(),
            provider_policy_config=provider_policy or ProviderPolicyRuntimeConfig(),
        ),
    )


def _provider_policy_resolver(
    tmp_path: Path,
    workflow_cls: type[object],
    *,
    strict: StrictProviderPolicy | None = None,
) -> ProviderPolicyResolver:
    compiled = compile_workflow(workflow_cls)
    return ProviderPolicyResolver(
        config=ResolvedRuntimeConfig(
            provider=ProviderConfig(),
            runtime=_runtime_config(),
            provider_policy=_provider_policy_runtime_config(strict=strict),
        ),
        workflow_policy=compiled.provider_policy,
        workspace_root=tmp_path,
    )


def _run_engine(
    tmp_path: Path,
    workflow_cls: type[object],
    provider: ScriptedLLMProvider,
    *,
    run_id: str,
    task_id: str,
    runtime_event_sink=None,
    strict: StrictProviderPolicy | None = None,
):
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir(parents=True, exist_ok=True)
    run_folder.mkdir(parents=True, exist_ok=True)
    compiled = compile_workflow(workflow_cls)
    return Engine(
        compiled,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=runtime_event_sink,
        provider_policy_resolver=_provider_policy_resolver(tmp_path, workflow_cls, strict=strict),
    ).run(
        task_id=task_id,
        run_id=run_id,
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )


def test_workflow_policy_is_inherited_and_step_policy_overrides(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))
    step_override = ProviderPolicyOverride(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
    )

    class PolicyWorkflow(simple.Workflow):
        policy = workflow_policy
        draft = simple.step("Draft.", routes={"done": "review"})
        review = simple.step("Review.", routes={"done": simple.FINISH}, policy=step_override)

    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done"), Outcome(raw_output='{"tag":"done"}', tag="done")]
    )
    execution = _run_with_runner(
        tmp_path,
        PolicyWorkflow,
        provider,
        task_id="policy-inheritance",
    )

    assert execution.result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["step", "step"]
    assert provider.calls[0].policy is not None
    assert provider.calls[1].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"
    assert provider.calls[1].policy.permissions.mode == "full_auto_sandboxed"


def test_reusable_policy_object_can_be_reused_by_two_steps(tmp_path: Path) -> None:
    reusable_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))

    class ReuseWorkflow(simple.Workflow):
        first = simple.step("First.", routes={"done": "second"}, policy=reusable_policy)
        second = simple.step("Second.", routes={"done": simple.FINISH}, policy=reusable_policy)

    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done"), Outcome(raw_output='{"tag":"done"}', tag="done")]
    )
    execution = _run_with_runner(
        tmp_path,
        ReuseWorkflow,
        provider,
        task_id="policy-reuse",
    )

    assert execution.result.terminal == FINISH
    assert provider.calls[0].policy == provider.calls[1].policy
    assert provider.calls[0].policy.permissions.mode == "ask"


def test_python_step_policy_affects_inline_operations_and_explicit_override_wins(tmp_path: Path) -> None:
    step_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))
    operation_override = ProviderPolicyOverride(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
    )

    class OperationWorkflow(simple.Workflow):
        class State(BaseModel):
            summary: str = ""
            verdict: str = ""

        @simple.python_step(policy=step_policy)
        def implement(ctx):
            summary = simple.llm("Summarize.", policy=operation_override)
            verdict = simple.classify("Choose.", choices=["ship", "hold"])
            ctx.state = ctx.state.model_copy(update={"summary": summary, "verdict": verdict})
            return None

    provider = ScriptedLLMProvider(operation_turns=["summary", "ship"])
    execution = _run_with_runner(
        tmp_path,
        OperationWorkflow,
        provider,
        task_id="policy-operations",
    )

    assert execution.result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["operation", "operation"]
    assert provider.calls[0].policy is not None
    assert provider.calls[1].policy is not None
    assert provider.calls[0].policy.permissions.mode == "full_auto_sandboxed"
    assert provider.calls[1].policy.permissions.mode == "ask"
    assert execution.result.state.summary == "summary"
    assert execution.result.state.verdict == "ship"


def test_flat_override_policy_is_accepted_for_inline_llm_calls(tmp_path: Path) -> None:
    class OperationWorkflow(simple.Workflow):
        class State(BaseModel):
            summary: str = ""

        @simple.python_step
        def inspect(ctx):
            summary = simple.llm(
                "Summarize risks.",
                policy=simple.PolicyOverride(
                    effort=simple.ModelEffort.LOW,
                    read_only=True,
                ),
            )
            ctx.state = ctx.state.model_copy(update={"summary": summary})
            return None

    provider = ScriptedLLMProvider(operation_turns=["summary"])
    execution = _run_with_runner(
        tmp_path,
        OperationWorkflow,
        provider,
        task_id="flat-inline-policy-override",
    )

    assert execution.result.terminal == FINISH
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.model.effort == "low"
    assert provider.calls[0].policy.sandbox.mode == "read_only"
    assert provider.calls[0].policy.sandbox.workspace.filesystem.allow_write == ()
    assert execution.result.state.summary == "summary"


def test_flat_dangerous_override_policy_is_accepted_for_inline_llm_calls(tmp_path: Path) -> None:
    class OperationWorkflow(simple.Workflow):
        class State(BaseModel):
            summary: str = ""

        @simple.python_step
        def inspect(ctx):
            summary = simple.llm(
                "Run unrestricted analysis.",
                policy=simple.PolicyOverride(
                    permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
                ),
            )
            ctx.state = ctx.state.model_copy(update={"summary": summary})
            return None

    provider = ScriptedLLMProvider(operation_turns=["summary"])
    execution = _run_with_runner(
        tmp_path,
        OperationWorkflow,
        provider,
        task_id="flat-inline-dangerous-policy-override",
    )

    assert execution.result.terminal == FINISH
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.permissions.mode == "full_auto_unsandboxed"
    assert provider.calls[0].policy.permissions.allow_dangerous_bypass is True
    assert provider.calls[0].policy.sandbox.mode == "danger_full_access"
    assert execution.result.state.summary == "summary"


def test_workflow_step_policy_applies_to_inline_operations_in_hooks(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
    )
    step_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))

    class ChildWorkflow(simple.Workflow):
        @simple.python_step
        def noop(_ctx):
            return None

    def before_launch(_ctx):
        simple.llm("Hook operation.")
        return Event("done")

    launch_step = simple.workflow_step(
        ChildWorkflow,
        message="Run child workflow.",
        routes={"done": simple.FINISH},
        policy=step_policy,
    )
    launch_step.before = before_launch

    class ParentWorkflow(simple.Workflow):
        policy = workflow_policy
        launch = launch_step

    provider = ScriptedLLMProvider(operation_turns=["hook result"])
    execution = _run_with_runner(
        tmp_path,
        ParentWorkflow,
        provider,
        task_id="workflow-step-hook-policy",
    )

    assert execution.result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["operation"]
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"


def test_workflow_step_hook_does_not_inherit_stale_policy_from_previous_step(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(
        permissions=PermissionPolicy(mode="full_auto_sandboxed"),
    )
    first_step_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))

    class ChildWorkflow(simple.Workflow):
        @simple.python_step
        def noop(_ctx):
            return None

    def before_launch(_ctx):
        simple.llm("Hook operation.")
        return Event("done")

    launch_step = simple.workflow_step(
        ChildWorkflow,
        message="Run child workflow.",
        routes={"done": simple.FINISH},
    )
    launch_step.before = before_launch

    class ParentWorkflow(simple.Workflow):
        policy = workflow_policy
        draft = simple.step("Draft.", routes={"done": "launch"}, policy=first_step_policy)
        launch = launch_step

    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done")],
        operation_turns=["hook result"],
    )
    execution = _run_with_runner(
        tmp_path,
        ParentWorkflow,
        provider,
        task_id="workflow-step-hook-cleanup",
    )

    assert execution.result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["step", "operation"]
    assert provider.calls[0].policy is not None
    assert provider.calls[1].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"
    assert provider.calls[1].policy.permissions.mode == "full_auto_sandboxed"


def test_strict_policy_rejects_unsafe_step_and_inline_overrides_with_same_violation(tmp_path: Path) -> None:
    strict = StrictProviderPolicy(
        sandbox=StrictSandboxPolicy(allowed_modes=("read_only", "workspace_write")),
    )
    unsafe_policy = ProviderPolicy(
        permissions=PermissionPolicy(
            mode="full_auto_unsandboxed",
            allow_dangerous_bypass=True,
        ),
        sandbox=SandboxPolicy(mode="danger_full_access"),
    )
    unsafe_override = ProviderPolicyOverride(
        permissions=PermissionPolicy(
            mode="full_auto_unsandboxed",
            allow_dangerous_bypass=True,
        ),
        sandbox=SandboxPolicy(mode="danger_full_access"),
    )

    class UnsafeStepWorkflow(simple.Workflow):
        implement = simple.step(
            "Implement.",
            routes={"done": simple.FINISH},
            policy=unsafe_policy,
            name="implement",
        )

    class UnsafeInlineWorkflow(simple.Workflow):
        @simple.python_step(name="implement")
        def implement(ctx):
            simple.llm("Implement.", policy=unsafe_override)
            return None

    step_provider = ScriptedLLMProvider()
    inline_provider = ScriptedLLMProvider()

    with pytest.raises(ProviderPolicyError) as step_exc:
        _run_with_runner(
            tmp_path / "step",
            UnsafeStepWorkflow,
            step_provider,
            task_id="unsafe-step",
            provider_policy=_provider_policy_runtime_config(strict=strict),
        )
    with pytest.raises(ProviderPolicyError) as inline_exc:
        _run_with_runner(
            tmp_path / "inline",
            UnsafeInlineWorkflow,
            inline_provider,
            task_id="unsafe-inline",
            provider_policy=_provider_policy_runtime_config(strict=strict),
        )

    assert str(step_exc.value) == str(inline_exc.value)
    assert "sandbox.mode='danger_full_access'" in str(step_exc.value)
    assert step_provider.calls == []
    assert inline_provider.calls == []


def test_policy_changes_participate_in_topology_hash() -> None:
    class AskWorkflow(simple.Workflow):
        policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))
        draft = simple.step("Draft.", routes={"done": simple.FINISH})

    class FullAutoWorkflow(simple.Workflow):
        policy = ProviderPolicy(permissions=PermissionPolicy(mode="full_auto_sandboxed"))
        draft = simple.step("Draft.", routes={"done": simple.FINISH})

    assert compile_workflow(AskWorkflow).topology_hash != compile_workflow(FullAutoWorkflow).topology_hash


def test_operation_replay_fingerprint_changes_when_policy_changes(tmp_path: Path) -> None:
    class AskWorkflow(simple.Workflow):
        name = "policy_replay"

        class State(BaseModel):
            summary: str = ""

        @simple.python_step(policy=ProviderPolicy(permissions=PermissionPolicy(mode="ask")))
        def implement(ctx):
            ctx.state = ctx.state.model_copy(update={"summary": simple.llm("Summarize.")})
            return None

    class FullAutoWorkflow(simple.Workflow):
        name = "policy_replay"

        class State(BaseModel):
            summary: str = ""

        @simple.python_step(policy=ProviderPolicy(permissions=PermissionPolicy(mode="full_auto_sandboxed")))
        def implement(ctx):
            ctx.state = ctx.state.model_copy(update={"summary": simple.llm("Summarize.")})
            return None

    _run_engine(
        tmp_path,
        AskWorkflow,
        ScriptedLLMProvider(operation_turns=["first result"]),
        run_id="run-policy-replay",
        task_id="task-policy-replay",
    )

    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = _run_engine(
        tmp_path,
        FullAutoWorkflow,
        ScriptedLLMProvider(),
        run_id="run-policy-replay",
        task_id="task-policy-replay",
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    )

    assert result.terminal == FINISH
    assert result.state.summary == "first result"
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"


def test_direct_engine_run_propagates_authored_workflow_policy_without_manual_resolver(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))

    class DirectEngineWorkflow(simple.Workflow):
        policy = workflow_policy
        draft = simple.step("Draft.", routes={"done": simple.FINISH})

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir(parents=True, exist_ok=True)
    run_folder.mkdir(parents=True, exist_ok=True)
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done")]
    )

    result = Engine(
        DirectEngineWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="direct-engine-policy",
        run_id="run-direct-engine-policy",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["step"]
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"
