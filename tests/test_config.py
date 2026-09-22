from __future__ import annotations

from pathlib import Path

import pytest

from botpipe import Botpipe
from botpipe.config import (
    ConfigurationError,
    discover_config,
    load_config,
    validate_non_secret_settings,
)


def test_missing_default_stays_unresolved_until_requested(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.default_provider is None
    assert config.selection is None
    assert config.client_kwargs()["provider"] is None
    with pytest.raises(ConfigurationError, match="no default provider"):
        config.require_provider()


def test_profile_resolution_is_immutable_and_preserves_scope_omission(tmp_path: Path) -> None:
    (tmp_path / "botpipe.toml").write_text(
        """default_provider = "codex"
default_profile = "review"

[providers.codex]
model = "base-model"
generate_allow_commands = [["git", "status", "--short"]]

[providers.codex.options]
command = ["codex", "exec"]

[providers.codex.profiles.review]
effort = "high"
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    selection = config.require_provider()
    assert selection.name == "codex"
    assert selection.profile == "review"
    assert selection.generate_allow_commands == (("git", "status", "--short"),)
    assert selection.query_read_roots is None
    assert config.policy == {"model": "base-model", "effort": "high"}
    assert selection.provider_config() == {"command": ["codex", "exec"]}
    assert selection.provider_defaults() == {
        "profile": "review",
        "model": "base-model",
        "effort": "high",
        "generate_allow_commands": [["git", "status", "--short"]],
    }
    with pytest.raises(TypeError):
        selection.options["command"] = []  # type: ignore[index]


def test_explicit_collections_and_maps_replace_profile_values(tmp_path: Path) -> None:
    (tmp_path / "botpipe.toml").write_text(
        """default_provider = "codex"
[providers.codex]
query_read_roots = ["src"]
generate_allow_commands = [["git", "status"]]
[providers.codex.options]
command = ["wrong"]
environment = { SAFE = "1" }
""",
        encoding="utf-8",
    )
    config = load_config(
        tmp_path,
        provider_config={"command": ["codex", "exec"]},
        generate_allow_commands=(),
        query_read_roots=(),
    )
    selection = config.require_provider()
    assert selection.options == {"command": ("codex", "exec")}
    assert selection.generate_allow_commands == ()
    assert selection.query_read_roots == ()


def test_profile_instructions_reach_provider_and_per_call_overrides_do_not_mutate(tmp_path):
    from botpipe import Provider
    from botpipe.providers import FakeProvider

    (tmp_path / "botpipe.toml").write_text(
        'default_provider = "claude"\ndefault_profile = "review"\n'
        '[providers.claude]\ninstructions = "Base role"\n'
        '[providers.claude.profiles.review]\ninstructions = "Review role"\n'
    )
    selected = load_config(tmp_path).require_provider()
    assert selected.instructions == "Review role"
    assert "instructions" not in selected.provider_config()
    native = FakeProvider(["first", "second", "third", "fourth"])
    with Botpipe(tmp_path, provider=native, provider_defaults=selected.provider_defaults()) as runtime:
        provider = Provider(runtime=runtime)
        provider.generate("first")
        provider.generate("second", instructions=None)
        provider.with_config(instructions="Derived role").generate("third")
        provider.generate("fourth")
    assert [call.instructions for call in native.calls] == [
        "Review role", None, "Derived role", "Review role",
    ]


def test_non_text_profile_instructions_are_rejected(tmp_path):
    (tmp_path / "botpipe.toml").write_text(
        'default_provider = "claude"\n[providers.claude]\ninstructions = ["wrong"]\n'
    )
    with pytest.raises(ConfigurationError, match="instructions must be a string"):
        load_config(tmp_path)


def test_config_source_precedence_and_relative_environment_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "botpipe.toml").write_text('default_provider = "codex"\n')
    selected = tmp_path / "selected.json"
    selected.write_text('{"default_provider":"pi"}')
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("default_provider: claude-code\n")
    monkeypatch.setenv("BOTPIPE_CONFIG", selected.name)

    assert discover_config(tmp_path) == selected
    assert load_config(tmp_path).default_provider == "pi"
    assert load_config(tmp_path, path=explicit).default_provider == "claude-code"


def test_canonical_file_precedes_pyproject_and_unknown_keys_fail(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.botpipe]\ndefault_provider = "pi"\n', encoding="utf-8"
    )
    canonical = tmp_path / "botpipe.toml"
    canonical.write_text('default_provider = "codex"\n', encoding="utf-8")
    assert discover_config(tmp_path) == canonical
    assert load_config(tmp_path).default_provider == "codex"

    canonical.write_text("surprise = true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unknown configuration keys"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "settings",
    [
        {"api_key": "literal"},
        {"headers": {"Authorization": "Bearer literal"}},
        {"env": {"OPENAI_API_KEY": "literal"}},
        {"nested": [{"access_token": "literal"}]},
        {"endpoint": "https://user:password@example.invalid/api"},
    ],
)
def test_secret_bearing_settings_are_rejected(settings: object) -> None:
    with pytest.raises(ConfigurationError, match="environment credential"):
        validate_non_secret_settings(settings)


def test_provider_options_reject_secrets_but_allow_credential_references(
    tmp_path: Path,
) -> None:
    (tmp_path / "botpipe.toml").write_text(
        """default_provider = "codex"
[providers.codex.options]
credential_source = "workload-identity"
api_key = "must-not-persist"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="provider options.api_key"):
        load_config(tmp_path)

    config = load_config(
        tmp_path,
        provider_config={"credential_source": "workload-identity"},
    )
    assert config.require_provider().options == {
        "credential_source": "workload-identity"
    }


def test_runtime_rejects_serializable_credentials_before_opening_journal(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigurationError, match="environment credential"):
        Botpipe(
            tmp_path,
            provider="codex",
            provider_config={"env": {"SERVICE_TOKEN": "literal"}},
        )
    assert not (tmp_path / ".botpipe-v2" / "state.sqlite3").exists()


def test_injected_live_adapter_may_own_private_credentials(tmp_path: Path) -> None:
    class LiveAdapter:
        name = "injected"

        def __init__(self) -> None:
            self.api_key = "kept outside serializable configuration"

        def run(self, request):  # pragma: no cover - construction is the contract
            raise AssertionError("not dispatched")

    with Botpipe(tmp_path, provider=LiveAdapter()) as client:
        assert client.provider_name == "injected"
