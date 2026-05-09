from __future__ import annotations

import hashlib
import json
import re

import pytest

import botlane.policy as public_policy
from botlane import FINISH, Workflow, step
from botlane.core.compiler import (
    _policy_input_fingerprint,
    _policy_input_payload,
    compile_workflow,
)
from botlane.core.provider_policy import (
    ProviderPolicy,
    ProviderPolicyOverride,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    policy_fingerprint,
)


def _payload_fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_public_policy_imports_and_all() -> None:
    from botlane import (
        ModelEffort,
        ModelVerbosity,
        NetworkMode,
        PermissionMode,
        Policy,
        ProviderName,
        ReasoningSummary,
        SandboxMode,
    )
    from botlane.policy import Policy as ModulePolicy

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


def test_policy_docstring_describes_sparse_inheriting_public_contract() -> None:
    doc = public_policy.Policy.__doc__

    assert doc is not None
    assert "stores only supplied fields" in doc
    assert "inherit from the effective" in doc
    assert "policy enums rather than raw strings" in doc
    assert "network_domains implies limited network mode" in doc
    assert "permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED" in doc


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

    dangerous_manual = public_policy.Policy(
        sandbox_mode=public_policy.SandboxMode.DANGER_FULL_ACCESS
    ).resolve()
    assert dangerous_manual.permissions.mode == "ask"
    assert dangerous_manual.permissions.allow_dangerous_bypass is True
    assert dangerous_manual.sandbox.mode == "danger_full_access"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "read_only": True,
                "sandbox_mode": public_policy.SandboxMode.WORKSPACE_WRITE,
            },
            "read_only=True is incompatible with sandbox_mode other than SandboxMode.READ_ONLY",
        ),
        (
            {
                "read_only": True,
                "allow_write": "src/",
            },
            "allow_write cannot be set when sandbox mode is read-only",
        ),
        (
            {
                "permission_mode": public_policy.PermissionMode.FULL_AUTO_UNSANDBOXED,
                "sandbox_mode": public_policy.SandboxMode.WORKSPACE_WRITE,
            },
            "permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED requires sandbox_mode=SandboxMode.DANGER_FULL_ACCESS",
        ),
        (
            {
                "sandbox_mode": public_policy.SandboxMode.DANGER_FULL_ACCESS,
                "permission_mode": public_policy.PermissionMode.FULL_AUTO_SANDBOXED,
            },
            "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS is incompatible with permission_mode=PermissionMode.FULL_AUTO_SANDBOXED",
        ),
        (
            {
                "network_domains": (),
            },
            "network_domains must not be empty when provided",
        ),
        (
            {
                "network": public_policy.NetworkMode.LIMITED,
            },
            "network=NetworkMode.LIMITED requires non-empty network_domains",
        ),
        (
            {
                "network": public_policy.NetworkMode.FULL,
                "network_domains": ("docs.python.org",),
            },
            "network='full' cannot be combined with network_domains",
        ),
    ],
)
def test_policy_same_layer_validation_preserves_exact_messages(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        public_policy.Policy(**kwargs)


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


def test_policy_to_layer_payload_serializes_nested_public_policy_bases_as_policy_layers() -> None:
    base = public_policy.Policy(effort=public_policy.ModelEffort.LOW)
    child = public_policy.Policy(base=base, allow_write="reports/")
    payload = child.to_layer_payload()

    assert payload["allow_write"] == ["reports/"]
    assert payload["base"] == {
        "kind": "policy_layer",
        "payload": {"effort": "low"},
    }
    encoded = json.dumps(payload, sort_keys=True)
    assert '"kind": "policy"' not in encoded
    assert '"kind": "layer"' not in encoded


def test_policy_to_layer_payload_serializes_concrete_provider_policy_bases() -> None:
    base = ProviderPolicy(permissions={"mode": "ask"})
    child = public_policy.Policy(
        base=base,
        effort=public_policy.ModelEffort.HIGH,
        allow_write=("src/", "tests/"),
    )

    assert child.to_layer_payload() == {
        "effort": "high",
        "allow_write": ["src/", "tests/"],
        "base": {
            "kind": "provider_policy",
            "payload": base.model_dump(mode="json", warnings=False),
        },
    }


def test_policy_input_payload_and_fingerprint_use_explicit_kind_labels() -> None:
    policy_layer = public_policy.Policy(effort=public_policy.ModelEffort.LOW)
    provider_policy = ProviderPolicy(model={"effort": "low"})
    provider_policy_override = ProviderPolicyOverride(model={"effort": "low"})

    layer_payload = _policy_input_payload(policy_layer)
    provider_payload = _policy_input_payload(provider_policy)
    override_payload = _policy_input_payload(provider_policy_override)

    assert layer_payload == {
        "kind": "policy_layer",
        "payload": {"effort": "low"},
    }
    assert provider_payload == {
        "kind": "provider_policy",
        "payload": provider_policy.model_dump(mode="json", warnings=False),
    }
    assert override_payload == {
        "kind": "provider_policy_override",
        "payload": provider_policy_override.model_dump(mode="json", warnings=False),
    }

    assert _policy_input_fingerprint(policy_layer) == _payload_fingerprint(layer_payload)
    assert _policy_input_fingerprint(provider_policy) == _payload_fingerprint(provider_payload)
    assert _policy_input_fingerprint(provider_policy_override) == _payload_fingerprint(override_payload)
    assert _policy_input_fingerprint(provider_policy) != policy_fingerprint(provider_policy)
    assert len(
        {
            _policy_input_fingerprint(policy_layer),
            _policy_input_fingerprint(provider_policy),
            _policy_input_fingerprint(provider_policy_override),
        }
    ) == 3


def test_policy_payload_and_fingerprint_are_deterministic_for_identical_authored_layers() -> None:
    left = public_policy.Policy(
        base=public_policy.Policy(effort=public_policy.ModelEffort.LOW),
        allow_write=("reports/", "src/"),
    )
    right = public_policy.Policy(
        base=public_policy.Policy(effort=public_policy.ModelEffort.LOW),
        allow_write=("reports/", "src/"),
    )
    different = public_policy.Policy(
        base=ProviderPolicy(model={"effort": "low"}),
        allow_write=("reports/", "src/"),
    )
    authored_different = public_policy.Policy(
        base=public_policy.Policy(effort=public_policy.ModelEffort.HIGH),
        allow_write=("reports/", "src/"),
    )

    assert left.to_layer_payload() == right.to_layer_payload()
    assert _policy_input_fingerprint(left) == _policy_input_fingerprint(right)
    assert left.to_layer_payload() != authored_different.to_layer_payload()
    assert _policy_input_fingerprint(left) != _policy_input_fingerprint(authored_different)
    assert _policy_input_payload(left) != _policy_input_payload(different)
    assert _policy_input_fingerprint(left) != _policy_input_fingerprint(different)


def test_policy_layer_payload_and_compiler_fingerprint_support_public_policy() -> None:
    policy = public_policy.Policy(
        base=ProviderPolicy(permissions={"mode": "ask"}),
        effort=public_policy.ModelEffort.HIGH,
        allow_write=("src/", "tests/"),
    )
    assert _policy_input_payload(policy) == {
        "kind": "policy_layer",
        "payload": policy.to_layer_payload(),
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


def test_public_policy_changes_participate_in_topology_hash_for_workflow_and_step_layers() -> None:
    class WorkflowLow(Workflow):
        policy = public_policy.Policy(effort=public_policy.ModelEffort.LOW)
        implement = step("Update the code.", routes={"done": FINISH})

    class WorkflowHigh(Workflow):
        policy = public_policy.Policy(effort=public_policy.ModelEffort.HIGH)
        implement = step("Update the code.", routes={"done": FINISH})

    class StepLow(Workflow):
        implement = step(
            "Inspect the code.",
            policy=public_policy.Policy(effort=public_policy.ModelEffort.LOW),
            routes={"done": FINISH},
        )

    class StepHigh(Workflow):
        implement = step(
            "Inspect the code.",
            policy=public_policy.Policy(effort=public_policy.ModelEffort.HIGH),
            routes={"done": FINISH},
        )

    assert compile_workflow(WorkflowLow).topology_hash != compile_workflow(WorkflowHigh).topology_hash
    assert compile_workflow(StepLow).topology_hash != compile_workflow(StepHigh).topology_hash


def test_compile_and_resolve_dangerous_manual_workflow_policy() -> None:
    class DangerousManualWorkflow(Workflow):
        policy = public_policy.Policy(
            sandbox_mode=public_policy.SandboxMode.DANGER_FULL_ACCESS,
            effort=public_policy.ModelEffort.HIGH,
        )

        inspect = step("Inspect only.", routes={"done": FINISH})

    compiled = compile_workflow(DangerousManualWorkflow)
    resolved = public_policy.resolve_policy_layer(
        SYSTEM_DEFAULT_PROVIDER_POLICY,
        compiled.provider_policy,
    )

    assert resolved.model.effort == "high"
    assert resolved.permissions.mode == "ask"
    assert resolved.permissions.allow_dangerous_bypass is True
    assert resolved.sandbox.mode == "danger_full_access"


def test_dangerous_manual_policy_preserves_non_full_auto_base_permissions() -> None:
    base = ProviderPolicy(permissions={"mode": "auto_edit"})

    resolved = public_policy.resolve_policy_layer(
        base,
        public_policy.Policy(sandbox_mode=public_policy.SandboxMode.DANGER_FULL_ACCESS),
    )

    assert resolved.permissions.mode == "auto_edit"
    assert resolved.permissions.allow_dangerous_bypass is True
    assert resolved.sandbox.mode == "danger_full_access"
