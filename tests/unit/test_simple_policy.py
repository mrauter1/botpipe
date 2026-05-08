from __future__ import annotations

import pytest

import autoloop
import autoloop.policy as public_policy
import autoloop.simple as simple
from autoloop.core.provider_policy import ProviderPolicy, ProviderPolicyOverride
from autoloop.policy import PermissionMode, Policy


def test_policy_surface_exports_shared_policy_symbols() -> None:
    from autoloop import (
        ModelEffort,
        ModelVerbosity,
        NetworkMode,
        PermissionMode as RootPermissionMode,
        Policy as RootPolicy,
        ProviderName,
        ReasoningSummary,
        SandboxMode,
    )
    from autoloop.simple import (
        ModelEffort as SimpleModelEffort,
        ModelVerbosity as SimpleModelVerbosity,
        NetworkMode as SimpleNetworkMode,
        PermissionMode as SimplePermissionMode,
        Policy as SimplePolicy,
        ProviderName as SimpleProviderName,
        ReasoningSummary as SimpleReasoningSummary,
        SandboxMode as SimpleSandboxMode,
    )

    assert RootPolicy is autoloop.Policy is simple.Policy is Policy is SimplePolicy
    assert ProviderName is autoloop.ProviderName is simple.ProviderName is SimpleProviderName
    assert ModelEffort is autoloop.ModelEffort is simple.ModelEffort is SimpleModelEffort
    assert ModelVerbosity is autoloop.ModelVerbosity is simple.ModelVerbosity is SimpleModelVerbosity
    assert ReasoningSummary is autoloop.ReasoningSummary is simple.ReasoningSummary is SimpleReasoningSummary
    assert SandboxMode is autoloop.SandboxMode is simple.SandboxMode is SimpleSandboxMode
    assert NetworkMode is autoloop.NetworkMode is simple.NetworkMode is SimpleNetworkMode
    assert RootPermissionMode is autoloop.PermissionMode is simple.PermissionMode is SimplePermissionMode

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
        assert name in autoloop.__all__

    assert "PolicyOverride" not in autoloop.__all__
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
    with pytest.raises(ImportError):
        exec("from autoloop import PolicyOverride")
    with pytest.raises(AttributeError):
        getattr(simple, "PolicyOverride")


def test_simple_declarations_accept_public_policy_layers() -> None:
    step_policy = simple.Policy(permission_mode=PermissionMode.ASK)

    class PolicyWorkflow(simple.Workflow):
        policy = simple.Policy(permission_mode=PermissionMode.FULL_AUTO_SANDBOXED)
        draft = simple.step("Draft.", policy=step_policy)

    assert isinstance(PolicyWorkflow.policy, Policy)
    assert isinstance(PolicyWorkflow.draft.policy, Policy)


def test_simple_declarations_keep_internal_override_compatibility() -> None:
    override = ProviderPolicyOverride(permissions={"mode": "ask"})
    declaration = simple.step("Draft.", policy=override)

    assert declaration.policy is override
