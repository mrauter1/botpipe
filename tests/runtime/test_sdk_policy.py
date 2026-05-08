from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import autoloop.simple as simple
from autoloop import FINISH, Autoloop
from autoloop.core.primitives import Event, Outcome
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.steps import PromptStep
from autoloop.policy import ModelEffort, PermissionMode, Policy
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig


def _sdk_client(
    tmp_path: Path,
    provider: ScriptedLLMProvider,
    *,
    default_policy: Policy | None = None,
) -> Autoloop:
    return Autoloop(
        workspace=tmp_path,
        provider=provider,
        default_policy=default_policy,
        state_dir=tmp_path / ".autoloop",
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
