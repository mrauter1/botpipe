from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import botlane.simple as simple
from botlane import FINISH, Botlane
from botlane.core.provider_policy import PermissionPolicy, ProviderPolicy
from botlane.core.primitives import Event, Outcome
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.steps import PromptStep
from botlane.policy import ModelEffort, PermissionMode, Policy
from botlane.runtime.config import GitTrackingRuntimeConfig, ProviderPolicyRuntimeConfig, RuntimeConfig


def _sdk_client(
    tmp_path: Path,
    provider: ScriptedLLMProvider,
    *,
    default_policy: Policy | None = None,
    provider_policy_config: ProviderPolicyRuntimeConfig | None = None,
    state_dir: Path | None = None,
) -> Botlane:
    return Botlane(
        workspace=tmp_path,
        provider=provider,
        default_policy=default_policy,
        provider_policy_config=provider_policy_config,
        state_dir=tmp_path / ".autoloop" if state_dir is None else state_dir,
        runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False, commit_policy="off")),
    )


class _PolicyRuntimeWorkflow(simple.Workflow):
    class State(BaseModel):
        summary: str = ""

    inspect = simple.step("Inspect the repository.", routes={"done": FINISH})


def test_sdk_run_policy_overrides_sdk_default_policy_for_workflow_steps(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output='{"tag":"done"}', tag="done")])
    client = _sdk_client(
        tmp_path,
        provider,
        default_policy=Policy(
            effort=ModelEffort.LOW,
            network_domains=("docs.python.org",),
        ),
    )

    client.run(
        _PolicyRuntimeWorkflow,
        "Run it.",
        policy=Policy(effort=ModelEffort.HIGH),
    )

    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.model.effort == "high"
    assert provider.calls[0].policy.sandbox.workspace.network.mode == "limited"
    assert provider.calls[0].policy.sandbox.workspace.network.allow_domains == ("docs.python.org",)


def test_sdk_direct_operations_inherit_sdk_default_policy_and_apply_explicit_overrides(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(operation_turns=["summary", "ship"])
    client = _sdk_client(
        tmp_path,
        provider,
        default_policy=Policy(
            permission_mode=PermissionMode.ASK,
            effort=ModelEffort.LOW,
        ),
    )

    client.llm("Summarize.", policy=Policy(effort=ModelEffort.HIGH))
    client.classify("Choose.", choices=["ship", "hold"])

    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.model.effort == "high"
    assert provider.calls[0].policy.permissions.mode == "ask"
    assert provider.calls[1].policy is not None
    assert provider.calls[1].policy.model.effort == "low"
    assert provider.calls[1].policy.permissions.mode == "ask"


def test_sdk_step_invocation_policy_is_local_and_does_not_mutate_reused_step(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output='{"tag":"done"}', tag="done"),
            Outcome(raw_output='{"tag":"done"}', tag="done"),
        ]
    )
    client = _sdk_client(tmp_path, provider)
    step_def = PromptStep(
        name="inspect",
        producer=simple.Prompt.inline("Inspect."),
        provider_policy=Policy(effort=ModelEffort.LOW),
    )

    client.step(
        step_def,
        "First run.",
        policy=Policy(effort=ModelEffort.HIGH),
    )
    client.step(
        step_def,
        "Second run.",
    )

    assert isinstance(step_def.provider_policy, Policy)
    assert step_def.provider_policy.to_layer_payload() == {"effort": "low"}
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.model.effort == "high"
    assert provider.calls[1].policy is not None
    assert provider.calls[1].policy.model.effort == "low"


def test_sdk_inline_operations_apply_runtime_sdk_workflow_run_step_and_explicit_layers(tmp_path: Path) -> None:
    class InlinePolicyWorkflow(simple.Workflow):
        class State(BaseModel):
            summary: str = ""

        policy = Policy(deny_write=".env")

        @simple.python_step(policy=Policy(read_only=True), routes={"done": FINISH})
        def implement(ctx):
            ctx.state = ctx.state.model_copy(
                update={"summary": simple.llm("Summarize.", policy=Policy(effort=ModelEffort.HIGH))}
            )
            return Event("done")

    provider = ScriptedLLMProvider(operation_turns=["summary"])
    client = _sdk_client(
        tmp_path,
        provider,
        default_policy=Policy(network_domains=("docs.python.org",)),
        provider_policy_config=ProviderPolicyRuntimeConfig(
            default=ProviderPolicy(permissions=PermissionPolicy(mode="ask"))
        ),
    )

    result = client.run(
        InlinePolicyWorkflow,
        "Run it.",
        policy=Policy(allow_write="reports/"),
    )

    assert result.ok is True
    assert result.state.summary == "summary"
    assert provider.calls[0].kind == "operation"
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.permissions.mode == "ask"
    assert provider.calls[0].policy.model.effort == "high"
    assert provider.calls[0].policy.sandbox.mode == "read_only"
    assert provider.calls[0].policy.sandbox.workspace.filesystem.allow_write == ()
    assert provider.calls[0].policy.sandbox.workspace.filesystem.deny_write == (".env",)
    assert provider.calls[0].policy.sandbox.workspace.network.mode == "limited"
    assert provider.calls[0].policy.sandbox.workspace.network.allow_domains == ("docs.python.org",)


def test_sdk_workspace_root_stays_distinct_from_state_root_for_policy_relative_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_dir = tmp_path / "state-root"

    def _assert_workspace_root(request):
        assert request.context is not None
        assert request.context.root == workspace.resolve()
        assert request.policy is not None
        assert request.policy.sandbox.workspace.filesystem.allow_write == ("reports/",)
        return Outcome(raw_output='{"tag":"done"}', tag="done")

    provider = ScriptedLLMProvider(llm_turns=[_assert_workspace_root])
    client = _sdk_client(
        workspace,
        provider,
        state_dir=state_dir,
    )

    result = client.run(
        _PolicyRuntimeWorkflow,
        "Run it.",
        policy=Policy(allow_write="reports/"),
    )

    assert result.ok is True
    assert state_dir.resolve() != workspace.resolve()
    assert provider.calls[0].policy is not None
    assert provider.calls[0].policy.sandbox.workspace.filesystem.allow_write == ("reports/",)
