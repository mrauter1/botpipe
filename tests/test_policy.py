from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from botpipe.policy import (
    NetworkMode,
    OperationKind,
    PermissionMode,
    Policy,
    ProviderName,
    SandboxMode,
)


def test_policy_round_trip_and_deduplicates_paths() -> None:
    policy = Policy.from_dict(
        {
            "model": "test-model",
            "base_url": "https://provider.invalid",
            "model_overrides": {"review": "test-review"},
            "sandbox_mode": "workspace_write",
            "network": "limited",
            "network_domains": ["example.com", "example.com"],
            "allow_write": ["out", "out"],
            "timeout": 12.5,
        }
    )
    assert policy.network is NetworkMode.LIMITED
    assert policy.allow_write == ("out",)
    assert Policy.from_dict(policy.to_dict()) == policy
    with pytest.raises(FrozenInstanceError):
        policy.model = "changed"  # type: ignore[misc]


def test_policy_merge_only_replaces_authored_fields() -> None:
    base = Policy(
        model="a",
        network=NetworkMode.LIMITED,
        network_domains=("example.com",),
        allow_write=("out",),
    )
    merged = base.merged(Policy(model="b", permission_mode=PermissionMode.ASK))
    assert merged.model == "b"
    assert merged.network_domains == ("example.com",)
    assert merged.allow_write == ("out",)


def test_policy_merge_read_only_clears_inherited_writes() -> None:
    base = Policy(sandbox_mode=SandboxMode.WORKSPACE_WRITE, allow_write=(".",))
    resolved = Policy.resolve(base, Policy(sandbox_mode=SandboxMode.READ_ONLY))
    assert resolved.sandbox_mode is SandboxMode.READ_ONLY
    assert resolved.allow_write == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"network": "limited"},
        {"network": "none", "network_domains": ["example.com"]},
        {"sandbox_mode": "read_only", "allow_write": ["out"]},
        {"sandbox_mode": "workspace_write", "permission_mode": "full_auto_unsandboxed"},
    ],
)
def test_policy_rejects_inconsistent_controls(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Policy.from_dict(payload)


def test_effective_policy_has_safe_explicit_defaults() -> None:
    policy = Policy().effective()
    assert policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
    assert policy.permission_mode is PermissionMode.ASK
    assert policy.network is NetworkMode.NONE
    assert policy.allow_write == (".",)


def test_provider_and_operation_enums_cover_new_native_contracts() -> None:
    assert {value.value for value in ProviderName} == {"codex", "claude", "pi", "jev"}
    assert {value.value for value in OperationKind} == {"generate", "query", "run"}


@pytest.mark.parametrize(
    ("base", "override", "field"),
    [
        (Policy(sandbox_mode="read_only"), Policy(sandbox_mode="workspace_write"), "sandbox_mode"),
        (Policy(network="none"), Policy(network="limited", network_domains=("x.test",)), "network"),
        (Policy(permission_mode="ask"), Policy(permission_mode="full_auto_sandboxed"), "permission_mode"),
        (Policy(allow_read=("src",)), Policy(allow_read=("../outside",)), "allow_read"),
        (Policy(network="limited", network_domains=("api.test",)), Policy(network_domains=("other.test",)), "network_domains"),
        (Policy(allow_local_binding=False), Policy(allow_local_binding=True), "local binding"),
        (Policy(timeout=5), Policy(timeout=6), "timeout"),
    ],
)
def test_policy_override_rejects_authority_broadening(
    base: Policy, override: Policy, field: str
) -> None:
    with pytest.raises(ValueError, match=field):
        base.merged(override)


def test_policy_override_can_narrow_paths_network_and_deadline() -> None:
    base = Policy(
        sandbox_mode="workspace_write",
        network="limited",
        network_domains=("api.test", "docs.test"),
        allow_read=(".",),
        allow_write=("generated",),
        timeout=10,
    )
    narrowed = base.merged(
        Policy(
            sandbox_mode="read_only",
            network="none",
            allow_read=("src",),
            allow_write=(),
            timeout=3,
        )
    )
    assert narrowed.sandbox_mode is SandboxMode.READ_ONLY
    assert narrowed.network is NetworkMode.NONE
    assert narrowed.allow_read == ("src",)
    assert narrowed.allow_write == ()
    assert narrowed.timeout == 3


def test_parent_denials_cannot_be_cleared_by_child_policy() -> None:
    base = Policy(
        deny_read=("secret",),
        deny_write=("protected",),
        deny_network_domains=("blocked.test",),
        deny_permissions=("Bash",),
    )
    merged = base.merged(
        Policy(
            deny_read=(),
            deny_write=("more",),
            deny_network_domains=(),
            deny_permissions=("Edit",),
        )
    )
    assert merged.deny_read == ("secret",)
    assert merged.deny_write == ("protected", "more")
    assert merged.deny_network_domains == ("blocked.test",)
    assert merged.deny_permissions == ("Bash", "Edit")


def test_current_policy_intersection_keeps_narrower_overlapping_roots() -> None:
    saved = Policy(
        sandbox_mode="workspace_write",
        allow_read=(".",),
        allow_write=("generated", "cache"),
    )
    current = Policy(
        sandbox_mode="workspace_write",
        allow_read=("src",),
        allow_write=("generated/reports", "tmp"),
    )

    effective = saved.intersect(current)

    assert effective.allow_read == ("src",)
    assert effective.allow_write == ("generated/reports",)


def test_current_policy_intersection_preserves_limited_domain_scope() -> None:
    saved = Policy(
        network="limited",
        network_domains=("*.example.com", "unrelated.test"),
    )
    current = Policy(
        network="limited",
        network_domains=("api.example.com", "other.test"),
    )

    effective = saved.intersect(current)

    assert effective.network is NetworkMode.LIMITED
    assert effective.network_domains == ("api.example.com",)


def test_disjoint_limited_domains_intersect_to_no_network() -> None:
    saved = Policy(network="limited", network_domains=("api.example",))
    current = Policy(network="limited", network_domains=("other.example",))

    effective = saved.intersect(current)

    assert effective.network is NetworkMode.NONE
    assert effective.network_domains == ()


def test_current_policy_intersection_unions_denials_and_uses_shorter_deadline() -> None:
    saved = Policy(deny_read=("saved-secret",), timeout=30)
    current = Policy(
        sandbox_mode="read_only", deny_read=("deployment-secret",), timeout=5
    )

    effective = saved.intersect(current)

    assert effective.sandbox_mode is SandboxMode.READ_ONLY
    assert effective.deny_read == ("saved-secret", "deployment-secret")
    assert effective.timeout == 5


def test_empty_current_policy_is_identity_for_effective_authority() -> None:
    saved = Policy(
        sandbox_mode="danger_full_access",
        permission_mode="full_auto_unsandboxed",
        network="full",
        allow_local_binding=True,
    ).effective()

    assert saved.intersect(Policy()) == saved
