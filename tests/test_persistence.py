import pytest
import pytest_asyncio

from src.persistence.db import init_db, close_db, get_db
from src.persistence.conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
    soft_delete_conversation,
    add_message,
    get_messages,
)


@pytest_asyncio.fixture
async def db():
    await init_db()
    yield
    await close_db()


@pytest.mark.asyncio
async def test_create_conversation(db):
    conv_id = await create_conversation(title="Test Conv")
    assert conv_id is not None
    conv = await get_conversation(conv_id)
    assert conv is not None
    assert conv["title"] == "Test Conv"


@pytest.mark.asyncio
async def test_list_conversations(db):
    await create_conversation(title="Conv A")
    await create_conversation(title="Conv B")
    convs = await list_conversations()
    assert len(convs) >= 2


@pytest.mark.asyncio
async def test_update_conversation_title(db):
    conv_id = await create_conversation(title="Original")
    await update_conversation_title(conv_id, "Updated")
    conv = await get_conversation(conv_id)
    assert conv["title"] == "Updated"


@pytest.mark.asyncio
async def test_title_length_cap(db):
    conv_id = await create_conversation(title="Original")
    long_title = "A" * 500
    await update_conversation_title(conv_id, long_title)
    conv = await get_conversation(conv_id)
    assert len(conv["title"]) <= 256


@pytest.mark.asyncio
async def test_empty_title_defaults(db):
    conv_id = await create_conversation(title="Original")
    await update_conversation_title(conv_id, "   ")
    conv = await get_conversation(conv_id)
    assert conv["title"] == "New conversation"


@pytest.mark.asyncio
async def test_soft_delete_conversation(db):
    conv_id = await create_conversation(title="Delete Me")
    await soft_delete_conversation(conv_id)
    convs = await list_conversations(include_deleted=False)
    ids = [c["id"] for c in convs]
    assert conv_id not in ids
    convs_all = await list_conversations(include_deleted=True)
    ids_all = [c["id"] for c in convs_all]
    assert conv_id in ids_all


@pytest.mark.asyncio
async def test_add_and_get_messages(db):
    conv_id = await create_conversation()
    msg_id = await add_message(conv_id, "user", "Hello")
    assert msg_id is not None

    await add_message(conv_id, "assistant", "Hi there!")

    messages = await get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_message_order(db):
    conv_id = await create_conversation()
    await add_message(conv_id, "user", "First")
    await add_message(conv_id, "assistant", "Second")
    await add_message(conv_id, "user", "Third")

    messages = await get_messages(conv_id)
    assert messages[0]["content"] == "First"
    assert messages[1]["content"] == "Second"
    assert messages[2]["content"] == "Third"


@pytest.mark.asyncio
async def test_foreign_key_enforcement(db):
    """Messages added with a non-existent conversation_id should fail."""
    import aiosqlite
    with pytest.raises((aiosqlite.IntegrityError, Exception)):
        await add_message("nonexistent-conv-id", "user", "orphan")


@pytest.mark.asyncio
async def test_history_trimming_logic(db):
    from src.config import settings

    conv_id = await create_conversation()
    for i in range(50):
        await add_message(conv_id, "user", f"Message {i}")

    messages = await get_messages(conv_id)
    assert len(messages) == 50

    max_history = settings.llm.max_history_messages
    system_msg = {"role": "system", "content": "test"}
    all_msgs = [system_msg] + [{"role": "user", "content": m["content"]} for m in messages]

    assert len(all_msgs) > max_history + 1
    trimmed = [all_msgs[0]] + all_msgs[-(max_history):]
    assert len(trimmed) <= max_history + 1