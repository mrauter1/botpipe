from __future__ import annotations

import pytest

from botpipe.config import ConfigError, discover_config, load_config


def test_discovers_canonical_toml_and_merges_explicit_codex_overrides(tmp_path):
    path = tmp_path / "botpipe.toml"
    path.write_text('[codex]\nmodel = "configured"\nnetwork = false\n')

    assert discover_config(tmp_path) == path
    config = load_config(tmp_path, provider_config={"effort": "high"})
    assert config.provider_config == {
        "model": "configured",
        "network": False,
        "effort": "high",
    }


@pytest.mark.parametrize("key", ["provider", "provider_config", "codex_path"])
def test_file_configuration_rejects_removed_provider_aliases(tmp_path, key):
    value = '"codex"' if key != "provider_config" else '{}'
    (tmp_path / "botpipe.toml").write_text(f"{key} = {value}\n")

    with pytest.raises(ConfigError, match="unknown configuration keys"):
        load_config(tmp_path)


@pytest.mark.parametrize("name", [".botpipe.toml", "botpipe.json"])
def test_discovery_ignores_removed_configuration_formats(tmp_path, name):
    (tmp_path / name).write_text("{}")

    assert discover_config(tmp_path) is None


def test_explicit_configuration_must_be_toml(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")

    with pytest.raises(ConfigError, match="must be a TOML file"):
        load_config(tmp_path, path=path)


def test_environment_selects_an_explicit_toml_file(tmp_path, monkeypatch):
    path = tmp_path / "selected.toml"
    path.write_text('[codex]\neffort = "high"\n')
    monkeypatch.setenv("BOTPIPE_CONFIG", str(path))

    assert discover_config(tmp_path) == path
    assert load_config(tmp_path).provider_config["effort"] == "high"
