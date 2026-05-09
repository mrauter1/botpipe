from __future__ import annotations

import re

import pytest

import botlane
import botlane.policy as public_policy
import botlane.sdk as sdk
import botlane.simple as simple
from botlane.core.primitives import Event
from botlane.core.steps import PythonStep
from botlane.core.provider_policy import ProviderPolicy, ProviderPolicyOverride
from botlane.policy import PermissionMode, Policy


def test_policy_surface_exports_shared_policy_symbols() -> None:
    from botlane import (
        ModelEffort,
        ModelVerbosity,
        NetworkMode,
        PermissionMode as RootPermissionMode,
        Policy as RootPolicy,
        ProviderName,
        ReasoningSummary,
        SandboxMode,
    )
    from botlane.simple import (
        ModelEffort as SimpleModelEffort,
        ModelVerbosity as SimpleModelVerbosity,
        NetworkMode as SimpleNetworkMode,
        PermissionMode as SimplePermissionMode,
        Policy as SimplePolicy,
        ProviderName as SimpleProviderName,
        ReasoningSummary as SimpleReasoningSummary,
        SandboxMode as SimpleSandboxMode,
    )

    assert RootPolicy is botlane.Policy is simple.Policy is Policy is SimplePolicy
    assert ProviderName is botlane.ProviderName is simple.ProviderName is SimpleProviderName
    assert ModelEffort is botlane.ModelEffort is simple.ModelEffort is SimpleModelEffort
    assert ModelVerbosity is botlane.ModelVerbosity is simple.ModelVerbosity is SimpleModelVerbosity
    assert ReasoningSummary is botlane.ReasoningSummary is simple.ReasoningSummary is SimpleReasoningSummary
    assert SandboxMode is botlane.SandboxMode is simple.SandboxMode is SimpleSandboxMode
    assert NetworkMode is botlane.NetworkMode is simple.NetworkMode is SimpleNetworkMode
    assert RootPermissionMode is botlane.PermissionMode is simple.PermissionMode is SimplePermissionMode

    for name in (
        "Policy",
        "ProviderName",
        "ModelEffort",
        "ModelVerbosity",
        "ReasoningSummary",
        "SandboxMode",
        "NetworkMode",
        "PermissionMode",
    ):
        assert name in botlane.__all__

    assert "PolicyOverride" not in botlane.__all__
    assert "PolicyOverride" not in simple.__all__


def test_policy_is_sparse_and_resolves_against_defaults() -> None:
    policy = simple.Policy()
    resolved = policy.resolve()

    assert isinstance(policy, Policy)
    assert isinstance(resolved, ProviderPolicy)
    assert policy.to_layer_payload() == {}
    assert resolved == public_policy.SYSTEM_DEFAULT_PROVIDER_POLICY


def test_policy_resolves_public_layers_and_internal_overrides() -> None:
    base = simple.Policy(permission_mode=simple.PermissionMode.ASK, read_only=True)
    child = simple.Policy(base=base, allow_write="reports/")
    internal = ProviderPolicyOverride(permissions={"mode": "full_auto_sandboxed"})

    resolved = child.resolve()
    merged = public_policy.resolve_policy_layer(resolved, internal)

    assert resolved.permissions.mode == "ask"
    assert resolved.sandbox.mode == "workspace_write"
    assert resolved.sandbox.workspace.filesystem.allow_write == ("reports/",)
    assert merged.permissions.mode == "full_auto_sandboxed"


def test_policy_rejects_removed_public_policy_override_symbol() -> None:
    with pytest.raises(AttributeError):
        getattr(simple, "PolicyOverride")
    with pytest.raises(AttributeError):
        getattr(simple, "ProviderPolicyOverride")


def test_policy_input_export_matrix_matches_phase_contract() -> None:
    assert "PolicyInput" in public_policy.__all__
    assert "PolicyInput" in sdk.__all__
    assert "PolicyInput" not in botlane.__all__
    assert "PolicyInput" not in simple.__all__
    assert "ProviderPolicyInput" not in simple.__all__

    assert sdk.PolicyInput is public_policy.PolicyInput

    with pytest.raises(AttributeError):
        getattr(botlane, "PolicyInput")
    with pytest.raises(AttributeError):
        getattr(simple, "PolicyInput")
    with pytest.raises(AttributeError):
        getattr(simple, "ProviderPolicyInput")


def test_policy_module_export_lists_match_public_surface_contract() -> None:
    assert tuple(public_policy.__all__) == (
        "Policy",
        "PolicyInput",
        "ProviderName",
        "ModelEffort",
        "ModelVerbosity",
        "ReasoningSummary",
        "SandboxMode",
        "NetworkMode",
        "PermissionMode",
        "resolve_policy_layer",
    )
    assert "PolicyOverride" not in public_policy.__all__
    assert "PolicyOverride" not in sdk.__all__
    assert "PolicyOverride" not in simple.__all__

    for name in (
        "Policy",
        "ProviderName",
        "ModelEffort",
        "ModelVerbosity",
        "ReasoningSummary",
        "SandboxMode",
        "NetworkMode",
        "PermissionMode",
    ):
        assert name in sdk.__all__
        assert name in simple.__all__

    assert "PolicyInput" in sdk.__all__
    assert "PolicyInput" not in simple.__all__


def test_public_policy_validation_wording_hides_internal_override_types() -> None:
    with pytest.raises(TypeError, match=r"policy must be a Policy or core provider policy object, or None"):
        simple.step("Draft.", policy="ask")  # type: ignore[arg-type]

    with pytest.raises(
        TypeError,
        match=r"provider_policy must be a Policy or core provider policy object, or None",
    ):
        PythonStep(
            name="capture",
            handler=lambda _ctx: Event("done"),
            provider_policy="ask",  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match=r"policy layer must be a Policy or core provider policy object, or None",
    ):
        public_policy.resolve_policy_layer(public_policy.SYSTEM_DEFAULT_PROVIDER_POLICY, "ask")  # type: ignore[arg-type]


def test_simple_declarations_accept_public_policy_layers() -> None:
    step_policy = simple.Policy(permission_mode=PermissionMode.ASK)

    class PolicyWorkflow(simple.Workflow):
        policy = simple.Policy(permission_mode=PermissionMode.FULL_AUTO_SANDBOXED)
        draft = simple.step("Draft.", policy=step_policy)

    assert isinstance(PolicyWorkflow.policy, Policy)
    assert isinstance(PolicyWorkflow.draft.policy, Policy)


def test_simple_declarations_accept_provider_policy_and_none() -> None:
    provider_policy = ProviderPolicy(permissions={"mode": "ask"})
    no_policy_declaration = simple.step("No policy.", policy=None)

    class PolicyWorkflow(simple.Workflow):
        policy = None
        draft = simple.step("Draft.", policy=provider_policy)

    assert PolicyWorkflow.policy is None
    assert PolicyWorkflow.draft.policy is provider_policy
    assert no_policy_declaration.policy is None


def test_simple_declarations_keep_internal_override_compatibility() -> None:
    override = ProviderPolicyOverride(permissions={"mode": "ask"})
    declaration = simple.step("Draft.", policy=override)

    assert declaration.policy is override


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "read_only": True,
                "allow_write": "src/",
            },
            "allow_write cannot be set when sandbox mode is read-only",
        ),
        (
            {
                "network": simple.NetworkMode.LIMITED,
            },
            "network=NetworkMode.LIMITED requires non-empty network_domains",
        ),
        (
            {
                "permission_mode": simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
                "sandbox_mode": simple.SandboxMode.WORKSPACE_WRITE,
            },
            "permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED requires sandbox_mode=SandboxMode.DANGER_FULL_ACCESS",
        ),
    ],
)
def test_simple_policy_validation_preserves_exact_public_messages(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        simple.Policy(**kwargs)
