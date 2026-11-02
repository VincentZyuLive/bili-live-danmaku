from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class MessageKind(StrEnum):
    TEXT = "text"
    GIFT = "gift"
    ENTRY = "entry"
    LIKE = "like"
    PAID = "paid"
    MEMBERSHIP = "membership"


class UserType(StrEnum):
    NORMAL = "normal"
    MEMBER = "member"
    MODERATOR = "moderator"
    OWNER = "owner"


class Fragment(BaseModel):
    type: Literal["text", "emote"] = "text"
    text: str = ""
    url: str | None = None
    px: int = 0
    verb: bool = False


class ChatMessage(BaseModel):
    id: str
    kind: MessageKind
    user_type: UserType = UserType.NORMAL
    user: str = ""
    user_color: str | None = None
    avatar_url: str | None = None
    parts: list[Fragment] = Field(default_factory=list)
    amount: str = ""
    amount_value: int = 0
    count: int = 1
    timestamp_ms: int = 0
    merge_key: str = ""
    dwell_ms: int = 0


class ConnectionStatus(BaseModel):
    state: Literal["idle", "connecting", "connected", "reconnecting", "error"] = "idle"
    message: str = "尚未连接"
    room_id: int | None = None
    real_room_id: int | None = None
    cookie_present: bool = False
    message_rate: float = 0.0
    last_error: str | None = None


class FontSettings(BaseModel):
    family: str = "LXGW WenKai Mono"
    size: int = Field(default=28, ge=12, le=72)
    url: str | None = None


class ThemeSettings(BaseModel):
    width: int = Field(default=480, ge=240, le=1920)
    height: int = Field(default=1080, ge=240, le=1920)
    font: FontSettings = Field(default_factory=FontSettings)
    panel_background: str = "#0b0d12"
    panel_opacity: float = Field(default=0.58, ge=0, le=1)
    panel_radius: int = Field(default=28, ge=0, le=80)
    panel_border: str = "#ffffff"
    panel_border_opacity: float = Field(default=0.12, ge=0, le=1)
    panel_padding: int = Field(default=18, ge=0, le=64)
    row_gap: int = Field(default=8, ge=0, le=32)
    text_color: str = "#f4f6fb"
    muted_color: str = "#aeb5c2"
    accent_color: str = "#ffd66b"
    show_status: bool = True
    max_messages: int = Field(default=80, ge=5, le=500)


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=6161, ge=1, le=65535)
    open_browser: bool = True


class StorageSettings(BaseModel):
    data_dir: str = "data"


class ReconnectSettings(BaseModel):
    base_seconds: float = Field(default=1.0, ge=0.1, le=60)
    max_seconds: float = Field(default=30.0, ge=1, le=300)


TTS_LANGUAGE_CODES = ("zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "it")
TTSVoiceId = Annotated[str, Field(min_length=1)]


class TTSVoices(BaseModel):
    zh: TTSVoiceId = "zh-CN-XiaoxiaoNeural"
    en: TTSVoiceId = "en-US-AvaMultilingualNeural"
    ja: TTSVoiceId = "ja-JP-NanamiNeural"
    ko: TTSVoiceId = "ko-KR-SunHiNeural"
    es: TTSVoiceId = "es-ES-XimenaNeural"
    fr: TTSVoiceId = "fr-FR-VivienneMultilingualNeural"
    de: TTSVoiceId = "de-DE-SeraphinaMultilingualNeural"
    pt: TTSVoiceId = "pt-BR-ThalitaMultilingualNeural"
    ru: TTSVoiceId = "ru-RU-SvetlanaNeural"
    it: TTSVoiceId = "it-IT-ElsaNeural"

    def get(self, language: str) -> str:
        return cast(str, getattr(self, language))


class TTSSettings(BaseModel):
    enabled: bool = False
    proxy: str = "http://127.0.0.1:7890"
    prefer_multilingual_voice: bool = False
    multilingual_voice: str = "en-US-AvaMultilingualNeural"
    language_priority: list[str] = Field(default_factory=lambda: list(TTS_LANGUAGE_CODES))
    voices: TTSVoices = Field(default_factory=TTSVoices)
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    read_kinds: list[MessageKind] = Field(default_factory=lambda: list(MessageKind))
    include_username: bool = True
    max_chars: int = Field(default=180, ge=1, le=1000)
    queue_size: int = Field(default=32, ge=1, le=500)
    min_interval_ms: int = Field(default=300, ge=0, le=10_000)

    @field_validator("proxy")
    @classmethod
    def validate_proxy(cls, value: str) -> str:
        proxy = value.strip()
        if not proxy:
            return ""
        parsed = urlsplit(proxy)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("tts.proxy 必须是 http:// 或 https:// URL，留空表示直连")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("tts.proxy 端口无效") from exc
        return proxy

    @field_validator("language_priority")
    @classmethod
    def validate_language_priority(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("language_priority 不能为空")
        unknown = [language for language in value if language not in TTS_LANGUAGE_CODES]
        if unknown:
            raise ValueError(f"不支持的语言代码：{', '.join(unknown)}")
        if len(value) != len(set(value)):
            raise ValueError("language_priority 不能包含重复语言")
        return value


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class AppConfig(BaseModel):
    version: int = 3
    room: str = ""
    cookie_file: str = "config/cookie.txt"
    history_lines: int = Field(default=60, ge=0, le=2000)
    entry_merge_seconds: float = Field(default=5.0, ge=0, le=60)
    gift_merge_seconds: float = Field(default=5.0, ge=0, le=60)
    auto_connect: bool = True
    server: ServerSettings = Field(default_factory=ServerSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    reconnect: ReconnectSettings = Field(default_factory=ReconnectSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    theme: ThemeSettings = Field(default_factory=ThemeSettings)


class EventEnvelope(BaseModel):
    type: Literal["event", "history", "status", "config", "config_error", "snapshot", "clear"]
    sequence: int
    server_time_ms: int
    payload: object
