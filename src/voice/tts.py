from __future__ import annotations

import asyncio
import io
import queue
import re
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import structlog

from src.config import settings

logger = structlog.get_logger()

_tts_backend = None
_playback_queue: queue.Queue = queue.Queue()
_stop_event = threading.Event()
_playback_thread: threading.Thread | None = None
_playback_lock = threading.Lock()


def _ensure_playback_thread():
    global _playback_thread
    with _playback_lock:
        if _playback_thread is None or not _playback_thread.is_alive():
            _playback_thread = threading.Thread(target=_playback_worker, daemon=True)
            _playback_thread.start()


def _get_kokoro():
    from kokoro import KModel, KPipeline
    model = KModel().to("cpu")
    pipeline = KPipeline(model_code="a", model=model)
    return pipeline


def synthesize(text: str) -> np.ndarray:
    if settings.voice.tts_backend == "kokoro":
        return _synthesize_kokoro(text)
    else:
        return asyncio.run(_synthesize_edge(text))


def _synthesize_kokoro(text: str) -> np.ndarray:
    pipeline = _get_kokoro()
    audio_chunks = []
    for _, _, audio in pipeline(text, voice=settings.voice.tts_voice):
        if isinstance(audio, np.ndarray):
            audio_chunks.append(audio)
        else:
            audio_chunks.append(np.array(audio))
    if audio_chunks:
        return np.concatenate(audio_chunks)
    return np.array([], dtype=np.float32)


async def _synthesize_edge(text: str) -> np.ndarray:
    import edge_tts
    from pydub import AudioSegment

    communicate = edge_tts.Communicate(text, settings.voice.tts_voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)
    audio = AudioSegment.from_mp3(buf)
    audio = audio.set_frame_rate(24000).set_channels(1)
    return np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0


def play_audio(audio: np.ndarray, sample_rate: int = 24000):
    sd.play(audio, samplerate=sample_rate, device=settings.voice.output_device)
    sd.wait()


def stop_playback():
    sd.stop()


def synthesize_and_queue(text: str):
    try:
        audio = synthesize(text)
        if len(audio) > 0:
            _ensure_playback_thread()
            _playback_queue.put(audio)
    except Exception as e:
        logger.error("tts_synthesis_error", error=str(e))


def _playback_worker():
    while not _stop_event.is_set():
        try:
            audio = _playback_queue.get(timeout=0.5)
            play_audio(audio)
            _playback_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error("tts_playback_error", error=str(e))


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def split_into_sentences(text: str) -> list[str]:
    sentences = _SENTENCE_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


async def speak_streaming(text_stream, broadcast_fn=None):
    buffer = ""
    for chunk in text_stream:
        buffer += chunk
        sentences = split_into_sentences(buffer)
        if len(sentences) > 1:
            complete = sentences[:-1]
            buffer = sentences[-1]
            for sentence in complete:
                await asyncio.to_thread(synthesize_and_queue, sentence)
                if broadcast_fn:
                    await broadcast_fn("SPEAKING")

    if buffer.strip():
        await asyncio.to_thread(synthesize_and_queue, buffer.strip())
        if broadcast_fn:
            await broadcast_fn("SPEAKING")

    _playback_queue.join()
    if broadcast_fn:
        await broadcast_fn("IDLE")