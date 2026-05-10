from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import botlane.simple as simple
from botlane.core.compiler import compile_workflow
from botlane.core.context import Context
from botlane.core.engine import Engine
from botlane.core.provider_policy import PermissionPolicy, ProviderPolicy, ProviderPolicyOverride
from botlane.core.provider_policy_resolution import ProviderPolicyResolverProtocol
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from botlane.runtime.config import (
    GitTrackingRuntimeConfig,
    ProviderConfig,
    ProviderPolicyRuntimeConfig,
    ResolvedRuntimeConfig,
    RuntimeConfig,
)
from botlane.runtime.provider_policy_resolver import ProviderPolicyResolver


class _State(BaseModel):
    status: str = "new"


def _runtime_config() -> RuntimeConfig:
    return RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False))


def test_runtime_provider_policy_resolver_satisfies_core_protocol(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))
    step_policy = ProviderPolicyOverride(permissions=PermissionPolicy(mode="full_auto_sandboxed"))
    operation_policy = ProviderPolicyOverride(permissions=PermissionPolicy(mode="auto_edit"))

    class PolicyWorkflow(simple.Workflow):
        policy = workflow_policy
        draft = simple.step("Draft.", routes={"done": simple.FINISH}, policy=step_policy)

    compiled = compile_workflow(PolicyWorkflow)
    resolver = ProviderPolicyResolver(
        config=ResolvedRuntimeConfig(
            provider=ProviderConfig(),
            runtime=_runtime_config(),
            provider_policy=ProviderPolicyRuntimeConfig(),
        ),
        sdk_default_policy=None,
        workflow_policy=compiled.provider_policy,
        run_policy=None,
        workspace_root=tmp_path,
    )
    ctx = Context(
        root=tmp_path,
        task_id="task-1",
        run_id="run-1",
        workflow_name=compiled.workflow_name,
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_demo",
        run_folder=tmp_path / "task" / "wf_demo" / "runs" / "run-1",
        package_folder=tmp_path / "workflows" / "demo",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    ctx._provider_policy = workflow_policy

    assert isinstance(resolver, ProviderPolicyResolverProtocol)
    assert resolver.resolve_for_step(compiled.steps["draft"]).permissions.mode == "full_auto_sandboxed"
    assert resolver.resolve_for_operation(ctx, explicit_policy=operation_policy).permissions.mode == "auto_edit"


def test_engine_without_explicit_runtime_resolver_uses_core_fallback_policy_resolution(tmp_path: Path) -> None:
    workflow_policy = ProviderPolicy(permissions=PermissionPolicy(mode="ask"))

    class PolicyWorkflow(simple.Workflow):
        class State(BaseModel):
            summary: str = ""

        policy = workflow_policy

        @simple.python_step
        def draft(ctx):
            summary = simple.llm("Summarize.")
            ctx.state = ctx.state.model_copy(update={"summary": summary})
            return None

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    provider = ScriptedLLMProvider(operation_turns=["summary"])
    result = Engine(
        compile_workflow(PolicyWorkflow),
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == "FINISH"
    assert result.state.summary == "summary"
    assert len(provider.calls) == 1
    assert provider.calls[0].kind == "operation"
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"


def test_engine_syncs_default_policy_resolver_into_operation_recorder_for_run_lifecycle(tmp_path: Path) -> None:
    class PolicyWorkflow(simple.Workflow):
        @simple.python_step
        def draft(_ctx):
            return None

    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()

    engine = Engine(
        compile_workflow(PolicyWorkflow),
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )
    observed_resolvers: list[object | None] = []
    original_setter = engine.operation_recorder.set_provider_policy_resolver

    def _spy_set_provider_policy_resolver(resolver: object | None) -> None:
        observed_resolvers.append(resolver)
        original_setter(resolver)

    engine.operation_recorder.set_provider_policy_resolver = _spy_set_provider_policy_resolver

    result = engine.run(
        task_id="task-default-resolver-lifecycle",
        run_id="run-default-resolver-lifecycle",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == "FINISH"
    assert len(observed_resolvers) == 2
    assert observed_resolvers[0] is not None
    assert isinstance(observed_resolvers[0], ProviderPolicyResolverProtocol)
    assert observed_resolvers[1] is None
    assert engine.provider_policy_resolver is None
