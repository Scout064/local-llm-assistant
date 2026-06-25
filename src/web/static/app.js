const app = {
    ws: null,
    currentConversationId: null,
    currentAssistantEl: null,
    currentAssistantText: "",
    recording: false,
    mediaRecorder: null,
};

function setStatus(state) {
    const badge = document.getElementById("status-badge");
    badge.textContent = state;
}

async function loadConversations() {
    const resp = await fetch("/conversations");
    const convs = await resp.json();
    renderConversationList(convs);
}

function renderConversationList(convs) {
    const list = document.getElementById("conversation-list");
    list.innerHTML = "";
    convs.forEach((conv) => {
        const el = document.createElement("div");
        el.className = "conv-item" + (conv.id === app.currentConversationId ? " active" : "");
        el.textContent = conv.title || "New conversation";
        el.addEventListener("click", () => selectConversation(conv.id));
        el.addEventListener("dblclick", () => renameConversation(conv.id, conv.title));
        list.appendChild(el);
    });
}

async function selectConversation(id) {
    app.currentConversationId = id;
    connectWebSocket(id);
    await loadMessages(id);
    loadConversations();
}

async function loadMessages(conversationId) {
    const resp = await fetch(`/conversations/${conversationId}/messages`);
    const msgs = await resp.json();
    const container = document.getElementById("messages");
    container.innerHTML = "";
    msgs.forEach((msg) => {
        if (msg.role === "user") {
            appendMessage("user", msg.content);
        } else if (msg.role === "assistant") {
            appendMessage("assistant", msg.content);
        } else if (msg.role === "tool") {
            const toolEl = document.createElement("div");
            toolEl.className = "msg-tool";
            toolEl.textContent = `[tool: ${msg.tool_name}]`;
            container.appendChild(toolEl);
            try {
                const data = JSON.parse(msg.content);
                if (data.type === "image") {
                    const imgWrap = document.createElement("div");
                    imgWrap.className = "msg msg-assistant msg-image";
                    const img = document.createElement("img");
                    img.src = data.path;
                    img.alt = "Generated image";
                    img.style.maxWidth = "100%";
                    imgWrap.appendChild(img);
                    container.appendChild(imgWrap);
                }
            } catch {}
        }
    });
    container.scrollTop = container.scrollHeight;
}

function appendMessage(role, text) {
    const container = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = `msg msg-${role}`;
    div.innerHTML = `<div class="msg-role">${role}</div><div class="msg-content">${escapeHtml(text)}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function escapeHtml(text) {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
}

function startAssistantBubble() {
    const container = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "msg msg-assistant";
    div.innerHTML = `<div class="msg-role">assistant</div><div class="msg-content"></div>`;
    container.appendChild(div);
    app.currentAssistantEl = div.querySelector(".msg-content");
    app.currentAssistantText = "";
    return div;
}

function connectWebSocket(conversationId) {
    if (app.ws) {
        app.ws.close();
    }
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    app.ws = new WebSocket(`${protocol}//${location.host}/ws/${conversationId}`);

    app.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleWsMessage(msg);
    };

    app.ws.onclose = () => {
        setStatus("IDLE");
    };
}

function handleWsMessage(msg) {
    switch (msg.type) {
        case "chunk":
            if (!app.currentAssistantEl) {
                startAssistantBubble();
            }
            app.currentAssistantText += msg.text;
            app.currentAssistantEl.textContent = app.currentAssistantText;
            document.getElementById("messages").scrollTop = document.getElementById("messages").scrollHeight;
            break;
        case "image":
            const imgContainer = document.getElementById("messages");
            const imgWrap = document.createElement("div");
            imgWrap.className = "msg msg-assistant msg-image";
            const imgEl = document.createElement("img");
            imgEl.src = msg.path;
            imgEl.alt = "Generated image";
            imgEl.style.maxWidth = "100%";
            imgWrap.appendChild(imgEl);
            imgContainer.appendChild(imgWrap);
            imgContainer.scrollTop = imgContainer.scrollHeight;
            break;
        case "tool_start":
            app.currentAssistantEl = null;
            const toolEl = document.createElement("div");
            toolEl.className = "msg-tool";
            toolEl.textContent = `[calling: ${msg.tool}]`;
            document.getElementById("messages").appendChild(toolEl);
            break;
        case "tool_done":
            break;
        case "status":
            setStatus(msg.state);
            break;
        case "done":
            app.currentAssistantEl = null;
            app.currentAssistantText = "";
            setStatus("IDLE");
            break;
        case "error":
            appendMessage("assistant", `Error: ${msg.message}`);
            setStatus("IDLE");
            break;
        case "conversation_created":
            selectConversation(msg.id);
            break;
        case "conversation_titled":
            loadConversations();
            break;
        case "voice_transcribed":
            sendMessage(msg.text);
            break;
    }
}

async function sendMessage(text) {
    if (!text.trim()) return;
    if (!app.currentConversationId) {
        const resp = await fetch("/conversations", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({title: "New conversation"}),
        });
        const conv = await resp.json();
        app.currentConversationId = conv.id;
        await selectConversation(conv.id);
    }
    appendMessage("user", text);
    if (app.ws && app.ws.readyState === WebSocket.OPEN) {
        app.ws.send(JSON.stringify({type: "message", conversation_id: app.currentConversationId, text}));
    }
    startAssistantBubble();
}

async function newConversation() {
    const resp = await fetch("/conversations", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({}),
    });
    const conv = await resp.json();
    await selectConversation(conv.id);
}

async function renameConversation(id, currentTitle) {
    const newTitle = prompt("Rename conversation:", currentTitle);
    if (newTitle && newTitle !== currentTitle) {
        await fetch(`/conversations/${id}/title`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({title: newTitle}),
        });
        loadConversations();
    }
}

function toggleMic() {
    if (app.recording) {
        stopRecording();
    } else {
        startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});
        app.mediaRecorder = new MediaRecorder(stream);
        const chunks = [];
        app.mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
        app.mediaRecorder.onstop = async () => {
            const blob = new Blob(chunks, {type: "audio/webm"});
            stream.getTracks().forEach((t) => t.stop());
            // In voice pipeline mode, transcription happens server-side
            // For now, we'd send to an STT endpoint
        };
        app.mediaRecorder.start();
        app.recording = true;
        document.getElementById("mic-btn").classList.add("recording");
        if (app.ws) {
            app.ws.send(JSON.stringify({type: "voice_start", conversation_id: app.currentConversationId}));
        }
    } catch (e) {
        console.error("Mic error:", e);
    }
}

function stopRecording() {
    if (app.mediaRecorder && app.recording) {
        app.mediaRecorder.stop();
    }
    app.recording = false;
    document.getElementById("mic-btn").classList.remove("recording");
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("send-btn").addEventListener("click", () => {
        const input = document.getElementById("message-input");
        sendMessage(input.value);
        input.value = "";
    });

    document.getElementById("message-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            const input = document.getElementById("message-input");
            sendMessage(input.value);
            input.value = "";
        }
    });

    document.getElementById("new-chat-btn").addEventListener("click", newConversation);
    document.getElementById("mic-btn").addEventListener("click", toggleMic);

    loadConversations();
});