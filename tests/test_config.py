from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from bili_live_danmaku.config import ConfigStore
from bili_live_danmaku.models import AppConfig, TTSSettings


def test_default_config_uses_local_cookie_file(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    config = store.load()
    assert Path(config.cookie_file) == Path("config/cookie.txt")
    assert store.cookie_path() == tmp_path / "config" / "cookie.txt"
    assert store.data_dir == tmp_path / "data"
    assert store.path == tmp_path / "config" / "config.yaml"
    assert store.path.exists()
    assert config.version == 3


def test_tts_proxy_defaults_and_validation() -> None:
    assert TTSSettings().proxy == "http://127.0.0.1:7890"
    assert TTSSettings(proxy="").proxy == ""
    assert TTSSettings(proxy="https://proxy.example:8443").proxy == "https://proxy.example:8443"

    with pytest.raises(ValidationError):
        TTSSettings(proxy="socks5://127.0.0.1:7890")
    with pytest.raises(ValidationError):
        TTSSettings(proxy="http://")


def test_config_round_trip(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    config = AppConfig(room="123", history_lines=3)
    config.theme.panel_radius = 42
    config.tts.voices.ja = "ja-JP-KeitaNeural"
    store.save(config)
    loaded = store.load()
    assert loaded.room == "123"
    assert loaded.history_lines == 3
    assert loaded.theme.panel_radius == 42
    assert loaded.tts.voices.ja == "ja-JP-KeitaNeural"


def test_broken_config_is_replaced(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.path.write_text("{not-json", encoding="utf-8")
    loaded = store.load()
    assert loaded.room == ""
    assert store.path.with_suffix(".broken.yaml").exists()


def test_example_config_is_copied_to_local_yaml(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    source = Path(__file__).resolve().parents[1] / "config" / "config.example.yaml"
    shutil.copy2(source, tmp_path / "config" / "config.example.yaml")
    store = ConfigStore(tmp_path)
    loaded = store.load()
    assert loaded.version == 3
    assert store.path.exists()
    assert store.cookie_path() == tmp_path / "config" / "cookie.txt"


def test_v2_config_migrates_voice_map_and_preserves_comments(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.path.write_text(
        """# keep this comment
version: 2
room: "42"
tts:
  enabled: true
  voice: zh-CN-YunxiNeural
  rate: "+5%"
""",
        encoding="utf-8",
    )
    loaded = store.load()
    saved = store.path.read_text(encoding="utf-8")
    assert loaded.version == 3
    assert loaded.tts.rate == "+5%"
    assert loaded.tts.voices.zh == "zh-CN-XiaoxiaoNeural"
    assert "voice: zh-CN-YunxiNeural" not in saved
    assert "voices:" in saved
    assert "# keep this comment" in saved


def test_form_save_preserves_existing_yaml_comments(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    source = """# top comment
version: 3
room: "1"
tts:
  # voice comment
  enabled: false
  language_priority: [zh, en]
  voices:
    zh: zh-CN-XiaoxiaoNeural
"""
    store.path.write_text(source, encoding="utf-8")
    config = store.load()
    config.room = "2"
    store.save(config)
    saved = store.path.read_text(encoding="utf-8")
    assert "# top comment" in saved
    assert "# voice comment" in saved
    assert 'room: "2"' in saved


def test_legacy_appdata_is_migrated(tmp_path: Path, monkeypatch) -> None:
    legacy_base = tmp_path / "legacy"
    legacy = legacy_base / "bili-live-danmaku"
    (legacy / "history").mkdir(parents=True)
    (legacy / "history" / "123.json").write_text("[]", encoding="utf-8")
    (legacy / "cookie.txt").write_text("SESSDATA=abc; DedeUserID=1", encoding="utf-8")
    (legacy / "config.json").write_text(json.dumps({"room": "123"}), encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(legacy_base))

    store = ConfigStore(tmp_path / "project")
    loaded = store.load()
    assert loaded.version == 3
    assert loaded.room == "123"
    assert store.cookie_path().read_text(encoding="utf-8").startswith("SESSDATA=")
    assert (store.data_dir / "history" / "123.json").exists()


def test_v3_config_adds_new_tts_defaults_and_preserves_comments(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    store.path.write_text(
        """# keep me
version: 3
room: "42"
tts:
  enabled: true
""",
        encoding="utf-8",
    )
    loaded = store.load()
    saved = store.path.read_text(encoding="utf-8")
    assert loaded.tts.prefer_multilingual_voice is False
    assert loaded.tts.multilingual_voice == "en-US-AvaMultilingualNeural"
    assert "prefer_multilingual_voice: false" in saved
    assert "multilingual_voice: en-US-AvaMultilingualNeural" in saved
    assert "# keep me" in saved
