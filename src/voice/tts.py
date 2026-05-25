from __future__ import annotations

import asyncio
import io
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
import structlog

from src.config import settings

logger = structlog.get_logger()

_tts_backend = None
_playback_queue: queue.Queue = queue.Queue()
_stop_event = threading.Event()


def _get_kokoro():
    from kokoro import KModel, KPipeline
    model = KModel().to("cpu")
    pipeline = KPipeline(model_code="a", model=model)
    return pipeline


def _get_edge_tts():
    import edge_tts
    return edge_tts


def synthesize(text: str) -> np.ndarray:
    """Synthesize speech from text. Runs synchronously — call via asyncio.to_thread()."""
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

    communicate = edge_tts.Communicate(text, settings.voice.tts_voice)
    with io.BytesIO() as buf:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        data, sr = sf.read(buf)
        return data


def play_audio(audio: np.ndarray, sample_rate: int = 24000):
    sd.play(audio, samplerate=sample_rate, device=settings.voice.output_device)
    sd.wait()


def stop_playback():
    sd.stop()


def synthesize_and_queue(text: str):
    try:
        audio = synthesize(text)
        if len(audio) > 0:
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


_playback_thread = threading.Thread(target=_playback_worker, daemon=True)
_playback_thread.start()


def split_into_sentences(text: str) -> list[str]:
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ".!?":
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return [s for s in sentences if s]


async def speak_streaming(text_stream, broadcast_fn=None):
    """Synthesize and play text incrementally, splitting on sentence boundaries.
    broadcast_fn is an async callable that takes a status state string.
    """
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