from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

import bili_live_danmaku.app as app_module
from bili_live_danmaku.app import Runtime, create_app, demo_messages
from bili_live_danmaku.config import ConfigStore
from bili_live_danmaku.tts import TTSPlaybackError


async def test_runtime_stop_has_timeout(tmp_path: Path, monkeypatch) -> None:
    runtime = Runtime(ConfigStore(tmp_path), demo=True)

    async def never_finishes() -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(runtime.tts, "stop", never_finishes)
    monkeypatch.setattr(app_module, "SHUTDOWN_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    await runtime.stop()
    assert time.monotonic() - started < 1.0


def test_api_and_pages_smoke(tmp_path: Path) -> None:
    runtime = Runtime(ConfigStore(tmp_path), demo=True)
    app = create_app(runtime)
    with TestClient(app) as client:
        assert client.get("/admin").status_code == 200
        assert client.get("/overlay").status_code == 200
        admin_page = client.get("/admin").text
        assert "Bili Live Danmaku" in admin_page
        assert 'id="ttsProxy"' in admin_page

        config = client.get("/api/config").json()
        config["auto_connect"] = False
        config["history_lines"] = 12
        response = client.put("/api/config", json=config)
        assert response.status_code == 200
        assert response.json()["history_lines"] == 12

        response = client.post("/api/cookie", json={"cookie": "SESSDATA=abc; DedeUserID=1"})
        assert response.status_code == 200
        cookie_text = (tmp_path / "config" / "cookie.txt").read_text(encoding="utf-8")
        assert cookie_text.startswith("SESSDATA=")

        response = client.post(
            "/api/fonts", files={"file": ("demo.ttf", b"not-a-real-font", "font/ttf")}
        )
        assert response.status_code == 200
        assert response.json()["url"].startswith("/fonts/")

        with client.websocket_connect("/ws") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"
            assert "config" in snapshot["payload"]


async def test_tts_voice_cache_is_scoped_by_proxy(monkeypatch) -> None:
    import edge_tts

    calls: list[str | None] = []

    async def fake_list_voices(*, proxy: str | None = None) -> list[dict[str, str]]:
        calls.append(proxy)
        return [
            {
                "ShortName": "zh-CN-XiaoxiaoNeural",
                "Locale": "zh-CN",
                "Gender": "Female",
                "FriendlyName": "Xiaoxiao",
            }
        ]

    monkeypatch.setattr(edge_tts, "list_voices", fake_list_voices)
    app_module._TTS_VOICE_CACHE.clear()

    await app_module._list_tts_voices("http://127.0.0.1:7890")
    await app_module._list_tts_voices("http://127.0.0.1:7890")
    await app_module._list_tts_voices("")

    assert calls == ["http://127.0.0.1:7890", None]


def test_tts_test_network_error_returns_502(tmp_path: Path, monkeypatch) -> None:
    runtime = Runtime(ConfigStore(tmp_path), demo=True)
    runtime.config.tts.enabled = True

    async def fail_test(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("speech service timed out")

    monkeypatch.setattr(runtime.tts, "speak_test", fail_test)
    app = create_app(runtime)
    with TestClient(app) as client:
        response = client.post("/api/tts/test", json={"text": "测试", "language": "zh"})
        assert response.status_code == 502
        assert "tts.proxy" in response.json()["detail"]


def test_status_never_returns_cookie_value(tmp_path: Path) -> None:
    runtime = Runtime(ConfigStore(tmp_path), cookie_override="SESSDATA=top-secret; DedeUserID=1")
    app = create_app(runtime)
    with TestClient(app) as client:
        text = client.get("/api/status").text
        assert "top-secret" not in text
        assert client.get("/api/status").json()["cookie_present"] is True


def test_demo_messages_include_local_avatars_and_varied_kinds() -> None:
    messages = demo_messages()
    assert len(messages) == 10
    assert all(
        message.avatar_url and message.avatar_url.startswith("/static/avatars/")
        for message in messages
    )
    assert len({message.kind for message in messages}) >= 5


def test_tts_playback_error_returns_503(tmp_path: Path, monkeypatch) -> None:
    runtime = Runtime(ConfigStore(tmp_path), demo=True)
    runtime.config.tts.enabled = True

    async def fail_playback(*_args: object, **_kwargs: object) -> None:
        raise TTSPlaybackError("audio device unavailable")

    monkeypatch.setattr(runtime.tts, "speak_test", fail_playback)
    app = create_app(runtime)
    with TestClient(app) as client:
        response = client.post("/api/tts/test", json={"text": "测试", "language": "zh"})
        assert response.status_code == 503
        assert "PipeWire/PulseAudio" in response.json()["detail"]


def test_config_document_api_validation_save_and_conflict(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "config" / "config.example.yaml",
        tmp_path / "config" / "config.example.yaml",
    )
    runtime = Runtime(ConfigStore(tmp_path), demo=True)
    app = create_app(runtime)
    with TestClient(app) as client:
        document = client.get("/api/config/document").json()
        assert document["config"]["version"] == 3
        assert "推荐音色" in document["example_yaml"]
        original_revision = document["revision"]

        invalid = client.post("/api/config/validate", json={"yaml": "version: [bad"})
        assert invalid.status_code == 422

        rendered = client.post(
            "/api/config/render", json={"config": document["config"]}
        )
        assert rendered.status_code == 200
        assert "language_priority:" in rendered.json()["yaml"]

        config = document["config"]
        config["room"] = "999"
        config["tts"]["voices"]["ja"] = "ja-JP-KeitaNeural"
        saved = client.put(
            "/api/config/document",
            json={"config": config, "base_revision": original_revision},
        )
        assert saved.status_code == 200
        assert saved.json()["config"]["room"] == "999"
        assert runtime.tts.settings.voices.ja == "ja-JP-KeitaNeural"

        stale = client.put(
            "/api/config/document",
            json={"config": config, "base_revision": original_revision},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["document"]["revision"] == saved.json()["revision"]

        yaml_save = client.put(
            "/api/config/document/yaml",
            json={
                "yaml": "version: 3\nroom: \'777\'\n",
                "base_revision": saved.json()["revision"],
            },
        )
        assert yaml_save.status_code == 200
        assert yaml_save.json()["config"]["room"] == "777"


def test_config_file_watcher_reloads_external_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "CONFIG_WATCH_INTERVAL_SECONDS", 0.02)
    store = ConfigStore(tmp_path)
    runtime = Runtime(store, demo=True)
    app = create_app(runtime)
    with TestClient(app) as client:
        store.path.write_text("version: 3\nroom: \'4321\'\n", encoding="utf-8")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            config = client.get("/api/config").json()
            if config["room"] == "4321":
                break
            time.sleep(0.03)
        assert client.get("/api/config").json()["room"] == "4321"
        assert runtime.config.room == "4321"
