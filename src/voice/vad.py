from __future__ import annotations

import numpy as np
import structlog
import torch

from src.config import settings

logger = structlog.get_logger()

_vad_model = None


def _load_vad_model():
    global _vad_model
    if _vad_model is None:
        _vad_model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
    return _vad_model


def record_until_silence(
    input_device=None,
    max_duration: float = 30.0,
    silence_threshold: float = 0.5,
    silence_ms: int = 800,
) -> np.ndarray:
    """Record audio until silence is detected. Runs synchronously — call via asyncio.to_thread()."""
    import sounddevice as sd

    model = _load_vad_model()
    sr = 16000
    chunk_ms = 30
    chunk_size = int(sr * chunk_ms / 1000)

    collected = []
    silent_count = 0
    max_silence_chunks = int(silence_ms / chunk_ms)
    total_chunks = 0
    max_chunks = int(max_duration * 1000 / chunk_ms)

    with sd.InputStream(
        samplerate=sr,
        channels=1,
        dtype="float32",
        blocksize=chunk_size,
        device=input_device or settings.voice.input_device,
    ) as stream:
        while total_chunks < max_chunks:
            data, overflowed = stream.read(chunk_size)
            chunk = data[:, 0]

            chunk_tensor = torch.FloatTensor(chunk)
            speech_prob = model(chunk_tensor, sr).item()

            if speech_prob >= silence_threshold:
                collected.append(chunk)
                silent_count = 0
            else:
                if collected:
                    silent_count += 1
                    collected.append(chunk)
                    if silent_count >= max_silence_chunks:
                        break
            total_chunks += 1

    if not collected:
        return np.array([], dtype=np.float32)

    return np.concatenate(collected)