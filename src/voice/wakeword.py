from __future__ import annotations

import asyncio
import threading

import structlog

from src.config import settings

logger = structlog.get_logger()


class WakeWordListener:
    """
    Continuously reads from the microphone in a background thread.
    Fires an asyncio.Event when the configured wake word is detected.
    """

    def __init__(self, detected_event: asyncio.Event):
        self.detected_event = detected_event
        self._running = False
        self._model = None

    def load(self):
        from openwakeword.model import Model

        model_path = settings.voice.wake_word.model
        # openwakeword accepts both built-in names and .onnx file paths
        self._model = Model(wakeword_models=[model_path])
        logger.info("wakeword_model_loaded", model=model_path)

    def start(self, loop: asyncio.AbstractEventLoop):
        self._running = True
        threading.Thread(target=self._run, args=(loop,), daemon=True).start()
        logger.info("wakeword_listener_started")

    def stop(self):
        self._running = False
        logger.info("wakeword_listener_stopped")

    def _run(self, loop: asyncio.AbstractEventLoop):
        import numpy as np
        import sounddevice as sd

        chunk_size = 1280   # 80ms at 16kHz; openwakeword expects 16kHz int16

        try:
            with sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
                device=settings.voice.input_device,
            ) as stream:
                while self._running:
                    chunk, _ = stream.read(chunk_size)
                    prediction = self._model.predict(chunk.flatten().astype(np.int16))
                    score = max(prediction.values()) if prediction else 0.0
                    if score >= settings.voice.wake_word.threshold:
                        logger.info("wakeword_detected", score=score)
                        loop.call_soon_threadsafe(self.detected_event.set)
        except Exception as e:
            logger.error("wakeword_listener_error", error=str(e))