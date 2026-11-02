from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from array import array
from collections import deque
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langdetect import DetectorFactory, LangDetectException, detect_langs

from .models import ChatMessage, MessageKind, TTSSettings

DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

_KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
_HANGUL_RE = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u052f]")
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")
_SPEECH_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
_SUPPORTED_LATIN_LANGUAGES = {"en", "es", "fr", "de", "pt", "it"}
DEFAULT_LANGUAGE_PRIORITY = ("zh", "en", "ja", "ko", "es", "fr", "de", "pt", "ru", "it")

_MIN_CONFIDENCE = 0.25
_TIE_MARGIN = 0.12


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    voice: str
    language: str


@dataclass(frozen=True)
class SpeechRequest:
    message_id: str
    segments: tuple[SpeechSegment, ...]


def _amount_text(amount: str) -> str:
    cleaned = amount.rsplit("·", 1)[-1].replace("CN¥", "").replace("¥", "").strip()
    return f"，金额 {cleaned} 元" if cleaned else ""


def _normalized_detected_language(value: str) -> str:
    language = value.lower().split("-", 1)[0]
    return "zh" if language == "zh" else language


def detect_language(
    text: str, language_priority: Sequence[str], *, short_text: bool = False
) -> str:
    if not language_priority:
        raise ValueError("language_priority 不能为空")
    enabled = set(language_priority)
    stripped = text.strip()
    if not stripped:
        return language_priority[0]

    script_language: str | None = None
    if _KANA_RE.search(stripped):
        script_language = "ja"
    elif _HANGUL_RE.search(stripped):
        script_language = "ko"
    elif _CYRILLIC_RE.search(stripped):
        script_language = "ru"
    elif _HAN_RE.search(stripped):
        script_language = "zh"
    if script_language is not None:
        return script_language if script_language in enabled else language_priority[0]

    if not _LATIN_RE.search(stripped):
        return language_priority[0]
    latin_letters = len(_LATIN_RE.findall(stripped))
    latin_words = re.findall(r"[A-Za-zÀ-ɏ]+", stripped)
    if short_text or (latin_letters <= 24 and len(latin_words) <= 3):
        for language in language_priority:
            if language in _SUPPORTED_LATIN_LANGUAGES:
                return language
        return language_priority[0]

    try:
        probabilities = detect_langs(stripped)
    except LangDetectException:
        return language_priority[0]

    candidates = [
        (_normalized_detected_language(item.lang), float(item.prob))
        for item in probabilities
        if _normalized_detected_language(item.lang) in enabled
    ]
    candidates = [
        (language, probability)
        for language, probability in candidates
        if language in _SUPPORTED_LATIN_LANGUAGES
    ]
    if not candidates:
        return language_priority[0]

    candidates.sort(key=lambda item: item[1], reverse=True)
    best_language, best_probability = candidates[0]
    if best_probability < _MIN_CONFIDENCE:
        return language_priority[0]
    if len(candidates) > 1 and best_probability - candidates[1][1] < _TIE_MARGIN:
        close_languages = {
            language
            for language, probability in candidates
            if probability >= best_probability - _TIE_MARGIN
        }
        for language in language_priority:
            if language in close_languages:
                return language
    return best_language


def _voice_for_language(language: str, settings: TTSSettings) -> str:
    return settings.voices.get(language)


def _body_text(message: ChatMessage) -> str:
    text_parts = [
        fragment.text.strip()
        for fragment in message.parts
        if fragment.text.strip()
    ]
    return " ".join(text_parts).strip()


def _spoken_body(message: ChatMessage, body: str, *, include_name: bool) -> str:
    if message.kind is MessageKind.TEXT:
        phrase = f"说：{body}" if include_name else body
    elif message.kind is MessageKind.GIFT:
        phrase = body if body.startswith("投喂") else f"送出了{body}"
    elif message.kind is MessageKind.ENTRY:
        phrase = body if "进入" in body else "进入了直播间"
    elif message.kind is MessageKind.LIKE:
        phrase = body if "点赞" in body else "为主播点赞了"
    elif message.kind is MessageKind.PAID:
        phrase = f"发送了一条醒目留言：{body}{_amount_text(message.amount)}"
    elif message.kind is MessageKind.MEMBERSHIP:
        phrase = body if body else "开通了舰长"
        phrase += _amount_text(message.amount)
    else:
        phrase = f"：{body}" if include_name and body else body
    if message.count > 1:
        phrase += f"，共 {message.count} 次"
    return phrase


def _split_speech_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SPEECH_SPLIT_RE.split(text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _append_segment(segments: list[SpeechSegment], text: str, voice: str, language: str) -> None:
    if not text:
        return
    if segments and segments[-1].voice == voice:
        previous = segments[-1]
        segments[-1] = SpeechSegment(
            text=previous.text + text,
            voice=previous.voice,
            language=previous.language,
        )
        return
    segments.append(SpeechSegment(text=text, voice=voice, language=language))


def _truncate_segments(segments: list[SpeechSegment], max_chars: int) -> list[SpeechSegment]:
    remaining = max_chars
    truncated: list[SpeechSegment] = []
    for segment in segments:
        if remaining <= 0:
            break
        text = segment.text[:remaining].strip()
        if text:
            truncated.append(
                SpeechSegment(text=text, voice=segment.voice, language=segment.language)
            )
            remaining -= len(text)
    return truncated


def message_to_speech_segments(message: ChatMessage, settings: TTSSettings) -> list[SpeechSegment]:
    body = _body_text(message)
    if not body and not message.amount:
        return []

    segments: list[SpeechSegment] = []
    username = message.user.strip()
    include_name = settings.include_username and bool(username)
    if include_name:
        language = detect_language(username, settings.language_priority, short_text=True)
        _append_segment(segments, username, _voice_for_language(language, settings), language)

    phrase = _spoken_body(message, body, include_name=include_name)
    for sentence in _split_speech_sentences(phrase):
        language = detect_language(sentence, settings.language_priority)
        _append_segment(segments, sentence, _voice_for_language(language, settings), language)

    return _truncate_segments(segments, settings.max_chars)


def message_to_speech(
    message: ChatMessage,
    include_username: bool,
    max_chars: int,
    language_priority: Sequence[str] | None = None,
) -> str | None:
    settings = TTSSettings(
        enabled=True,
        include_username=include_username,
        max_chars=max_chars,
        language_priority=list(language_priority or DEFAULT_LANGUAGE_PRIORITY),
    )
    text = "".join(segment.text for segment in message_to_speech_segments(message, settings))
    return text or None


def _pcm_chunks(decoded: Any) -> Generator[bytes, int, None]:
    raw = decoded.samples.tobytes()
    bytes_per_frame = max(1, decoded.nchannels * decoded.sample_width)
    offset = 0
    frame_count = yield b""
    while offset < len(raw):
        chunk_size = max(1, frame_count) * bytes_per_frame
        chunk = raw[offset : offset + chunk_size]
        offset += len(chunk)
        frame_count = yield chunk


@dataclass(frozen=True)
class _CombinedAudio:
    samples: Any
    sample_rate: int
    nchannels: int
    sample_width: int


def _play_audio_files(paths: Sequence[Path]) -> None:
    import miniaudio

    if not paths:
        return

    decoded_files: list[tuple[Path, Any]] = []
    for path in paths:
        try:
            decoded_files.append((path, miniaudio.decode_file(str(path))))
        except Exception:
            logger.exception("TTS 音频解码失败：%s", path)
    if not decoded_files:
        return

    first = decoded_files[0][1]
    samples = array(first.samples.typecode)
    samples.extend(first.samples)
    for path, decoded in decoded_files[1:]:
        if (
            decoded.sample_rate != first.sample_rate
            or decoded.nchannels != first.nchannels
            or decoded.sample_width != first.sample_width
        ):
            try:
                decoded = miniaudio.decode_file(
                    str(path),
                    nchannels=first.nchannels,
                    sample_rate=first.sample_rate,
                )
            except Exception:
                logger.exception("TTS 音频格式转换失败：%s", path)
                continue
        samples.extend(decoded.samples)

    if not samples:
        return
    combined = _CombinedAudio(
        samples=samples,
        sample_rate=first.sample_rate,
        nchannels=first.nchannels,
        sample_width=first.sample_width,
    )
    device = miniaudio.PlaybackDevice()
    try:
        stream = _pcm_chunks(combined)
        next(stream)
        device.start(stream)
        duration = len(combined.samples) / max(1, combined.sample_rate * combined.nchannels)
        time.sleep(duration + 0.08)
    finally:
        device.close()


class TTSService:
    def __init__(self, settings: TTSSettings, cache_dir: Path) -> None:
        self.settings = settings
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.queue: asyncio.Queue[SpeechRequest] = asyncio.Queue(maxsize=settings.queue_size)
        self._task: asyncio.Task[None] | None = None
        self._seen: deque[str] = deque(maxlen=512)
        self._seen_set: set[str] = set()

    async def start(self) -> None:
        if not self.settings.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="edge-tts")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def reconfigure(self, settings: TTSSettings) -> None:
        pending: list[SpeechRequest] = []
        if settings.queue_size != self.queue.maxsize:
            while not self.queue.empty():
                pending.append(self.queue.get_nowait())
            pending = pending[-settings.queue_size :]
            self.queue = asyncio.Queue(maxsize=settings.queue_size)
            for request in pending:
                self.queue.put_nowait(request)
        self.settings = settings
        if not settings.enabled:
            await self.stop()
            while not self.queue.empty():
                self.queue.get_nowait()
            return
        await self.start()

    async def enqueue(self, message: ChatMessage) -> None:
        if not self.settings.enabled or message.kind not in self.settings.read_kinds:
            return
        if message.id in self._seen_set:
            return
        segments = message_to_speech_segments(message, self.settings)
        if not segments:
            return
        self._remember(message.id)
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(SpeechRequest(message_id=message.id, segments=tuple(segments)))

    def _remember(self, message_id: str) -> None:
        if len(self._seen) == self._seen.maxlen:
            oldest = self._seen[0]
            self._seen_set.discard(oldest)
        self._seen.append(message_id)
        self._seen_set.add(message_id)

    async def speak_test(self, text: str = "弹幕朗读测试成功", language: str | None = None) -> None:
        if language is not None and language not in self.settings.language_priority:
            raise ValueError(f"语言未在 language_priority 中启用：{language}")
        selected = language or detect_language(text, self.settings.language_priority)
        voice = _voice_for_language(selected, self.settings)
        await self._speak(text, voice)

    def _should_use_multilingual_voice(self, request: SpeechRequest) -> bool:
        return bool(
            self.settings.prefer_multilingual_voice
            and self.settings.multilingual_voice.strip()
            and len({segment.voice for segment in request.segments}) > 1
        )

    async def _synthesize_to_file(self, text: str, voice: str) -> Path:
        import edge_tts

        audio_path = self.cache_dir / f"tts-{uuid.uuid4().hex}.mp3"
        try:
            communicate = edge_tts.Communicate(
                text,
                voice,
                rate=self.settings.rate,
                volume=self.settings.volume,
                pitch=self.settings.pitch,
                proxy=self.settings.proxy or None,
            )
            await communicate.save(str(audio_path))
            return audio_path
        except BaseException:
            try:
                audio_path.unlink()
            except FileNotFoundError:
                pass
            raise

    async def _prepare_segment_files(
        self, segments: Sequence[SpeechSegment]
    ) -> list[Path]:
        semaphore = asyncio.Semaphore(2)

        async def prepare(segment: SpeechSegment) -> Path:
            async with semaphore:
                return await self._synthesize_to_file(segment.text, segment.voice)

        results = await asyncio.gather(
            *(prepare(segment) for segment in segments), return_exceptions=True
        )
        paths: list[Path] = []
        for segment, result in zip(segments, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "Edge TTS 片段合成失败：%s (%s)",
                    segment.language,
                    result,
                )
                continue
            paths.append(result)
        return paths

    async def _play_files(self, paths: Sequence[Path]) -> None:
        await asyncio.to_thread(_play_audio_files, paths)

    async def _process_request(self, request: SpeechRequest) -> None:
        if self._should_use_multilingual_voice(request):
            text = "".join(segment.text for segment in request.segments)
            try:
                audio_path = await self._synthesize_to_file(
                    text, self.settings.multilingual_voice
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("多语种 TTS 合成失败，回退到多段音色")
            else:
                try:
                    await self._play_files([audio_path])
                finally:
                    try:
                        audio_path.unlink()
                    except FileNotFoundError:
                        pass
                return

        paths = await self._prepare_segment_files(request.segments)
        try:
            await self._play_files(paths)
        finally:
            for path in paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    async def _run(self) -> None:
        while True:
            request = await self.queue.get()
            try:
                await self._process_request(request)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Edge TTS 朗读失败")
            finally:
                self.queue.task_done()
            if self.settings.min_interval_ms:
                await asyncio.sleep(self.settings.min_interval_ms / 1000)

    async def _speak(self, text: str, voice: str) -> None:
        audio_path = await self._synthesize_to_file(text, voice)
        try:
            await self._play_files([audio_path])
        finally:
            try:
                audio_path.unlink()
            except FileNotFoundError:
                pass
