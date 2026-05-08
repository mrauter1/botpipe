from __future__ import annotations

from pathlib import Path

import pytest

import autoloop
import autoloop.simple as simple
from autoloop import FINISH, Workflow, llm, step
from autoloop.core.compiler import compile_workflow
from autoloop.core.provider_policy import (
    ProviderPolicy,
    ProviderPolicyOverride,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    merge_provider_policies,
)


def test_policy_surface_exports_are_public() -> None:
    from autoloop import (
        ModelEffort,
        ModelVerbosity,
        NetworkMode,
        PermissionMode,
        Policy,
        PolicyOverride,
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
        PolicyOverride as SimplePolicyOverride,
        ProviderName as SimpleProviderName,
        ReasoningSummary as SimpleReasoningSummary,
        SandboxMode as SimpleSandboxMode,
    )

    assert Policy is autoloop.Policy is simple.Policy is SimplePolicy
    assert PolicyOverride is autoloop.PolicyOverride is simple.PolicyOverride is SimplePolicyOverride
    assert ProviderName is autoloop.ProviderName is simple.ProviderName is SimpleProviderName
    assert ModelEffort is autoloop.ModelEffort is simple.ModelEffort is SimpleModelEffort
    assert ModelVerbosity is autoloop.ModelVerbosity is simple.ModelVerbosity is SimpleModelVerbosity
    assert ReasoningSummary is autoloop.ReasoningSummary is simple.ReasoningSummary is SimpleReasoningSummary
    assert SandboxMode is autoloop.SandboxMode is simple.SandboxMode is SimpleSandboxMode
    assert NetworkMode is autoloop.NetworkMode is simple.NetworkMode is SimpleNetworkMode
    assert PermissionMode is autoloop.PermissionMode is simple.PermissionMode is SimplePermissionMode

    for name in (
        "Policy",
        "PolicyOverride",
        "ProviderName",
        "ModelEffort",
        "ModelVerbosity",
        "ReasoningSummary",
        "SandboxMode",
        "NetworkMode",
        "PermissionMode",
    ):
        assert name in autoloop.__all__

    assert callable(Policy)
    assert callable(PolicyOverride)


def test_policy_tuple_helpers_normalize_paths_strings_and_duplicates() -> None:
    assert simple._policy_tuple(None, field_name="allow_write") == ()
    assert simple._policy_optional_tuple(None, field_name="allow_write") is None
    assert simple._policy_tuple(" src/ ", field_name="allow_write") == ("src/",)
    assert simple._policy_tuple(Path("src"), field_name="allow_write") == ("src",)
    assert simple._policy_tuple(
        (Path("src"), " src ", "tests/"),
        field_name="allow_write",
    ) == ("src", "tests/")


def test_policy_tuple_helpers_reject_invalid_entries() -> None:
    with pytest.raises(TypeError):
        simple._policy_tuple(b"src/", field_name="allow_write")
    with pytest.raises(TypeError):
        simple._policy_tuple((b"src/",), field_name="allow_write")
    with pytest.raises(TypeError):
        simple._policy_tuple((object(),), field_name="allow_write")
    with pytest.raises(ValueError):
        simple._policy_tuple(("  ",), field_name="allow_write")


def test_policy_string_mapping_helper_coerces_and_validates() -> None:
    assert simple._policy_string_mapping(None, field_name="model_overrides") is None
    assert simple._policy_string_mapping(
        {" provider ": 1},
        field_name="model_overrides",
    ) == {"provider": "1"}

    with pytest.raises(TypeError):
        simple._policy_string_mapping(("a", "b"), field_name="model_overrides")
    with pytest.raises(ValueError):
        simple._policy_string_mapping({"   ": "value"}, field_name="model_overrides")


def test_policy_returns_provider_policy_and_preserves_defaults() -> None:
    policy = simple.Policy()

    assert isinstance(policy, ProviderPolicy)
    assert policy == SYSTEM_DEFAULT_PROVIDER_POLICY
    assert policy.permissions.mode == SYSTEM_DEFAULT_PROVIDER_POLICY.permissions.mode
    assert policy.sandbox.mode == SYSTEM_DEFAULT_PROVIDER_POLICY.sandbox.mode


def test_policy_override_returns_sparse_provider_policy_override() -> None:
    override = simple.PolicyOverride(effort=simple.ModelEffort.LOW)

    assert isinstance(override, ProviderPolicyOverride)
    assert override.model is not None
    assert override.model.effort == "low"
    assert override.sandbox is None
    assert override.permissions is None


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (simple.Policy, {"effort": "medium"}),
        (simple.Policy, {"provider": "codex"}),
        (simple.Policy, {"verbosity": "high"}),
        (simple.Policy, {"reasoning_summary": "concise"}),
        (simple.Policy, {"sandbox_mode": "workspace_write"}),
        (simple.Policy, {"network": "none"}),
        (simple.Policy, {"permission_mode": "full_auto_unsandboxed"}),
        (simple.PolicyOverride, {"effort": "medium"}),
        (simple.PolicyOverride, {"provider": "codex"}),
        (simple.PolicyOverride, {"verbosity": "high"}),
        (simple.PolicyOverride, {"reasoning_summary": "concise"}),
        (simple.PolicyOverride, {"sandbox_mode": "workspace_write"}),
        (simple.PolicyOverride, {"network": "none"}),
        (simple.PolicyOverride, {"permission_mode": "full_auto_unsandboxed"}),
    ],
)
def test_policy_helpers_reject_raw_strings_for_enum_backed_fields(factory, kwargs) -> None:
    with pytest.raises(TypeError):
        factory(**kwargs)


def test_workflow_level_policy_lowers_flat_fields() -> None:
    policy = simple.Policy(
        network_domains=("docs.python.org", "github.com"),
        allow_write=("src/", "tests/"),
        effort=simple.ModelEffort.MEDIUM,
    )

    assert isinstance(policy, ProviderPolicy)
    assert policy.model.effort == "medium"
    assert policy.sandbox.mode == "workspace_write"
    assert policy.sandbox.workspace.filesystem.allow_write == ("src/", "tests/")
    assert policy.sandbox.workspace.network.mode == "limited"
    assert policy.sandbox.workspace.network.allow_domains == ("docs.python.org", "github.com")


def test_policy_lowers_provider_and_normalizes_filesystem_entries() -> None:
    provider_policy = simple.Policy(provider=simple.ProviderName.CODEX)
    write_policy = simple.Policy(allow_write="src/")
    deny_policy = simple.Policy(deny_write=(".env", ".env", "secrets/"))

    assert provider_policy.model.provider == "codex"
    assert write_policy.sandbox.workspace.filesystem.allow_write == ("src/",)
    assert deny_policy.sandbox.workspace.filesystem.deny_write == (".env", "secrets/")


def test_policy_read_only_and_network_validation_rules() -> None:
    policy = simple.Policy(read_only=True)

    assert policy.sandbox.mode == "read_only"
    assert policy.sandbox.workspace.filesystem.allow_write == ()

    with pytest.raises(ValueError):
        simple.Policy(read_only=True, allow_write="src/")
    with pytest.raises(ValueError):
        simple.Policy(sandbox_mode=simple.SandboxMode.READ_ONLY, allow_write="src/")
    with pytest.raises(ValueError):
        simple.Policy(network=simple.NetworkMode.LIMITED)
    with pytest.raises(ValueError):
        simple.Policy(network_domains=())
    with pytest.raises(ValueError):
        simple.Policy(network=simple.NetworkMode.NONE, network_domains=("github.com",))
    with pytest.raises(ValueError):
        simple.Policy(network=simple.NetworkMode.FULL, network_domains=("github.com",))


def test_policy_can_disable_network() -> None:
    policy = simple.Policy(network=simple.NetworkMode.NONE)

    assert policy.sandbox.workspace.network.enabled is False
    assert policy.sandbox.workspace.network.mode == "none"
    assert policy.sandbox.workspace.network.allow_domains == ()


def test_dangerous_workflow_level_policy_inference_and_validation() -> None:
    permission_policy = simple.Policy(permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED)

    assert permission_policy.permissions.mode == "full_auto_unsandboxed"
    assert permission_policy.permissions.allow_dangerous_bypass is True
    assert permission_policy.sandbox.mode == "danger_full_access"

    with pytest.raises(ValueError):
        simple.Policy(sandbox_mode=simple.SandboxMode.DANGER_FULL_ACCESS)
    with pytest.raises(ValueError):
        simple.Policy(
            permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
            sandbox_mode=simple.SandboxMode.WORKSPACE_WRITE,
        )
    with pytest.raises(ValueError):
        simple.Policy(
            permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
            sandbox_mode=simple.SandboxMode.READ_ONLY,
        )
    with pytest.raises(ValueError):
        simple.Policy(
            sandbox_mode=simple.SandboxMode.DANGER_FULL_ACCESS,
            permission_mode=simple.PermissionMode.FULL_AUTO_SANDBOXED,
        )


def test_override_lowers_sparse_fields_and_merge_preserves_defaults() -> None:
    override = simple.PolicyOverride(effort=simple.ModelEffort.LOW)
    resolved = merge_provider_policies(SYSTEM_DEFAULT_PROVIDER_POLICY, override)

    assert isinstance(override, ProviderPolicyOverride)
    assert override.model is not None
    assert override.model.effort == "low"
    assert override.sandbox is None
    assert override.permissions is None
    assert resolved.model.effort == "low"
    assert resolved.sandbox == SYSTEM_DEFAULT_PROVIDER_POLICY.sandbox
    assert resolved.permissions == SYSTEM_DEFAULT_PROVIDER_POLICY.permissions


def test_override_filesystem_and_network_lowering() -> None:
    write_override = simple.PolicyOverride(allow_write="src/")
    network_override = simple.PolicyOverride(network_domains="docs.python.org")
    read_only_override = simple.PolicyOverride(read_only=True)

    assert write_override.sandbox is not None
    assert write_override.sandbox.mode == "workspace_write"
    assert write_override.sandbox.workspace.filesystem.allow_write == ("src/",)

    assert network_override.sandbox is not None
    assert network_override.sandbox.workspace.network.mode == "limited"
    assert network_override.sandbox.workspace.network.allow_domains == ("docs.python.org",)

    assert read_only_override.sandbox is not None
    assert read_only_override.sandbox.mode == "read_only"
    assert read_only_override.sandbox.workspace.filesystem.allow_write == ()


def test_override_merge_clears_and_replaces_write_roots() -> None:
    read_only_resolved = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        simple.PolicyOverride(read_only=True),
    )
    write_resolved = merge_provider_policies(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        simple.PolicyOverride(allow_write="src/"),
    )

    assert read_only_resolved.sandbox.mode == "read_only"
    assert read_only_resolved.sandbox.workspace.filesystem.allow_write == ()
    assert write_resolved.sandbox.mode == "workspace_write"
    assert write_resolved.sandbox.workspace.filesystem.allow_write == ("src/",)


def test_dangerous_override_inference_and_validation() -> None:
    permission_override = simple.PolicyOverride(
        permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED
    )
    resolved = merge_provider_policies(SYSTEM_DEFAULT_PROVIDER_POLICY, permission_override)

    assert permission_override.sandbox is not None
    assert permission_override.sandbox.mode == "danger_full_access"
    assert permission_override.permissions is not None
    assert permission_override.permissions.mode == "full_auto_unsandboxed"
    assert permission_override.permissions.allow_dangerous_bypass is True

    assert resolved.permissions.mode == "full_auto_unsandboxed"
    assert resolved.permissions.allow_dangerous_bypass is True
    assert resolved.sandbox.mode == "danger_full_access"

    with pytest.raises(ValueError):
        simple.PolicyOverride(sandbox_mode=simple.SandboxMode.DANGER_FULL_ACCESS)
    with pytest.raises(ValueError):
        simple.PolicyOverride(
            permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
            sandbox_mode=simple.SandboxMode.WORKSPACE_WRITE,
        )
    with pytest.raises(ValueError):
        simple.PolicyOverride(
            permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
            sandbox_mode=simple.SandboxMode.READ_ONLY,
        )
    with pytest.raises(ValueError):
        simple.PolicyOverride(
            sandbox_mode=simple.SandboxMode.DANGER_FULL_ACCESS,
            permission_mode=simple.PermissionMode.FULL_AUTO_SANDBOXED,
        )


def test_workflow_policy_compiles_with_flat_policy() -> None:
    class DocsPatchWorkflow(Workflow):
        policy = simple.Policy(
            network_domains=("docs.python.org",),
            allow_write="src/",
            effort=simple.ModelEffort.MEDIUM,
        )

        implement = step(
            "Update the code.",
            routes={"done": FINISH},
        )

    compiled = compile_workflow(DocsPatchWorkflow)

    assert isinstance(compiled.provider_policy, ProviderPolicy)
    assert compiled.provider_policy.model.effort == "medium"
    assert compiled.provider_policy.sandbox.mode == "workspace_write"
    assert compiled.provider_policy.sandbox.workspace.filesystem.allow_write == ("src/",)
    assert compiled.provider_policy.sandbox.workspace.network.mode == "limited"
    assert compiled.provider_policy.sandbox.workspace.network.allow_domains == ("docs.python.org",)


def test_step_policy_compiles_with_flat_override() -> None:
    class StepPolicyWorkflow(Workflow):
        inspect = step(
            "Inspect only.",
            policy=simple.PolicyOverride(
                effort=simple.ModelEffort.LOW,
                read_only=True,
            ),
            routes={"done": FINISH},
        )

    compiled = compile_workflow(StepPolicyWorkflow)
    step_policy = compiled.steps["inspect"].provider_policy

    assert isinstance(step_policy, ProviderPolicyOverride)
    assert step_policy.model is not None
    assert step_policy.model.effort == "low"
    assert step_policy.sandbox is not None
    assert step_policy.sandbox.mode == "read_only"
    assert step_policy.sandbox.workspace.filesystem.allow_write == ()


def test_dangerous_workflow_compiles_with_flat_policy() -> None:
    class DangerousWorkflow(Workflow):
        policy = simple.Policy(
            permission_mode=simple.PermissionMode.FULL_AUTO_UNSANDBOXED,
        )

        migrate = step(
            "Run migration.",
            routes={"done": FINISH},
        )

    compiled = compile_workflow(DangerousWorkflow)
    policy = compiled.provider_policy

    assert policy is not None
    assert policy.sandbox.mode == "danger_full_access"
    assert policy.permissions.mode == "full_auto_unsandboxed"
    assert policy.permissions.allow_dangerous_bypass is True


def test_flat_override_is_accepted_by_operation_policy_surface() -> None:
    operation = llm
    override = simple.PolicyOverride(effort=simple.ModelEffort.LOW)

    assert isinstance(operation, simple.LLMOperation)
    assert simple._normalize_provider_policy(override) is override
