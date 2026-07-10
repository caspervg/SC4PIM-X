import tomllib

from sc4pimx import config


def test_startup_dialog_defaults_to_visible_when_key_is_missing(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[Paths]\nUserPluginsRoot = 'C:\\Plugins'\n", encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: path)

    assert config.load_startup()["ShowFileConfigurationAtStartup"] is True


def test_local_config_requires_at_least_one_valid_toml_value(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "user_config_path", lambda: path)

    assert not config.local_config_has_values()
    path.write_text("", encoding="utf-8")
    assert not config.local_config_has_values()
    path.write_text("not valid toml =", encoding="utf-8")
    assert not config.local_config_has_values()
    path.write_text("[Startup]\nShowFileConfigurationAtStartup = false\n", encoding="utf-8")
    assert config.local_config_has_values()


def test_save_startup_preference_preserves_existing_config(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[Paths]\nUserPluginsRoot = 'C:\\Plugins'\n", encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: path)
    monkeypatch.setattr(config, "ensure_user_data_dir", lambda: tmp_path)

    config.save_startup({"ShowFileConfigurationAtStartup": False})

    with open(path, "rb") as fh:
        saved = tomllib.load(fh)
    assert saved["Paths"]["UserPluginsRoot"] == "C:\\Plugins"
    assert saved["Startup"]["ShowFileConfigurationAtStartup"] is False


def test_first_use_forces_dialog_even_if_fallback_preference_is_false(monkeypatch):
    monkeypatch.setattr(config, "local_config_has_values", lambda: False)
    monkeypatch.setattr(
        config,
        "load_startup",
        lambda: {"ShowFileConfigurationAtStartup": False},
    )

    assert config.should_show_file_configuration()


def test_saved_opt_out_skips_dialog(monkeypatch):
    monkeypatch.setattr(config, "local_config_has_values", lambda: True)
    monkeypatch.setattr(
        config,
        "load_startup",
        lambda: {"ShowFileConfigurationAtStartup": False},
    )

    assert not config.should_show_file_configuration()
