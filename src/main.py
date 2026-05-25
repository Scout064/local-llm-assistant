from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from src.config import settings
from src.persistence.db import init_db, close_db
from src.llm.client import ollama_client, AgentEvent
from src.plugins.registry import PluginRegistry
from src.web.routes import router, broadcast, broadcast_global

logger = structlog.get_logger()

wakeword_listener = None


async def _check_services(registry: PluginRegistry):
    model_ok = await ollama_client.check_model_available()
    if not model_ok:
        logger.error("model_not_available", model=settings.llm.model)

    for status in registry.get_status():
        if status["status"] != "ok":
            logger.warning("plugin_unhealthy", name=status["name"])


async def _start_wakeword():
    global wakeword_listener
    if not settings.voice.enabled or not settings.voice.wake_word.enabled:
        logger.info("wakeword_disabled")
        return

    try:
        from src.voice.wakeword import WakeWordListener

        detected_event = asyncio.Event()
        wakeword_listener = WakeWordListener(detected_event)
        wakeword_listener.load()

        loop = asyncio.get_running_loop()
        wakeword_listener.start(loop)

        asyncio.create_task(_wakeword_loop(detected_event))
        logger.info("wakeword_started", model=settings.voice.wake_word.model)
    except Exception as e:
        logger.warning("wakeword_init_failed", error=str(e))


async def _wakeword_loop(detected_event: asyncio.Event):
    try:
        from src.voice.vad import record_until_silence
        from src.voice.stt import transcribe
    except ImportError as e:
        logger.warning("voice_dependencies_missing", error=str(e))
        return

    while True:
        await detected_event.wait()
        detected_event.clear()
        logger.info("wakeword_triggered")

        await broadcast_global({"type": "status", "state": "WAKE_WORD_DETECTED"})

        audio = await asyncio.to_thread(record_until_silence)
        if audio is None or len(audio) == 0:
            continue

        await broadcast_global({"type": "status", "state": "LISTENING"})

        try:
            text = await asyncio.to_thread(transcribe, audio)
            logger.info("voice_transcribed", text=text)
        except Exception as e:
            logger.error("stt_error", error=str(e))
            continue

        if not text.strip():
            continue

        await broadcast_global({"type": "voice_transcribed", "text": text})
        logger.info("voice_input_ready", text=text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_assistant", db_path=settings.persistence.db_path)
    await init_db()
    logger.info("database_initialized")

    registry = PluginRegistry()
    await registry.load_all(settings)
    app.state.registry = registry

    await _check_services(registry)
    await _start_wakeword()

    yield

    logger.info("shutting_down")

    if wakeword_listener:
        wakeword_listener.stop()

    await registry.teardown_all()
    await close_db()
    logger.info("shutdown_complete")


app = FastAPI(title="Local Assistant", lifespan=lifespan)

static_dir = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.web.host,
        port=settings.web.port,
        log_level=settings.web.log_level,
    )