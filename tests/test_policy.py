from dataclasses import FrozenInstanceError

import pytest

from botpipe.policy import NetworkMode, Policy, SandboxMode


def test_policy_round_trip_and_immutable_defaults():
    policy = Policy.from_dict(
        {"sandbox": "read-only", "network": False, "model": "future-model"}
    )
    assert policy.sandbox_mode is SandboxMode.READ_ONLY
    assert policy.network is NetworkMode.NONE
    assert Policy.from_dict(policy.to_dict()) == policy
    with pytest.raises(FrozenInstanceError):
        policy.model = "changed"


def test_scope_policy_narrows_and_keeps_model_independent():
    base = Policy(
        sandbox_mode=SandboxMode.WORKSPACE_WRITE, network=NetworkMode.NONE, model="a"
    )
    narrowed = Policy.resolve(base, {"sandbox_mode": "read_only", "model": "b"})
    assert narrowed.sandbox_mode is SandboxMode.READ_ONLY
    assert narrowed.network is NetworkMode.NONE
    assert narrowed.model == "b"
    with pytest.raises(ValueError, match="sandbox cannot widen"):
        Policy.resolve(narrowed, {"sandbox_mode": "workspace_write"})
    with pytest.raises(ValueError, match="network cannot widen"):
        Policy.resolve(base, {"network": "full"})


def test_no_authored_ceiling_allows_explicit_full_access():
    policy = Policy.resolve(None, {"sandbox": "full-access"}).effective()
    assert policy.sandbox_mode is SandboxMode.DANGER_FULL_ACCESS
    assert policy.network is NetworkMode.NONE


@pytest.mark.parametrize(
    "payload",
    [
        {"network": "limited"},
        {"allow_write": ["out"]},
        {"permission_mode": "full_auto_unsandboxed"},
        {"timeout": float("nan")},
        {"timeout": 0},
        {"timeout": True},
    ],
)
def test_policy_rejects_unsupported_or_invalid_configuration(payload):
    with pytest.raises((TypeError, ValueError)):
        Policy.from_dict(payload)


def test_effective_policy_has_explicit_defaults():
    policy = Policy().effective()
    assert policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
    assert policy.network is NetworkMode.NONE
