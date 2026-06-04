const currentUser = window.CHAT_CONFIG.currentUser;
let users = window.CHAT_CONFIG.users || [];
const socket = window.io ? io() : null;

const messageList = document.getElementById("messageList");
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("messageInput");
const onlineUsers = document.getElementById("onlineUsers");
const onlineCount = document.getElementById("onlineCount");
const typingIndicator = document.getElementById("typingIndicator");
const chatTitle = document.getElementById("chatTitle");
const themeToggle = document.getElementById("themeToggle");
const searchInput = document.getElementById("searchInput");
const searchResults = document.getElementById("searchResults");
const emojiToggle = document.getElementById("emojiToggle");
const emojiPicker = document.getElementById("emojiPicker");
const uploadToggle = document.getElementById("uploadToggle");
const uploadForm = document.getElementById("uploadForm");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebar = document.getElementById("sidebar");

let activeUser = null;
let onlineIds = new Set();
let socketConnected = false;
let fallbackStarted = false;
let lastMessageId = 0;
let typingTimer = null;

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value || "";
    return div.innerHTML;
}

function avatarUrl(user) {
    return user.profile_picture ? `/uploads/${encodeURIComponent(user.profile_picture)}` : "/static/images/default-avatar.svg";
}

function isConversationMessage(message) {
    if (!activeUser || !message.recipient) return false;
    const senderId = message.sender.id;
    const recipientId = message.recipient.id;
    return (
        (senderId === currentUser.id && recipientId === activeUser.id) ||
        (senderId === activeUser.id && recipientId === currentUser.id)
    );
}

function clearMessages(emptyText = "No messages yet. Say hello.") {
    messageList.innerHTML = `<div class="empty-chat">${emptyText}</div>`;
}

function renderContacts() {
    onlineUsers.innerHTML = "";
    onlineCount.textContent = onlineIds.size;

    if (users.length === 0) {
        onlineUsers.innerHTML = '<li class="muted-contact">No other users yet</li>';
        return;
    }

    users.forEach((user) => {
        const item = document.createElement("li");
        item.className = `contact-item ${activeUser && activeUser.id === user.id ? "active" : ""}`;
        item.dataset.userId = user.id;
        item.innerHTML = `
            <span class="status-dot ${onlineIds.has(user.id) ? "" : "offline"}"></span>
            <img class="avatar" src="${avatarUrl(user)}" alt="">
            <strong>${escapeHtml(user.username)}</strong>
        `;
        item.addEventListener("click", () => selectUser(user));
        onlineUsers.appendChild(item);
    });
}

function renderMessage(message, container = messageList) {
    if (container === messageList && !isConversationMessage(message)) return;
    if (container === messageList && document.querySelector(`[data-message-id="${message.id}"]`)) return;

    const empty = container.querySelector(".empty-chat");
    if (empty) empty.remove();

    lastMessageId = Math.max(lastMessageId, Number(message.id) || 0);
    const isOwn = message.sender.id === currentUser.id;
    const row = document.createElement("article");
    row.className = `message-row ${isOwn ? "own" : ""}`;
    row.dataset.messageId = message.id;

    const fileMarkup = message.file ? `
        <div class="file-card">
            ${message.file.is_image ? `<img src="${message.file.preview_url}" alt="${escapeHtml(message.file.original_filename)}">` : ""}
            <a href="${message.file.download_url}">${escapeHtml(message.file.original_filename)}</a>
        </div>
    ` : "";

    row.innerHTML = `
        <img class="avatar" src="${avatarUrl(message.sender)}" alt="">
        <div class="bubble">
            <div class="message-meta">
                <strong>${escapeHtml(message.sender.username)}</strong>
                <span>${escapeHtml(message.timestamp)}</span>
                ${isOwn ? `<span class="receipt">${message.read ? "Read" : "Sent"}</span>` : ""}
            </div>
            <p class="message-text">${escapeHtml(message.content)}</p>
            ${fileMarkup}
        </div>
    `;

    container.appendChild(row);
    if (container === messageList) {
        messageList.scrollTop = messageList.scrollHeight;
        if (!isOwn && socketConnected) {
            socket.emit("message_read", { message_id: message.id });
        }
    }
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
}

async function loadConversation() {
    if (!activeUser) return;
    lastMessageId = 0;
    clearMessages("Loading messages...");
    const messages = await fetchJson(`/api/messages?user_id=${activeUser.id}`);
    clearMessages();
    messages.forEach((message) => renderMessage(message));
}

function selectUser(user) {
    activeUser = user;
    chatTitle.textContent = user.username;
    typingIndicator.textContent = onlineIds.has(user.id) ? "Online" : "Offline";
    searchInput.value = "";
    searchResults.classList.add("hidden");
    renderContacts();
    loadConversation().catch(() => clearMessages("Could not load this chat."));
    sidebar.classList.remove("open");
}

async function refreshOnlineUsers() {
    const data = await fetchJson("/api/heartbeat", { method: "POST", body: "{}" });
    onlineIds = new Set((data.online_users || []).map((user) => user.id));
    renderContacts();
    if (activeUser) {
        typingIndicator.textContent = onlineIds.has(activeUser.id) ? "Online" : "Offline";
    }
}

async function refreshUsers() {
    users = await fetchJson("/api/users");
    renderContacts();
}

async function pollMessages() {
    if (!activeUser) return;
    const messages = await fetchJson(`/api/messages?user_id=${activeUser.id}&after_id=${lastMessageId}`);
    messages.forEach((message) => renderMessage(message));
}

function startFallback() {
    if (fallbackStarted) return;
    fallbackStarted = true;
    refreshOnlineUsers().catch(() => {});
    refreshUsers().catch(() => {});
    window.setInterval(() => refreshOnlineUsers().catch(() => {}), 5000);
    window.setInterval(() => pollMessages().catch(() => {}), 2500);
}

renderContacts();
startFallback();

messageForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!activeUser) {
        alert("Select a user first.");
        return;
    }
    const content = messageInput.value.trim();
    if (!content) return;

    if (socketConnected) {
        socket.emit("send_message", { content, recipient_id: activeUser.id });
    } else {
        await fetchJson("/api/messages", {
            method: "POST",
            body: JSON.stringify({ content, recipient_id: activeUser.id })
        }).then((message) => renderMessage(message)).catch((error) => alert(error.message));
    }
    messageInput.value = "";
    if (socketConnected) socket.emit("typing", { typing: false, recipient_id: activeUser.id });
});

messageInput.addEventListener("input", () => {
    if (!socketConnected || !activeUser) return;
    socket.emit("typing", { typing: true, recipient_id: activeUser.id });
    window.clearTimeout(typingTimer);
    typingTimer = window.setTimeout(() => socket.emit("typing", { typing: false, recipient_id: activeUser.id }), 900);
});

if (socket) {
    socket.on("connect", () => {
        socketConnected = true;
        refreshOnlineUsers().catch(() => {});
    });
    socket.on("disconnect", () => {
        socketConnected = false;
    });
    socket.on("new_message", (message) => renderMessage(message));
    socket.on("online_users", (online) => {
        onlineIds = new Set((online || []).map((user) => user.id));
        renderContacts();
    });
    socket.on("typing_users", (data) => {
        if (!activeUser || data.from_id !== activeUser.id) return;
        typingIndicator.textContent = data.typing ? `${activeUser.username} is typing...` : (onlineIds.has(activeUser.id) ? "Online" : "Offline");
    });
    socket.on("message_error", (data) => alert(data.error));
    socket.on("message_read", (data) => {
        const row = document.querySelector(`[data-message-id="${data.message_id}"]`);
        const receipt = row ? row.querySelector(".receipt") : null;
        if (receipt) receipt.textContent = "Read";
    });
}

themeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("chat-theme", document.body.classList.contains("dark") ? "dark" : "light");
});

if (localStorage.getItem("chat-theme") === "dark") {
    document.body.classList.add("dark");
}

emojiToggle.addEventListener("click", () => emojiPicker.classList.toggle("hidden"));
emojiPicker.addEventListener("click", (event) => {
    if (event.target.tagName !== "BUTTON") return;
    messageInput.value += event.target.textContent;
    messageInput.focus();
});

uploadToggle.addEventListener("click", () => uploadForm.classList.toggle("hidden"));
uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!activeUser) {
        alert("Select a user first.");
        return;
    }
    const formData = new FormData(uploadForm);
    formData.append("recipient_id", activeUser.id);
    const response = await fetch("/upload", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
        alert(data.error || "Upload failed.");
        return;
    }
    uploadForm.reset();
    uploadForm.classList.add("hidden");
});

searchInput.addEventListener("input", async () => {
    const query = searchInput.value.trim();
    searchResults.innerHTML = "";
    if (!query || !activeUser) {
        searchResults.classList.add("hidden");
        return;
    }

    const results = await fetchJson(`/messages/search?q=${encodeURIComponent(query)}&user_id=${activeUser.id}`);
    searchResults.classList.remove("hidden");
    if (results.length === 0) {
        searchResults.innerHTML = '<div class="system-message">No matching messages found.</div>';
        return;
    }
    results.reverse().forEach((message) => renderMessage(message, searchResults));
});

sidebarToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
