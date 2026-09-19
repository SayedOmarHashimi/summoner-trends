import pytest

from extraction.config import ConfigError, load_settings, split_riot_id


def test_split_riot_id():
    assert split_riot_id("TrendTester#NA1") == ("TrendTester", "NA1")


def test_split_riot_id_trims_whitespace():
    assert split_riot_id("  TrendTester # NA1 ") == ("TrendTester", "NA1")


@pytest.mark.parametrize("value", ["TrendTester", "#NA1", "TrendTester#", ""])
def test_split_riot_id_rejects_malformed_input(value):
    with pytest.raises(ConfigError):
        split_riot_id(value)


def _write_env(tmp_path, body):
    env = tmp_path / ".env"
    env.write_text(body)
    return env


def test_load_settings_reads_the_env_file(tmp_path, monkeypatch):
    for key in ("RIOT_API_KEY", "RIOT_REGION", "RIOT_ROUTING", "RIOT_ID"):
        monkeypatch.delenv(key, raising=False)
    env = _write_env(
        tmp_path,
        "RIOT_API_KEY=RGAPI-real-key\nRIOT_REGION=euw1\nRIOT_ROUTING=europe\n"
        "RIOT_ID=Someone#EUW\n",
    )
    settings = load_settings(env)
    assert settings.api_key == "RGAPI-real-key"
    assert settings.platform_host == "https://euw1.api.riotgames.com"
    assert settings.regional_host == "https://europe.api.riotgames.com"
    assert settings.riot_id == "Someone#EUW"


def test_missing_api_key_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="RIOT_API_KEY is not set"):
        load_settings(_write_env(tmp_path, "RIOT_REGION=na1\n"))


def test_placeholder_api_key_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-00000000-0000-0000-0000-000000000000")
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings(_write_env(tmp_path, ""))


def test_invalid_routing_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-real-key")
    monkeypatch.setenv("RIOT_ROUTING", "na1")  # a platform, not a routing value
    with pytest.raises(ConfigError, match="RIOT_ROUTING"):
        load_settings(_write_env(tmp_path, ""))
