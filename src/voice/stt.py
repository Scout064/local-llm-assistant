from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import structlog

from src.config import settings

logger = structlog.get_logger()

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            settings.voice.stt_model,
            device=settings.voice.stt_device,
            compute_type="int8" if "cpu" in settings.voice.stt_device else "float16",
        )
    return _whisper_model


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe audio array. Runs synchronously — call via asyncio.to_thread()."""
    model = _get_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio, sample_rate)
        segments, _info = model.transcribe(f.name, beam_size=5)
        text = " ".join(seg.text for seg in segments).strip()
        Path(f.name).unlink(missing_ok=True)
        return text


def transcribe_file(file_path: str) -> str:
    """Transcribe a file on disk. Runs synchronously — call via asyncio.to_thread()."""
    model = _get_model()
    segments, _info = model.transcribe(file_path, beam_size=5)
    return " ".join(seg.text for seg in segments).strip()