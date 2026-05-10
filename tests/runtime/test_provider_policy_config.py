from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from botlane.core.provider_policy import SYSTEM_DEFAULT_PROVIDER_POLICY
from botlane.runtime.config import ConfigError, resolve_runtime_config
import botlane.runtime.config as runtime_config


def _runtime_args(**overrides: object) -> argparse.Namespace:
    payload = {
        "provider": None,
        "model": None,
        "model_effort": None,
        "policy_file": None,
        "policy_validation_unsupported": None,
        "policy_validation_lossy": None,
        "policy_validation_unsafe_expansion": None,
        "max_steps": None,
        "no_git": False,
        "git_commit_policy": None,
        "no_trace": False,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def test_resolve_runtime_config_uses_system_default_provider_policy_when_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.provider_policy.default == SYSTEM_DEFAULT_PROVIDER_POLICY
    assert resolved.provider_policy.strict is None
    assert resolved.provider_policy.validation.unsupported == "fail"
    assert resolved.provider_policy.validation.lossy_mapping == "warn"
    assert resolved.provider_policy.validation.unsafe_expansion == "fail"


def test_resolve_runtime_config_merges_global_and_workspace_provider_policy_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_path = global_config_dir / "botlane.yaml"
    local_config_path = tmp_path / "botlane.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider_policy": {
                "default": {
                    "sandbox": {
                        "workspace": {
                            "filesystem": {
                                "deny_read": ["./.env"],
                                "allow_write": [".", "./build"],
                            }
                        }
                    },
                    "env": {"set": {"GLOBAL": "1"}},
                }
            }
        },
        local_config_path: {
            "provider_policy": {
                "default": {
                    "sandbox": {
                        "workspace": {
                            "filesystem": {
                                "deny_read": ["./secrets/**"],
                                "allow_write": [".", "./dist"],
                            }
                        }
                    },
                    "env": {"set": {"LOCAL": "2"}},
                }
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.provider_policy.default.sandbox.workspace.filesystem.allow_write == (".", "./dist")
    assert resolved.provider_policy.default.sandbox.workspace.filesystem.deny_read == ("./.env", "./secrets/**")
    assert resolved.provider_policy.default.env.set == {"GLOBAL": "1", "LOCAL": "2"}


def test_resolve_runtime_config_applies_workspace_strict_provider_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_path = global_config_dir / "botlane.yaml"
    local_config_path = tmp_path / "botlane.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider_policy": {
                "strict": {
                    "sandbox": {
                        "workspace": {
                            "filesystem": {"allowed_write_roots": [".", "./build"]}
                        }
                    }
                }
            }
        },
        local_config_path: {
            "provider_policy": {
                "strict": {
                    "sandbox": {
                        "allowed_modes": ["read_only"],
                        "workspace": {
                            "filesystem": {"required_deny_write": ["/etc", "/usr/local/bin", "/tmp"]}
                        },
                    }
                }
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.provider_policy.strict is not None
    assert resolved.provider_policy.strict.sandbox.allowed_modes == ("read_only",)
    assert resolved.provider_policy.strict.sandbox.workspace.filesystem.allowed_write_roots == (".", "./build")
    assert resolved.provider_policy.strict.sandbox.workspace.filesystem.required_deny_write == (
        "/etc",
        "/usr/local/bin",
        "/tmp",
    )


def test_workspace_strict_null_clears_inherited_strict_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config_dir = tmp_path / "global-config"
    global_config_path = global_config_dir / "botlane.yaml"
    local_config_path = tmp_path / "botlane.yaml"
    global_config_dir.mkdir(parents=True)
    global_config_path.write_text("", encoding="utf-8")
    local_config_path.write_text("", encoding="utf-8")

    payloads = {
        global_config_path: {
            "provider_policy": {
                "strict": {
                    "sandbox": {
                        "workspace": {
                            "filesystem": {"allowed_write_roots": [".", "./build"]}
                        }
                    }
                }
            }
        },
        local_config_path: {
            "provider_policy": {
                "strict": None,
            }
        },
    }
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: global_config_dir)
    monkeypatch.setattr(runtime_config, "load_runtime_config_file", lambda path: payloads[path])

    resolved = resolve_runtime_config(tmp_path, _runtime_args())

    assert resolved.provider_policy.strict is None


def test_policy_file_overrides_and_extends_provider_policy_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider_policy:\n"
        "  default:\n"
        "    sandbox:\n"
        "      workspace:\n"
        "        filesystem:\n"
        "          allow_write: [\".\"]\n",
        encoding="utf-8",
    )
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "default:\n"
        "  sandbox:\n"
        "    workspace:\n"
        "      filesystem:\n"
        "        allow_write: [\".\", \"./build\"]\n"
        "validation:\n"
        "  unsupported: ignore\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args(policy_file=policy_file))

    assert resolved.provider_policy.default.sandbox.workspace.filesystem.allow_write == (".", "./build")
    assert resolved.provider_policy.validation.unsupported == "ignore"


def test_policy_file_accepts_full_runtime_config_document_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text("", encoding="utf-8")
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "provider_policy:\n"
        "  default:\n"
        "    sandbox:\n"
        "      workspace:\n"
        "        filesystem:\n"
        "          allow_write: [\".\", \"./dist\"]\n"
        "  validation:\n"
        "    lossy_mapping: ignore\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args(policy_file=policy_file))

    assert resolved.provider_policy.default.sandbox.workspace.filesystem.allow_write == (".", "./dist")
    assert resolved.provider_policy.validation.lossy_mapping == "ignore"


def test_resolve_runtime_config_rejects_unknown_provider_policy_keys(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"provider_policy\.default\.bogus"):
        runtime_config.parse_runtime_config(
            {"provider_policy": {"default": {"bogus": True}}},
            tmp_path / "botlane.yaml",
        )


def test_resolve_runtime_config_reports_invalid_policy_enum_with_field_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"provider_policy\.default\.permissions\.mode"):
        runtime_config.parse_runtime_config(
            {"provider_policy": {"default": {"permissions": {"mode": "invalid"}}}},
            tmp_path / "botlane.yaml",
        )


def test_resolve_runtime_config_rejects_null_default_policy_override(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"provider_policy\.default must be a mapping when provided"):
        runtime_config.parse_runtime_config(
            {"provider_policy": {"default": None}},
            tmp_path / "botlane.yaml",
        )


def test_resolve_runtime_config_rejects_null_validation_override(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"provider_policy\.validation must be a mapping when provided"):
        runtime_config.parse_runtime_config(
            {"provider_policy": {"validation": None}},
            tmp_path / "botlane.yaml",
        )


def test_resolve_runtime_config_maps_legacy_provider_model_and_effort_into_provider_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider:\n"
        "  name: claude\n"
        "  claude:\n"
        "    model: claude-opus\n"
        "    effort: high\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.provider.claude.model == "claude-opus"
    assert resolved.provider.claude.effort == "high"
    assert resolved.provider_policy.default.model.default == "claude-opus"
    assert resolved.provider_policy.default.model.effort == "high"


def test_cli_model_and_effort_map_into_provider_policy_only_when_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(
        config_root,
        _runtime_args(provider="codex", model="gpt-5.5", model_effort="high"),
    )

    assert resolved.provider.codex.model == "gpt-5.5"
    assert resolved.provider.codex.model_effort == "high"
    assert resolved.provider_policy.default.model.default == "gpt-5.5"
    assert resolved.provider_policy.default.model.effort == "high"


def test_runtime_full_auto_maps_to_full_auto_sandboxed_when_policy_mode_is_not_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text("runtime:\n  full_auto: true\n", encoding="utf-8")
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.runtime.full_auto is True
    assert resolved.provider_policy.default.permissions.mode == "full_auto_sandboxed"


def test_resolve_runtime_config_maps_legacy_claude_bypass_into_provider_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider:\n"
        "  name: claude\n"
        "  claude:\n"
        "    permission_strategy: bypass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.provider.claude.permission_strategy == "bypass"
    assert resolved.provider_policy.default.permissions.mode == "full_auto_unsandboxed"
    assert resolved.provider_policy.default.permissions.allow_dangerous_bypass is True
    assert resolved.provider_policy.default.permissions.disable_dangerous_bypass is False
    assert resolved.provider_policy.default.sandbox.enabled is False
    assert resolved.provider_policy.default.sandbox.required is False
    assert resolved.provider_policy.default.sandbox.mode == "danger_full_access"


def test_explicit_policy_mode_beats_legacy_full_auto_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "runtime:\n"
        "  full_auto: true\n"
        "provider_policy:\n"
        "  default:\n"
        "    permissions:\n"
        "      mode: ask\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.provider_policy.default.permissions.mode == "ask"


def test_explicit_policy_fields_beat_legacy_claude_bypass_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider:\n"
        "  name: claude\n"
        "  claude:\n"
        "    permission_strategy: bypass\n"
        "provider_policy:\n"
        "  default:\n"
        "    permissions:\n"
        "      mode: ask\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.provider.claude.permission_strategy == "bypass"
    assert resolved.provider_policy.default.permissions.mode == "ask"
    assert resolved.provider_policy.default.permissions.allow_dangerous_bypass is False


def test_policy_validation_cli_overrides_replace_config_validation_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider_policy:\n"
        "  validation:\n"
        "    unsupported: fail\n"
        "    lossy_mapping: warn\n"
        "    unsafe_expansion: fail\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(
        config_root,
        _runtime_args(
            policy_validation_unsupported="ignore",
            policy_validation_lossy="fail",
            policy_validation_unsafe_expansion="warn",
        ),
    )

    assert resolved.provider_policy.validation.unsupported == "ignore"
    assert resolved.provider_policy.validation.lossy_mapping == "fail"
    assert resolved.provider_policy.validation.unsafe_expansion == "warn"


def test_narrow_yaml_loader_parses_provider_policy_lists_and_nulls_without_pyyaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "repo"
    config_root.mkdir()
    (config_root / "botlane.yaml").write_text(
        "provider_policy:\n"
        "  strict:\n"
        "    sandbox:\n"
        "      allowed_modes: [\"read_only\", \"workspace_write\"]\n"
        "      workspace:\n"
        "        network:\n"
        "          allowed_modes: [\"none\", \"limited\", \"full\"]\n"
        "          allowed_domains: null\n"
        "    env:\n"
        "      required_deny: [\"*TOKEN*\", \"*SECRET*\", \"*KEY*\"]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "yaml", None)
    monkeypatch.setattr(runtime_config, "user_config_dir", lambda: tmp_path / "missing-user-config")

    resolved = resolve_runtime_config(config_root, _runtime_args())

    assert resolved.provider_policy.strict is not None
    assert resolved.provider_policy.strict.sandbox.allowed_modes == ("read_only", "workspace_write")
    assert resolved.provider_policy.strict.sandbox.workspace.network.allowed_modes == ("none", "limited", "full")
    assert resolved.provider_policy.strict.sandbox.workspace.network.allowed_domains is None
