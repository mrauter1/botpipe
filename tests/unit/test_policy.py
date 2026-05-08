from __future__ import annotations

import pytest

import autoloop.policy as public_policy
from autoloop import FINISH, Workflow, step
from autoloop.core.compiler import compile_workflow
from autoloop.core.provider_policy import ProviderPolicy, ProviderPolicyOverride, SYSTEM_DEFAULT_PROVIDER_POLICY


def test_public_policy_imports_and_all() -> None:
    from autoloop import (
        ModelEffort,
        ModelVerbosity,
        NetworkMode,
        PermissionMode,
        Policy,
        ProviderName,
        ReasoningSummary,
        SandboxMode,
    )
    from autoloop.policy import Policy as ModulePolicy

    assert Policy is ModulePolicy is public_policy.Policy
    assert public_policy.__all__ == [
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
    ]
    assert ProviderName.CODEX.value == "codex"
    assert ModelEffort.MEDIUM.value == "medium"
    assert ModelVerbosity.HIGH.value == "high"
    assert ReasoningSummary.CONCISE.value == "concise"
    assert SandboxMode.WORKSPACE_WRITE.value == "workspace_write"
    assert NetworkMode.NONE.value == "none"
    assert PermissionMode.FULL_AUTO_UNSANDBOXED.value == "full_auto_unsandboxed"


def test_policy_rejects_raw_strings_for_enum_backed_fields() -> None:
    with pytest.raises(TypeError):
        public_policy.Policy(effort="medium")
    with pytest.raises(TypeError):
        public_policy.Policy(provider="codex")
    with pytest.raises(TypeError):
        public_policy.Policy(verbosity="high")
    with pytest.raises(TypeError):
        public_policy.Policy(reasoning_summary="concise")
    with pytest.raises(TypeError):
        public_policy.Policy(sandbox_mode="workspace_write")
    with pytest.raises(TypeError):
        public_policy.Policy(network="none")
    with pytest.raises(TypeError):
        public_policy.Policy(permission_mode="full_auto_unsandboxed")
    with pytest.raises(TypeError):
        public_policy.Policy(effort=public_policy.NetworkMode.FULL)


def test_policy_resolve_defaults_and_inheritance() -> None:
    assert public_policy.Policy().resolve() == SYSTEM_DEFAULT_PROVIDER_POLICY

    resolved = public_policy.Policy(effort=public_policy.ModelEffort.MEDIUM).resolve()
    assert resolved.model.effort == "medium"
    assert resolved.permissions.mode == SYSTEM_DEFAULT_PROVIDER_POLICY.permissions.mode

    write_policy = public_policy.Policy(allow_write="src/").resolve()
    assert write_policy.sandbox.mode == "workspace_write"
    assert write_policy.sandbox.workspace.filesystem.allow_write == ("src/",)

    read_only_policy = public_policy.Policy(read_only=True).resolve()
    assert read_only_policy.sandbox.mode == "read_only"
    assert read_only_policy.sandbox.workspace.filesystem.allow_write == ()

    base = public_policy.Policy(network_domains=("docs.python.org",), effort=public_policy.ModelEffort.LOW)
    child = public_policy.Policy(base=base, effort=public_policy.ModelEffort.HIGH)
    inherited = child.resolve()
    assert inherited.model.effort == "high"
    assert inherited.sandbox.workspace.network.mode == "limited"
    assert inherited.sandbox.workspace.network.allow_domains == ("docs.python.org",)


def test_policy_same_layer_validation_and_dangerous_access() -> None:
    with pytest.raises(ValueError):
        public_policy.Policy(network=public_policy.NetworkMode.LIMITED)
    with pytest.raises(ValueError):
        public_policy.Policy(network_domains=())
    with pytest.raises(ValueError):
        public_policy.Policy(read_only=True, allow_write="src/")
    with pytest.raises(ValueError):
        public_policy.Policy(
            permission_mode=public_policy.PermissionMode.FULL_AUTO_UNSANDBOXED,
            sandbox_mode=public_policy.SandboxMode.WORKSPACE_WRITE,
        )
    with pytest.raises(ValueError):
        public_policy.Policy(
            sandbox_mode=public_policy.SandboxMode.DANGER_FULL_ACCESS,
            permission_mode=public_policy.PermissionMode.FULL_AUTO_SANDBOXED,
        )

    dangerous = public_policy.Policy(
        permission_mode=public_policy.PermissionMode.FULL_AUTO_UNSANDBOXED
    ).resolve()
    assert dangerous.permissions.mode == "full_auto_unsandboxed"
    assert dangerous.permissions.allow_dangerous_bypass is True
    assert dangerous.sandbox.mode == "danger_full_access"


def test_resolve_policy_layer_accepts_policy_inputs_and_detects_cycles() -> None:
    base = ProviderPolicy()
    override = ProviderPolicyOverride(permissions={"mode": "ask"})

    resolved_override = public_policy.resolve_policy_layer(base, override)
    assert resolved_override.permissions.mode == "ask"

    resolved_policy = public_policy.resolve_policy_layer(
        base,
        public_policy.Policy(permission_mode=public_policy.PermissionMode.ASK),
    )
    assert resolved_policy.permissions.mode == "ask"

    concrete = ProviderPolicy(permissions={"mode": "deny_all"})
    resolved_concrete = public_policy.resolve_policy_layer(base, concrete)
    assert resolved_concrete.permissions.mode == "deny_all"

    first = public_policy.Policy()
    second = public_policy.Policy(base=first)
    first.base = second  # type: ignore[misc]
    with pytest.raises(ValueError, match="cyclic"):
        first.resolve()


def test_policy_layer_payload_and_compiler_fingerprint_support_public_policy() -> None:
    policy = public_policy.Policy(
        base=ProviderPolicy(permissions={"mode": "ask"}),
        effort=public_policy.ModelEffort.HIGH,
        allow_write=("src/", "tests/"),
    )
    assert policy.to_layer_payload() == {
        "effort": "high",
        "allow_write": ["src/", "tests/"],
        "base": {
            "kind": "provider_policy",
            "payload": ProviderPolicy(permissions={"mode": "ask"}).model_dump(mode="json", warnings=False),
        },
    }

    class DocsPatchWorkflow(Workflow):
        policy = public_policy.Policy(
            network_domains=("docs.python.org",),
            allow_write="src/",
            effort=public_policy.ModelEffort.MEDIUM,
        )

        implement = step("Update the code.", routes={"done": FINISH})

    compiled = compile_workflow(DocsPatchWorkflow)
    assert isinstance(compiled.provider_policy, public_policy.Policy)
    assert compiled.provider_policy.to_layer_payload()["effort"] == "medium"
