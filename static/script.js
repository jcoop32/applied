// Main Entry for Chat Page (index.html) and Profile Page (profile.html)
let currentSessionId = null;

document.addEventListener("DOMContentLoaded", () => {
    // Prevent double initialization
    if (window.appInitialized) return;
    window.appInitialized = true;

    // Auth Check runs globally first
    checkAuth().then(() => {
        const path = window.location.pathname;

        // Route-based initialization
        if (path === "/" || path.startsWith("/chat")) {
            initChatPage();
        } else if (path.startsWith("/profile")) {
            initProfilePage();
        } else if (path.startsWith("/jobs")) {
            initJobsPage();
        }
    });

    // Logout Helper
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("token");
            document.cookie = "access_token=; Max-Age=0; path=/";
            window.location.href = "/login";
        });
    }

    // Mobile Menu
    const mobileMenuBtn = document.getElementById("mobile-menu-btn");
    const sidebar = document.querySelector(".sidebar");
    if (mobileMenuBtn && sidebar) {
        mobileMenuBtn.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });
    }
});

const API_BASE = "/api";
let currentUser = null;
let lastResearchStatus = {}; // Cache to track transitions

// Helper: Authenticated Fetch
async function authFetch(url, options = {}) {
    const token = localStorage.getItem("token");
    if (!token) {
        window.location.href = "/login";
        throw new Error("No token found");
    }

    const headers = options.headers ? new Headers(options.headers) : new Headers();
    headers.set("Authorization", `Bearer ${token}`);

    const newOptions = {
        ...options,
        headers: headers
    };

    const res = await fetch(url, newOptions);
    if (res.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
    return res;
}

async function checkAuth() {
    try {
        const res = await authFetch(`${API_BASE}/auth/me`);
        if (!res.ok) return;
        currentUser = await res.json();

        const userEmailDisplay = document.getElementById("user-email-display");
        if (userEmailDisplay) userEmailDisplay.textContent = currentUser.email;

        initRealtime(); // Initialize Realtime Subscriptions
    } catch (e) {
        // Redirect handled in authFetch
    }
}

// ==========================================
// CHAT PAGE LOGIC
// ==========================================
function initChatPage() {
    const sendBtn = document.getElementById("send-btn");
    const chatInput = document.getElementById("chat-input");
    const fileInput = document.getElementById("file-upload");
    const uploadTrigger = document.getElementById("upload-trigger");
    const newChatBtn = document.getElementById("new-chat-btn");

    // Load Sessions, then restore last active session
    loadSessions().then(() => {
        // Check URL first
        const urlParams = new URLSearchParams(window.location.search);
        const urlSessionId = urlParams.get('session_id');

        if (urlSessionId) {
            loadSession(urlSessionId);
            // Clean URL
            window.history.replaceState({}, document.title, "/");
        } else {
            const savedSessionId = localStorage.getItem('currentChatSessionId');
            if (savedSessionId) {
                loadSession(savedSessionId);
            }
        }
    });

    // Check Researcher Visibility - Removed, handled by checkAuth -> initRealtime -> updateResearchUI

    // Event Listeners
    if (sendBtn) sendBtn.addEventListener("click", sendMessage);

    if (chatInput) {
        chatInput.addEventListener("input", function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            sendBtn.disabled = this.value.trim() === "";
        });

        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    if (uploadTrigger) uploadTrigger.addEventListener("click", () => fileInput.click());
    if (fileInput) fileInput.addEventListener("change", handleFileUpload);

    if (newChatBtn) {
        newChatBtn.addEventListener("click", startNewChat);
    }

    // Explicitly attach listeners to Research Buttons (Find Jobs)
    const researchBtns = document.querySelectorAll(".research-btn");
    researchBtns.forEach(btn => {
        btn.addEventListener("click", openSearchConfigModal);
    });

    // Attach listeners to Update Resume buttons or others if needed
    // (Attach Resume logic is handled in initAttachResume)

    // Expose global actions (Keep for now if legacy references exist, but primary is via listeners)
    window.triggerResearch = triggerResearch;
    window.triggerApply = triggerApply;
    // window.openSearchConfigModal = openSearchConfigModal; // Removed reliance

    initMentionSystem();
    initAttachResume();
    initSearchModal();

    // Check for pending apply prompt from Jobs page
    const pendingPrompt = localStorage.getItem('pendingApplyPrompt');
    if (pendingPrompt) {
        const chatInput = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-btn');
        if (chatInput) {
            chatInput.value = pendingPrompt;
            chatInput.style.height = 'auto';
            chatInput.style.height = (chatInput.scrollHeight) + 'px';
            if (sendBtn) sendBtn.disabled = false;
        }
        localStorage.removeItem('pendingApplyPrompt');
    }
}

// --- Chat Sessions ---
async function loadSessions() {
    try {
        const res = await authFetch(`${API_BASE}/chat/sessions`);
        if (!res.ok) return;
        const sessions = await res.json();

        const container = document.getElementById("chat-history-list");
        if (!container) return;

        // Remove only dynamically added session items, keep the static "Current Session"
        container.querySelectorAll(".session-item").forEach(item => item.remove());

        // Add session items
        sessions.forEach(session => {
            const item = document.createElement("div");
            item.className = "history-item session-item";

            // Flex container
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.style.alignItems = "center";
            item.style.padding = "10px 15px";
            item.style.cursor = "pointer";
            item.style.position = "relative"; // For dropdown positioning

            // Title
            const titleSpan = document.createElement("span");
            titleSpan.textContent = session.title;
            titleSpan.style.whiteSpace = "nowrap";
            titleSpan.style.overflow = "hidden";
            titleSpan.style.textOverflow = "ellipsis";
            titleSpan.style.marginRight = "10px";
            titleSpan.style.flex = "1";

            // Allow clicking title to load
            titleSpan.onclick = (e) => {
                e.stopPropagation();
                loadSession(session.id);
            };

            item.appendChild(titleSpan);

            // Kebab Menu (Three Dots)
            const kebabBtn = document.createElement("div");
            kebabBtn.className = "kebab-btn";
            kebabBtn.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
            kebabBtn.style.padding = "5px";
            kebabBtn.style.color = "var(--text-secondary)";
            kebabBtn.style.cursor = "pointer";

            // Dropdown Menu
            const dropdown = document.createElement("div");
            dropdown.className = "session-menu-dropdown";
            dropdown.style.display = "none";
            dropdown.style.position = "absolute";
            dropdown.style.right = "10px";
            dropdown.style.top = "30px";
            dropdown.style.background = "#2a2a2a";
            dropdown.style.border = "1px solid #444";
            dropdown.style.borderRadius = "4px";
            dropdown.style.zIndex = "100";
            dropdown.style.minWidth = "120px";

            // Rename Option
            const renameOpt = document.createElement("div");
            renameOpt.textContent = "Rename";
            renameOpt.style.padding = "8px 12px";
            renameOpt.style.cursor = "pointer";
            renameOpt.className = "menu-option";
            renameOpt.onmouseover = () => renameOpt.style.background = "#3a3a3a";
            renameOpt.onmouseout = () => renameOpt.style.background = "transparent";
            renameOpt.onclick = (e) => {
                e.stopPropagation();
                dropdown.style.display = "none";
                renameSession(session.id, session.title);
            };

            // Delete Option
            const deleteOpt = document.createElement("div");
            deleteOpt.textContent = "Delete";
            deleteOpt.style.padding = "8px 12px";
            deleteOpt.style.cursor = "pointer";
            deleteOpt.style.color = "#ff6b6b";
            deleteOpt.className = "menu-option";
            deleteOpt.onmouseover = () => deleteOpt.style.background = "#3a3a3a";
            deleteOpt.onmouseout = () => deleteOpt.style.background = "transparent";
            deleteOpt.onclick = (e) => {
                e.stopPropagation();
                dropdown.style.display = "none";
                deleteSession(session.id);
            };

            dropdown.appendChild(renameOpt);
            dropdown.appendChild(deleteOpt);

            kebabBtn.onclick = (e) => {
                e.stopPropagation();
                // Close others
                document.querySelectorAll('.session-menu-dropdown').forEach(el => {
                    if (el !== dropdown) el.style.display = 'none';
                });
                dropdown.style.display = dropdown.style.display === "block" ? "none" : "block";
            };

            item.appendChild(kebabBtn);
            item.appendChild(dropdown);

            // Highlight current
            if (session.id === currentSessionId) {
                item.classList.add('active');
            }

            // Click item (background) loads session
            item.onclick = (e) => {
                loadSession(session.id);
            };

            container.appendChild(item);
        });

        // Global click to close menus
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.kebab-btn')) {
                document.querySelectorAll('.session-menu-dropdown').forEach(el => el.style.display = 'none');
            }
        });

    } catch (e) {
        console.error("Failed to load sessions", e);
    }
}

async function deleteSession(sessionId) {
    if (!confirm("Are you sure you want to delete this chat?")) return;

    try {
        const res = await authFetch(`${API_BASE}/chat/sessions/${sessionId}`, {
            method: "DELETE"
        });

        if (res.ok) {
            // If current session, clear it
            if (currentSessionId === sessionId) {
                startNewChat();
            } else {
                loadSessions();
            }
        } else {
            alert("Failed to delete session");
        }
    } catch (e) {
        console.error("Delete failed", e);
    }
}

async function renameSession(sessionId, oldTitle) {
    const newTitle = prompt("Enter new chat title:", oldTitle);
    if (!newTitle || newTitle === oldTitle) return;

    try {
        const res = await authFetch(`${API_BASE}/chat/sessions/${sessionId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: newTitle })
        });

        if (res.ok) {
            loadSessions(); // Refresh list
        } else {
            alert("Failed to rename session");
        }
    } catch (e) {
        console.error("Rename failed", e);
    }
}

async function startNewChat() {
    // CRITICAL: Reset session ID first to ensure next message creates new session
    currentSessionId = null;
    localStorage.removeItem('currentChatSessionId');

    const container = document.getElementById("messages-container");
    if (container) {
        container.innerHTML = "";

        // Add Welcome
        const welcomeHtml = `
            <div class="message bot-message">
                <div class="avatar"><i class="fas fa-robot"></i></div>
                <div class="content">
                    Hello! I'm your AI Resume Expert. I can help you find jobs, analyze your resume, or apply to positions.<br><br>
                    How can I help you today?
                </div>
            </div>
        `;
        container.innerHTML = welcomeHtml;
    }

    // Refresh sessions to clear active selection
    loadSessions();
}

async function loadSession(sessionId) {
    currentSessionId = sessionId;
    localStorage.setItem('currentChatSessionId', sessionId);
    const container = document.getElementById("messages-container");
    if (!container) return;
    container.innerHTML = ""; // Clear current

    // Refresh sidebar highlighting
    // loadSessions(); // Removed to prevent full list re-fetch

    // Efficiently update active class
    document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
    // Find the item with this session ID and add active
    // We didn't store ID on the element easily, but we can try finding by click handler or re-render if needed.
    // Actually, let's just re-iterate or rely on the fact that the user just clicked it.
    // But if loaded via URL, we need to highlight. 
    // Let's implement a simple ID lookup if possible, or just skip if performance is key.
    // Better: Add data-id to session items in loadSessions implementation (which we didn't touch yet but can assume or leave as is).
    // For now, let's just skip the full refresh. The highlighting might be stale until page reload but that's a fair trade for performance, 
    // OR we can implement a lightweight highlighter.

    const items = document.querySelectorAll('.session-item');
    items.forEach(item => {
        // This is a bit hacky without data attributes, but we can't easily modify loadSessions output structure 
        // without seeing it again. 
        // Wait, we can just look at `loadSessions` in previous view. It didn't add data-id.
        // Let's just remove the call.
    });

    // Fetch messages
    try {
        const res = await authFetch(`${API_BASE}/chat/sessions/${sessionId}/messages`);
        if (!res.ok) throw new Error("Failed to load");
        const messages = await res.json();

        if (messages.length === 0) {
            addMessage("model", "This session history is empty.", true);
        } else {
            messages.forEach(msg => {
                addMessage(msg.role === 'model' ? 'model' : 'user', msg.content, true);
            });
        }

        setTimeout(scrollToBottom, 100);

        // Connect to Live Log Stream
        connectLogStream(sessionId);

    } catch (e) {
        console.error(e);
        addMessage("model", "❌ Failed to load chat history.");
    }
}

let activeEventSource = null;

function connectLogStream(sessionId) {
    if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
    }

    // Close any previous terminal view? Maybe keep history?
    // distinct per session? For now, we just attach listener.

    console.log("🔌 Connecting to Log Stream for", sessionId);
    activeEventSource = new EventSource(`${API_BASE}/chat/stream/${sessionId}`);

    activeEventSource.onmessage = (event) => {
        // Default message type
        // But we used 'log' type in python mainly.
        // EventSource standard handles named events specifically or 'message' as default.
        // Our python sends "event: log\ndata: ...". So we need matching listener.
    };

    activeEventSource.addEventListener("log", (event) => {
        const msg = event.data;
        showLogInternal(msg);
    });

    activeEventSource.addEventListener("complete", (event) => {
        const msg = event.data;
        showLogInternal(`✅ ${msg}`, "success");
        // Don't close immediately, user might want to read.
        // activeEventSource.close(); 
    });

    activeEventSource.addEventListener("error", (event) => {
        // showLogInternal("Connection lost (Agent might be done or sleeping).", "error");
        // Often fires on normal close too
    });
}

function showLogInternal(text, type = "info") {
    // 1. Find or Create Terminal UI Container
    let terminal = document.getElementById("agent-terminal");
    const container = document.getElementById("messages-container");

    if (!terminal) {
        terminal = document.createElement("div");
        terminal.id = "agent-terminal";
        terminal.className = "agent-terminal";
        terminal.innerHTML = `
            <div class="terminal-header" onclick="this.parentElement.classList.toggle('minimized')">
                <span><i class="fas fa-terminal"></i> Agent Live Logs</span>
                <span class="toggle-icon"><i class="fas fa-chevron-down"></i></span>
            </div>
            <div class="terminal-body" id="terminal-logs"></div>
        `;
        // Insert at bottom of messages container? Or fixed at bottom of screen?
        // Fixed bottom of messages container is better contextually.
        // Actually, maybe fixed at bottom of CHAT AREA (above input).

        // Let's float it above the input area
        const wrapper = document.querySelector(".chat-area"); // Parent of messages-container
        if (wrapper) {
            // We want it overlaying the bottom of the messages list, or pushing messages up?
            // Let's put it IN message container for now, appended at end.
            // Problem: manual scroll.

            // Better: Insert it AFTER messages container, BEFORE input wrapper.
            const inputWrapper = document.querySelector(".input-area-wrapper");
            wrapper.insertBefore(terminal, inputWrapper);
        }
    }

    const logBody = document.getElementById("terminal-logs");
    if (!logBody) return;

    const line = document.createElement("div");
    line.className = `log-line log-${type}`;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    line.innerHTML = `<span class="log-time">[${time}]</span> ${text}`;

    logBody.appendChild(line);
    logBody.scrollTop = logBody.scrollHeight;

    // Ensure terminal is visible/open if new logs come in
    terminal.classList.remove("minimized");
}


// --- Chat Actions ---

function scrollToBottom() {
    const c = document.getElementById("messages-container");
    if (c) c.scrollTop = c.scrollHeight;
}

function addMessage(role, content, isHistoryLoad = false, buttons = []) {
    const container = document.getElementById("messages-container");
    if (!container) return;

    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role === 'user' ? 'user-message' : 'bot-message'}`;

    const avatarDiv = document.createElement("div");
    avatarDiv.className = "avatar";
    avatarDiv.innerHTML = role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

    const contentDiv = document.createElement("div");
    contentDiv.className = "content";

    // Basic formatting
    let formatted = content ? content
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>') : "";

    contentDiv.innerHTML = formatted;

    // Render Buttons if any
    if (buttons && buttons.length > 0) {
        const btnContainer = document.createElement("div");
        btnContainer.className = "chat-buttons";
        btnContainer.style.marginTop = "10px";
        btnContainer.style.display = "flex";
        btnContainer.style.gap = "8px";
        btnContainer.style.flexWrap = "wrap";

        buttons.forEach(btnText => {
            const btn = document.createElement("button");
            btn.className = "chip";
            btn.textContent = btnText;
            btn.style.fontSize = "0.9rem";
            btn.style.cursor = "pointer";
            btn.onclick = () => {
                const chatInput = document.getElementById("chat-input");
                if (chatInput) {
                    chatInput.value = btnText;
                    sendMessage();
                }
            };
            btnContainer.appendChild(btn);
        });
        contentDiv.appendChild(btnContainer);
    }

    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);

    container.appendChild(msgDiv);
    scrollToBottom();

    return contentDiv; // Return for streaming updates
}

async function sendMessage() {
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");

    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.disabled = true;

    addMessage("user", text);

    // Create Bot Message Placeholder
    const botContentDiv = addMessage("model", "");
    const loadingIcon = document.createElement("i");
    loadingIcon.className = "fas fa-ellipsis-h fa-spin";
    botContentDiv.appendChild(loadingIcon);

    // Keep track of full text for markdown rendering
    let fullText = "";

    try {
        const payload = {
            message: text,
            session_id: currentSessionId
        };

        const res = await authFetch(`${API_BASE}/chat/message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("API Error");

        // Streaming Reader
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let firstChunk = true;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            if (firstChunk) {
                loadingIcon.remove(); // Remove spinner on first byte
                firstChunk = false;
            }

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split("\n");
            buffer = lines.pop(); // Keep incomplete line

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);

                    if (data.type === "meta") {
                        if (!currentSessionId && data.session_id) {
                            currentSessionId = data.session_id;
                            localStorage.setItem('currentChatSessionId', data.session_id);
                            loadSessions();
                        }
                    }
                    else if (data.type === "token") {
                        fullText += data.content;
                        // Re-render with basic markdown
                        botContentDiv.innerHTML = fullText
                            .replace(/\n/g, '<br>')
                            .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
                        scrollToBottom();
                    }
                    else if (data.type === "end") {
                        // Handle Buttons/Actions if any
                        if (data.buttons) {
                            // Re-use logic to add buttons? 
                            // We don't have a clean way to add buttons to existing msg via helper,
                            // so we manually do it here or call a helper.
                            // But addMessage handles buttons at creation.
                            // Let's just append them.
                            const btnContainer = document.createElement("div");
                            btnContainer.className = "chat-buttons";
                            btnContainer.style.marginTop = "10px";
                            btnContainer.style.display = "flex";
                            btnContainer.style.gap = "8px";
                            btnContainer.style.flexWrap = "wrap";

                            (data.buttons || []).forEach(btnText => {
                                const btn = document.createElement("button");
                                btn.className = "chip";
                                btn.textContent = btnText;
                                btn.style.fontSize = "0.9rem";
                                btn.style.cursor = "pointer";
                                btn.onclick = () => {
                                    const chatInput = document.getElementById("chat-input");
                                    if (chatInput) {
                                        chatInput.value = btnText;
                                        sendMessage();
                                    }
                                };
                                btnContainer.appendChild(btn);
                            });
                            botContentDiv.appendChild(btnContainer);
                        }

                        // Handles final action payload buttons (clarification)
                        if (data.action && data.action.type === "clarification") {
                            const opts = data.action.payload.options || [];
                            if (opts.length > 0) {
                                const btnContainer = document.createElement("div");
                                btnContainer.className = "chat-buttons";
                                btnContainer.style.marginTop = "10px";
                                btnContainer.style.display = "flex";
                                btnContainer.style.gap = "8px";
                                btnContainer.style.flexWrap = "wrap";

                                opts.forEach(btnText => {
                                    const btn = document.createElement("button");
                                    btn.className = "chip";
                                    btn.textContent = btnText;
                                    btn.style.fontSize = "0.9rem";
                                    btn.style.cursor = "pointer";
                                    btn.onclick = () => {
                                        const chatInput = document.getElementById("chat-input");
                                        if (chatInput) {
                                            chatInput.value = btnText;
                                            sendMessage();
                                        }
                                    };
                                    btnContainer.appendChild(btn);
                                });
                                botContentDiv.appendChild(btnContainer);
                            }
                        }
                    }

                } catch (e) { console.error("Stream Parse Error", e); }
            }
        }

    } catch (e) {
        addMessage("model", `Sorry, something went wrong: ${e.message}`);
        console.error(e);
    } finally {
        sendBtn.disabled = false;
    }
}

// --- Upload & Research Logic ---

async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    addMessage("user", `[Attached: ${file.name}]`);

    const formData = new FormData();
    formData.append("file", file);

    const token = localStorage.getItem("token");
    try {
        // Use raw fetch for upload to handle multipart boundary automatically
        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }, // manual header for FormData
            body: formData
        });

        if (res.ok) {
            addMessage("model", `✅ Uploaded **${file.name}**. I can now use it.`);
            checkResearcherVisibility(); // Show button now!
        } else {
            addMessage("model", "❌ Upload failed.");
        }
    } catch (e) {
        addMessage("model", "❌ Error uploading.");
    }
}

let supabaseClient = null;

async function initRealtime() {
    try {
        // Optimization: Cache Config
        let config = null;
        const cachedConfig = localStorage.getItem('app_config');
        if (cachedConfig) {
            try { config = JSON.parse(cachedConfig); } catch (e) { }
        }

        if (!config) {
            const configRes = await authFetch('/api/auth/config');
            if (!configRes.ok) return;
            config = await configRes.json();
            localStorage.setItem('app_config', JSON.stringify(config));
        }

        if (window.supabase) {
            // FIX: Pass Auth Token to Client
            const token = localStorage.getItem("token");
            const options = {
                global: {
                    headers: {
                        Authorization: `Bearer ${token}`
                    }
                }
            };

            console.log("🔌 Initializing Supabase with URL:", config.supabase_url);
            supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key, options);
            console.log("🔌 Supabase Realtime Initialized with Auth Token");

            if (!currentUser) return;

            // Subscribe to Profiles (Status Updates)
            supabaseClient
                .channel('public:profiles')
                .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'profiles', filter: `user_id=eq.${currentUser.id}` }, (payload) => {
                    console.log("Realtime: Profile Update", payload);
                    updateResearchUI(payload.new);
                })
                .subscribe((status) => {
                    console.log(`🔌 Channel 'public:profiles' status: ${status}`);
                    if (status === 'SUBSCRIBED') {
                        // showLogInternal("Real-time updates active.", "success");
                    } else if (status === 'CHANNEL_ERROR') {
                        console.error("❌ Realtime Channel Error - Check RLS Policies or Token Validity");
                    }
                });

            // Subscribe to Leads (New Jobs)
            // Note: RLS might prevent receiving events if row-level security is strict on real-time
            supabaseClient
                .channel('public:job_leads')
                .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'job_leads', filter: `user_id=eq.${currentUser.id}` }, (payload) => {
                    console.log("Realtime: New Lead", payload);
                    // Toast or refresh jobs if on jobs page
                    showLogInternal(`New Job Found: ${payload.new.company_name} - ${payload.new.title}`, "success");
                })
                .subscribe();

            // Initial UI Check
            // Use cached profile if we just fetched it or reuse it
            if (!window.currentUserProfile) {
                const res = await authFetch(`${API_BASE}/profile`);
                const data = await res.json();
                window.currentUserProfile = data;
                updateResearchUI(data);
            } else {
                updateResearchUI(window.currentUserProfile);
            }
        }
    } catch (e) {
        console.error("Realtime Init Failed", e);
    }
}

async function updateResearchUI(profileData) {
    if (!profileData) return;

    // 1. Check Primary Resume existence
    const hasResume = !!profileData.primary_resume_name;
    const btns = document.querySelectorAll(".research-btn");

    btns.forEach(btn => {
        if (!hasResume) {
            btn.style.display = "none";
            return;
        }
        btn.style.display = "inline-flex";
    });

    // 2. Check Research Status
    // profileData.profile_data might be JSON string or object depending on source
    let pArgs = profileData.profile_data || {};
    if (typeof pArgs === 'string') {
        try { pArgs = JSON.parse(pArgs); } catch (e) { }
    }

    const startBtns = document.querySelectorAll(".research-btn");
    const statusBox = document.getElementById("research-status-container") || createStatusContainer();

    // Check status of primary resume
    const resumeName = profileData.primary_resume_name;
    const statusObj = (pArgs.research_status || {})[resumeName] || {};
    const status = statusObj.status || "IDLE";

    // Check for transition to COMPLETED
    const lastStatus = lastResearchStatus[resumeName];
    if (status === "COMPLETED" && lastStatus && lastStatus !== "COMPLETED") {
        console.log("Realtime: Research Completed for", resumeName);
        handleResearchCompletion(resumeName);
    }
    lastResearchStatus[resumeName] = status;

    // Reset Buttons text
    startBtns.forEach(btn => {
        if (status === "SEARCHING" || status === "QUEUED") {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Researching...';
            btn.disabled = true;
            btn.style.background = "#555";
        } else {
            btn.innerHTML = '<i class="fas fa-search"></i> Find Jobs';
            btn.disabled = false;
            btn.style.background = "linear-gradient(135deg, #4285f4, #34a853)";
        }
    });

    // Update Status Box / Cancel Button
    if (status === "SEARCHING" || status === "QUEUED") {
        statusBox.style.display = "flex";

        let logText = (statusObj.last_log || "Finding jobs...").replace(/"/g, '&quot;');
        // Truncate long logs
        if (logText.length > 60) logText = logText.substring(0, 57) + "...";

        statusBox.innerHTML = `
            <div style="flex:1;">
                <span class="status-text"><i class="fas fa-sync fa-spin"></i> <span id="live-log-text">${logText}</span></span>
            </div>
            <button id="cancel-research-btn" class="cancel-btn">Stop</button>
        `;
        document.getElementById("cancel-research-btn").onclick = () => cancelResearch(resumeName);

        // Auto-scroll if near bottom
        scrollToBottom();
    } else {
        statusBox.style.display = "none";
    }
}

async function handleResearchCompletion(resumeName) {
    try {
        const res = await authFetch(`${API_BASE}/agents/matches?resume_filename=${resumeName}`);
        if (!res.ok) return;

        const data = await res.json();
        addMessage("model", `✅ Research Complete! Found **${data.matches.length}** jobs.`);
        addJobCards(data.matches);

    } catch (e) {
        console.error("Failed to handle completion", e);
    }
}

function createStatusContainer() {
    // POSITIONING FIX: Create it inside messages container so it flows with chat
    const existing = document.getElementById("research-status-container");
    if (existing) return existing;

    const container = document.createElement("div");
    container.id = "research-status-container";
    container.className = "status-floater inline-status"; // Added inline-status class

    // Append to Messages Container at the bottom
    const messages = document.getElementById("messages-container");
    if (messages) {
        messages.appendChild(container);
    }
    return container;
}

async function cancelResearch(resumeName) {
    if (!confirm("Stop current research task?")) return;

    try {
        const res = await authFetch(`${API_BASE}/chat/research/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ resume_filename: resumeName, session_id: currentSessionId })
        });
        if (res.ok) {
            showLogInternal("🛑 Cancellation requested.", "warning");
        }
    } catch (e) {
        console.error("Cancel failed", e);
    }
}

// Replaces checkResearcherVisibility
// Called by initChatPage
async function checkResearcherVisibility() {
    // Just trigger the update logic which fetches profile
    try {
        const res = await authFetch(`${API_BASE}/profile`);
        const data = await res.json();
        updateResearchUI(data);
    } catch (e) { }
}

async function triggerResearch() {
    // Legacy support or fallback
    openSearchConfigModal();
}

function initSearchModal() {
    const modal = document.getElementById("search-modal");
    const closeBtn = document.querySelector(".close-search-modal");
    const confirmBtn = document.getElementById("confirm-search-btn");

    if (closeBtn && modal) {
        closeBtn.addEventListener("click", () => {
            modal.style.display = "none";
        });
    }

    if (confirmBtn) {
        // Remove old listeners
        const newBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
        newBtn.addEventListener("click", confirmSearch);
    }

    window.addEventListener("click", (event) => {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    });
}

async function openSearchConfigModal() {
    console.log("Opening Search Modal");
    const modal = document.getElementById("search-modal");
    const resumeSelect = document.getElementById("search-resume-select");
    if (!modal) return;

    // Load Resumes
    if (resumeSelect) {
        resumeSelect.innerHTML = '<option value="">Loading...</option>';
        try {
            const res = await authFetch(`${API_BASE}/resumes`);
            const resumes = await res.json();

            // Get Primary Resume
            const profileRes = await authFetch(`${API_BASE}/profile`);
            const profile = await profileRes.json();
            const primaryResume = profile.primary_resume_name;

            resumeSelect.innerHTML = '';
            if (resumes.length === 0) {
                resumeSelect.innerHTML = '<option value="">No resumes found</option>';
            } else {
                resumes.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.name;
                    opt.textContent = r.name;
                    if (r.name === primaryResume) opt.selected = true;
                    resumeSelect.appendChild(opt);
                });
            }
        } catch (e) {
            console.error("Error loading resumes for search modal", e);
            resumeSelect.innerHTML = '<option>Error loading context</option>';
        }
    }

    modal.style.display = "block";
}

async function confirmSearch() {
    console.log("Confirming search...");
    const titlesInput = document.getElementById("search-titles");
    const locationInput = document.getElementById("search-location");
    const limitInput = document.getElementById("search-limit");
    const resumeSelect = document.getElementById("search-resume-select");
    const modal = document.getElementById("search-modal");

    const titles = titlesInput.value.trim();
    const location = locationInput.value.trim();
    const limit = parseInt(limitInput.value) || 10;
    const resumeName = resumeSelect.value;

    if (!resumeName) {
        alert("Please select a resume context.");
        return;
    }

    // Close Modal
    modal.style.display = "none";

    // UX Feedback in Chat
    let msg = `Start Researcher with **${resumeName}**`;
    if (titles) msg += ` for **${titles}**`;
    if (location) msg += ` in **${location}**`;
    addMessage("user", msg);

    addMessage("model", `Starting research...`);

    // VISIBILITY FIX: Force UI to show "Searching" loop immediately before Fetch returns
    // This provides instant feedback and prevents "lag" before the button appears.
    const fakeProfile = {
        primary_resume_name: resumeName,
        profile_data: {
            research_status: {
                [resumeName]: { status: "SEARCHING", last_log: "Initializing..." }
            }
        }
    };
    updateResearchUI(fakeProfile);

    try {
        const payload = {
            resume_filename: resumeName,
            limit: limit,
            job_title: titles,
            location: location
        };

        const res = await authFetch(`${API_BASE}/agents/research`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const data = await res.json();
            // Force UI update to show searching state (redundant but safe)
            checkResearcherVisibility();

            if (data.session_id) {
                // We rely on updateResearchUI now, so we might not need this if the status container does the job.
                // But let's keep it if it adds a specific "Cancel" message block?
                // Actually the user wants the cancel button INLINE.
                // updateResearchUI handles the status box.
            }
        } else {
            console.error("Research start failed", await res.text());
            addMessage("model", "❌ Failed to start research.");
            checkResearcherVisibility(); // Reset UI
        }
    } catch (e) {
        console.error("Error confirmSearch:", e);
        addMessage("model", "❌ Error starting research.");
        checkResearcherVisibility(); // Reset UI
    }
}

// ==========================================
// PROFILE PAGE LOGIC
// ==========================================
async function initProfilePage() {
    const resumeSelect = document.getElementById("primary-resume-select");
    const autoFillBtn = document.getElementById("parse-btn");

    // Store current profile for merging later
    let currentProfile = {};

    // Load current profile
    try {
        const res = await authFetch(`${API_BASE}/profile`);
        const user = await res.json();
        currentProfile = user.profile_data || {};

        // Fill form fields
        if (user.profile_data) {
            const p = user.profile_data;
            const map = {
                "full_name": p.name || user.full_name,
                "phone": p.phone,
                "linkedin": p.linkedin,
                "portfolio": p.portfolio,
                "address": p.address,
                "summary": p.summary,
                "skills": p.skills ? p.skills.join(", ") : "",
                "salary_expectations": p.salary_expectations,
                "race": p.race,
                "veteran": p.veteran,
                "disability": p.disability,
                "authorization": p.authorization
            };

            for (let id in map) {
                const el = document.getElementById(id);
                if (el && map[id]) el.value = map[id];
            }

            // Render Experience
            const expContainer = document.getElementById("experience-list");
            if (expContainer && p.experience && p.experience.length > 0) {
                expContainer.innerHTML = p.experience.map(e => `
                    <div class="experience-card">
                        <div class="card-header">
                            <strong class="card-title">${e.title || 'Role'}</strong>
                            <span class="card-meta">${e.duration || ''}</span>
                        </div>
                        <div class="card-subtitle">${e.company || 'Company'}</div>
                        <p class="card-body">${e.responsibilities || ''}</p>
                    </div>
                `).join("");
            }

            // Render Education
            const eduContainer = document.getElementById("education-list");
            if (eduContainer && p.education && p.education.length > 0) {
                eduContainer.innerHTML = p.education.map(e => `
                    <div class="experience-card">
                        <div class="card-header">
                            <strong class="card-title">${e.school || 'School'}</strong>
                            <span class="card-subtitle">${e.date || ''}</span>
                        </div>
                        <div class="card-body">${e.degree || 'Degree'}</div>
                    </div>
                `).join("");
            }
        }

        // Populate Resume Dropdown
        // Note: Currently no endpoint lists all resumes separately?
        // We can just add the primary one if we don't have a list endpoint.
        // Assuming we rely on primary_resume_name for now.
        if (user.primary_resume_name) {
            resumeSelect.innerHTML = "";
            const opt = document.createElement("option");
            opt.value = user.primary_resume_name;
            opt.textContent = user.primary_resume_name + " (Primary)";
            opt.selected = true;
            resumeSelect.appendChild(opt);
        } else {
            resumeSelect.innerHTML = "<option>No resumes found</option>";
        }

    } catch (e) { console.error(e); }

    if (autoFillBtn) {
        autoFillBtn.addEventListener("click", async (e) => {
            e.preventDefault();

            const resumeSelect = document.getElementById("primary-resume-select");
            const selectedResume = resumeSelect.value;

            if (!selectedResume) {
                alert("Please select a resume first.");
                return;
            }

            autoFillBtn.disabled = true;
            autoFillBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Parsing...';

            try {
                const res = await authFetch(`${API_BASE}/profile/parse`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ resume_path: selectedResume })
                });

                if (res.ok) {
                    // Reload the page to show updated data
                    window.location.reload();
                } else {
                    alert("Failed to parse resume. Please try again.");
                }
            } catch (e) {
                console.error("Parse error:", e);
                alert("Error parsing resume.");
            } finally {
                autoFillBtn.disabled = false;
                autoFillBtn.innerHTML = '<i class="fas fa-magic"></i> Auto-Fill from Resume';
            }
        });
    }

    // Handle Profile Form Submission
    const profileForm = document.getElementById("profile-form");
    if (profileForm) {
        profileForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const saveBtn = document.getElementById("save-btn");
            const statusMsg = document.getElementById("status-msg");

            // Collect form data and merge with existing profile data
            const formData = {
                full_name: document.getElementById("full_name")?.value || "",
                profile_data: {
                    ...currentProfile, // MERGE existing data (experience, education, etc.)
                    name: document.getElementById("full_name")?.value || "",
                    phone: document.getElementById("phone")?.value || "",
                    linkedin: document.getElementById("linkedin")?.value || "",
                    portfolio: document.getElementById("portfolio")?.value || "",
                    address: document.getElementById("address")?.value || "",
                    summary: document.getElementById("summary")?.value || "",
                    skills: document.getElementById("skills")?.value ?
                        document.getElementById("skills").value.split(",").map(s => s.trim()) : [],
                    salary_expectations: document.getElementById("salary_expectations")?.value || "",
                    race: document.getElementById("race")?.value || "",
                    veteran: document.getElementById("veteran")?.value || "",
                    disability: document.getElementById("disability")?.value || "",
                    authorization: document.getElementById("authorization")?.value || ""
                }
            };

            // Disable button
            saveBtn.disabled = true;
            saveBtn.textContent = "Saving...";

            try {
                const res = await authFetch(`${API_BASE}/profile`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(formData)
                });

                if (res.ok) {
                    statusMsg.innerHTML = '<span style="color: var(--accent-color);">✅ Profile saved successfully!</span>';
                    setTimeout(() => statusMsg.innerHTML = "", 3000);
                } else {
                    statusMsg.innerHTML = '<span style="color: #ff6b6b;">❌ Failed to save profile</span>';
                }
            } catch (e) {
                console.error("Save error:", e);
                statusMsg.innerHTML = '<span style="color: #ff6b6b;">❌ Error saving profile</span>';
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = "Save Changes";
            }
        });
    }
}

async function triggerApply(url, title, mode = null) {
    console.log("Triggering Apply:", url, title);
    // If no mode specified, prompt user for choice
    if (!mode) {
        console.log("Prompting for mode...");
        const choice = await showApplyModeModal(url, title);
        if (!choice) {
            console.log("Apply cancelled by user");
            return;
        }
        mode = choice;
    }

    addMessage("user", `Apply to ${title} (${mode === 'cloud' ? '☁️ Cloud' : '💻 Local'})`);
    addMessage("model", `Starting Application using ${mode === 'cloud' ? 'Browser Use Cloud' : 'Local Browser'}...`);

    try {
        const res = await authFetch(`${API_BASE}/agents/apply`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_url: url, mode: mode })
        });

        if (res.ok) {
            const data = await res.json();
            let msg = "✅ Application started.";
            if (data.session_url) {
                msg += `\n\n🔗 **Watch Live**: [View Session](${data.session_url})`;
            }
            addMessage("model", msg);

            if (data.session_id) {
                addCancelButtonMessage(data.session_id);
            }
        } else {
            console.error("Apply start failed", await res.text());
            addMessage("model", "❌ Failed to start application.");
        }
    } catch (e) {
        console.error("Error triggering apply", e);
        addMessage("model", "❌ Error starting application.");
    }
}

// Mode selection modal for Applier Agent
function showApplyModeModal(url, title) {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.display = 'block';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 420px;">
                <div class="modal-header">
                    <h3>Choose Execution Mode</h3>
                    <span class="close-modal">&times;</span>
                </div>
                <div class="modal-body" style="text-align: center; padding: 20px;">
                    <p style="margin-bottom: 20px;">How would you like to run the Applier Agent for <strong>${title}</strong>?</p>
                    <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
                        <button id="mode-local-btn" class="chip" style="padding: 12px 20px; font-size: 0.9rem;">
                            💻 Local
                        </button>
                        <button id="mode-browser-use-btn" class="chip" style="padding: 12px 20px; font-size: 0.9rem; background: linear-gradient(135deg, #FF8008, #FFC837); color: #000;">
                            🌐 Browser Use
                        </button>
                        <button id="mode-cloud-btn" class="chip" style="padding: 12px 20px; font-size: 0.9rem; background: linear-gradient(135deg, #667eea, #764ba2);">
                            ☁️ Google Cloud
                        </button>
                    </div>
                    <div style="margin-top: 15px; font-size: 0.85rem; color: var(--text-secondary); text-align: left; line-height: 1.4;">
                        <p style="margin-bottom: 5px;"><i class="fas fa-desktop"></i> <strong>Local:</strong> Runs on your machine (Docker/Terminal).</p>
                        <p style="margin-bottom: 5px;"><i class="fas fa-globe"></i> <strong>Browser Use:</strong> Managed Cloud Browser (Stealthy).</p>
                        <p style="margin: 0;"><i class="fas fa-cloud"></i> <strong>Google Cloud:</strong> Fully autonomous background worker.</p>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const close = () => { modal.remove(); resolve(null); };
        modal.querySelector('.close-modal').onclick = close;
        modal.onclick = (e) => { if (e.target === modal) close(); };

        modal.querySelector('#mode-local-btn').onclick = () => { modal.remove(); resolve('local'); };
        modal.querySelector('#mode-browser-use-btn').onclick = () => { modal.remove(); resolve('browser_use'); };
        modal.querySelector('#mode-cloud-btn').onclick = () => { modal.remove(); resolve('cloud'); };
    });
}

function addJobCards(jobs) {
    const template = document.getElementById("job-card-template");
    if (!template) return;

    const listDiv = document.createElement("div");
    listDiv.className = "job-list-container";

    jobs.forEach(job => {
        const clone = template.content.cloneNode(true);
        clone.querySelector(".job-title").textContent = job.title;
        clone.querySelector(".job-company").textContent = job.company;
        clone.querySelector(".match-score").textContent = job.match_score + "% Match";

        const viewBtn = clone.querySelector(".view-btn");
        viewBtn.href = job.url;

        const applyBtn = clone.querySelector(".apply-btn");
        applyBtn.onclick = () => triggerApply(job.url, job.title);

        listDiv.appendChild(clone);
    });

    const container = document.getElementById("messages-container");
    const msgDiv = document.createElement("div");
    msgDiv.className = "message bot-message";
    const avatarDiv = document.createElement("div");
    avatarDiv.className = "avatar";
    avatarDiv.innerHTML = '<i class="fas fa-robot"></i>';

    const contentDiv = document.createElement("div");
    contentDiv.className = "content";
    contentDiv.innerHTML = "<p>Here are the top matches I found:</p>";
    contentDiv.appendChild(listDiv);

    msgDiv.appendChild(avatarDiv);
    msgDiv.appendChild(contentDiv);
    container.appendChild(msgDiv);
    scrollToBottom();
}

// pollResearchStatus removed in favor of Realtime updates via updateResearchUI


// --- Attach Resume Logic ---
function initAttachResume() {
    const attachBtn = document.getElementById("attach-resume-btn");
    const modal = document.getElementById("resume-modal");
    const closeSpan = document.querySelector(".close-modal");

    if (attachBtn && modal) {
        attachBtn.addEventListener("click", () => {
            modal.style.display = "block";
            loadResumesForModal();
        });
    }

    if (closeSpan && modal) {
        closeSpan.addEventListener("click", () => {
            modal.style.display = "none";
        });
    }

    // Close on outside click
    window.addEventListener("click", (event) => {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    });
}

async function loadResumesForModal() {
    const listContainer = document.getElementById("resume-list-container");
    listContainer.innerHTML = "<p>Loading...</p>";

    try {
        const resumesRes = await authFetch(`${API_BASE}/resumes`);
        const resumes = await resumesRes.json();

        // Fetch Current Profile to see active one
        const profileRes = await authFetch(`${API_BASE}/profile`);
        const profile = await profileRes.json();
        const currentResume = profile.primary_resume_name;

        listContainer.innerHTML = "";

        if (!Array.isArray(resumes) || resumes.length === 0) {
            listContainer.innerHTML = "<p>No resume found. Upload one first!</p>";
            return;
        }

        resumes.forEach(r => {
            const div = document.createElement("div");
            div.className = "resume-option";
            if (r.name === currentResume) {
                div.classList.add("active-resume");
            }

            const nameSpan = document.createElement("span");
            nameSpan.className = "resume-name";
            nameSpan.textContent = r.name;

            const metaSpan = document.createElement("span");
            metaSpan.className = "resume-meta";
            // Format Date
            const date = r.created_at ? new Date(r.created_at).toLocaleDateString() : "";
            metaSpan.textContent = date;

            div.appendChild(nameSpan);
            div.appendChild(metaSpan);

            div.onclick = () => selectResume(r.name);

            listContainer.appendChild(div);
        });

    } catch (e) {
        console.error(e);
        listContainer.innerHTML = "<p>Error loading resumes.</p>";
    }
}

async function selectResume(filename) {
    const modal = document.getElementById("resume-modal");
    if (modal) modal.style.display = "none";

    addMessage("user", `Switched context to **${filename}**`);
    addMessage("model", "Updating context...");

    try {
        const res = await authFetch(`${API_BASE}/profile`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ primary_resume_name: filename })
        });

        if (res.ok) {
            addMessage("model", `✅ Context updated. I am now using **${filename}**.`);
            checkResearcherVisibility();
        } else {
            addMessage("model", "❌ Failed to update context.");
        }
    } catch (e) {
        console.error(e);
        addMessage("model", "❌ Error updating context.");
    }
}

// --- Jobs Page Logic ---
async function initJobsPage() {
    initInfoModal(); // Initialize modal listeners
    const resumeSelect = document.getElementById("resume-filter");
    const refreshBtn = document.getElementById("refresh-jobs-btn");

    // Inject Email into Sidebar (Handled by checkAuth now)
    // await loadUserInfo();

    // Load Resumes into Filter
    try {
        const res = await authFetch(`${API_BASE}/resumes`);
        const resumes = await res.json();

        resumeSelect.innerHTML = "";

        // Option: All Resumes? Or select primary
        // Use cached profile if available
        let profile = window.currentUserProfile;
        if (!profile) {
            const profRes = await authFetch(`${API_BASE}/profile`);
            profile = await profRes.json();
            window.currentUserProfile = profile;
        }

        const primary = profile.primary_resume_name;

        if (resumes.length === 0) {
            resumeSelect.innerHTML = "<option>No resumes found</option>";
            return;
        }

        resumes.forEach(r => {
            const opt = document.createElement("option");
            opt.value = r.name;
            opt.textContent = r.name;
            if (r.name === primary) opt.selected = true;
            resumeSelect.appendChild(opt);
        });

        // Load Jobs for Initial Selection
        loadJobs(resumeSelect.value);

    } catch (e) {
        console.error("Error loading resumes for filter", e);
        resumeSelect.innerHTML = "<option>Error loading context</option>";
    }

    // Listeners
    resumeSelect.addEventListener("change", (e) => {
        loadJobs(e.target.value);
    });

    const sortSelect = document.getElementById("sort-jobs");
    if (sortSelect) {
        sortSelect.addEventListener("change", () => {
            loadJobs(resumeSelect.value);
        });
    }

    refreshBtn.addEventListener("click", () => {
        loadJobs(resumeSelect.value);
    });
}

async function loadUserInfo() {
    try {
        const res = await authFetch(`${API_BASE}/auth/me`);
        if (!res.ok) return;
        const user = await res.json();

        const userEmailDisplay = document.getElementById("user-email-display");
        if (userEmailDisplay) userEmailDisplay.textContent = user.email;
    } catch (e) {
        console.error("Failed to load user info", e);
    }
}

async function loadJobs(resumeName) {
    const container = document.getElementById("jobs-container");
    const sortSelect = document.getElementById("sort-jobs");
    const sortBy = sortSelect ? sortSelect.value : "match_desc";

    container.innerHTML = "<p style='text-align:center;'>Loading leads...</p>";

    if (!resumeName) return;

    try {
        const url = `${API_BASE}/leads/?resume=${encodeURIComponent(resumeName)}`;
        const res = await authFetch(url);
        const data = await res.json();

        container.innerHTML = "";

        if (!data.leads || data.leads.length === 0) {
            container.innerHTML = "<p style='text-align:center; color:gray;'>No leads found for this resume context.</p>";
            return;
        }

        // --- SORTING LOGIC ---
        let leads = [...data.leads];
        leads.sort((a, b) => {
            if (sortBy === "match_desc") {
                return (b.match_score || 0) - (a.match_score || 0);
            } else if (sortBy === "date_desc") {
                return new Date(b.created_at) - new Date(a.created_at);
            } else if (sortBy === "date_asc") {
                return new Date(a.created_at) - new Date(b.created_at);
            } else if (sortBy === "status") {
                // simple alphabetical sort for status, or custom weight
                // Let's favor APPLIED > IN_PROGRESS > NEW > FAILED?
                const weights = { "APPLIED": 4, "IN_PROGRESS": 3, "NEW": 2, "FAILED": 1 };
                return (weights[b.status] || 0) - (weights[a.status] || 0);
            }
            return 0;
        });

        leads.forEach(lead => {
            const div = document.createElement("div");
            div.className = "job-item";

            // Determine Status Color
            let statusClass = "status-new";
            if (lead.status === "APPLIED") statusClass = "status-applied";
            if (lead.status === "IN_PROGRESS") statusClass = "status-in-progress"; // Ensure we have CSS for this or fallback
            // Note: If no 'status-in-progress' class exists, it might fall back to default text color.
            // We can just add inline style or verify css later.

            // Format Date
            const dateStr = lead.created_at ? new Date(lead.created_at).toLocaleDateString() : "Unknown Date";

            div.innerHTML = `
                <div class="job-main-info">
                    <h3>${lead.title}</h3>
                    <p>${lead.company}</p>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 5px;">
                        <i class="far fa-calendar-alt"></i> Found: ${dateStr}
                    </div>
                </div>
                <div class="job-meta">
                    <span class="match-score">${lead.match_score}% Match</span>
                    <span class="status-pill ${statusClass}">${lead.status}</span>
                    <div class="actions" style="display: flex; gap: 10px; align-items: center;">
                        <a href="${lead.url}" target="_blank" style="color: var(--text-secondary); font-size: 1.1rem; padding: 4px;" title="View Job">
                            <i class="fas fa-external-link-alt"></i>
                        </a>
                        <button class="info-btn" style="background: none; border: none; color: var(--text-secondary); font-size: 1.1rem; cursor: pointer; padding: 4px;" title="Match Reasoning">
                            <i class="fas fa-info-circle"></i>
                        </button>
                        <button class="delete-btn" style="background: none; border: none; color: #ff6b6b; font-size: 1.1rem; cursor: pointer; padding: 4px;" title="Delete Lead">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="apply-chat-btn" data-lead-id="${lead.id}" style="padding: 6px 16px; font-size: 0.8rem; background: var(--accent-color); color: #000; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 5px;">
                            Apply <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>
            `;

            // Add click handler for Apply button
            const applyBtn = div.querySelector('.apply-chat-btn');
            if (applyBtn) {
                applyBtn.addEventListener('click', function (e) {
                    e.preventDefault();
                    try {
                        openApplyModal(lead, resumeName);
                    } catch (err) {
                        console.error("Error opening apply modal:", err);
                        alert("Error opening apply modal: " + err.message);
                    }
                });
            }

            // Info Button
            const infoBtn = div.querySelector('.info-btn');
            if (infoBtn) {
                infoBtn.addEventListener('click', () => openInfoModal(lead));
            }

            // Delete Button
            const deleteBtn = div.querySelector('.delete-btn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', () => {
                    if (confirm(`Are you sure you want to delete "${lead.title}"?`)) {
                        deleteLead(lead.id, div);
                    }
                });
            }

            container.appendChild(div);
        });

    } catch (e) {
        console.error("Error loading jobs", e);
        container.innerHTML = "<p style='text-align:center;'>Error loading leads.</p>";
    }
}

async function deleteLead(leadId, rowElement) {
    try {
        const res = await authFetch(`${API_BASE}/leads/${leadId}`, {
            method: "DELETE"
        });
        if (res.ok) {
            rowElement.remove();
            // Optional: Show toast
        } else {
            alert("Failed to delete lead.");
        }
    } catch (e) {
        console.error("Error deleting lead:", e);
        alert("Error deleting lead.");
    }
}

function initInfoModal() {
    const modal = document.getElementById("info-modal");
    const closeBtn = document.querySelector(".close-info-modal");

    if (closeBtn && modal) {
        closeBtn.onclick = () => modal.style.display = "none";
    }

    if (modal) {
        window.addEventListener("click", (event) => {
            if (event.target == modal) {
                modal.style.display = "none";
            }
        });
    }
}

function openInfoModal(lead) {
    const modal = document.getElementById("info-modal");
    const content = document.getElementById("info-modal-content");

    if (!modal || !content) return;

    // Format reasoning with basic markdown-like rendering if needed, 
    // but for now just text or simple replacement
    let reasoning = lead.match_reason || "No reasoning available.";
    // Simple bolding of sections usually returned by LLM
    reasoning = reasoning.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    reasoning = reasoning.replace(/\n/g, '<br>');

    content.innerHTML = `
        <h4 style="color: var(--accent-color); margin-top:0;">${lead.title} @ ${lead.company}</h4>
        <p>${reasoning}</p>
    `;

    modal.style.display = "block";
}

// ==========================================
// MENTION SYSTEM & UNIFIED APPLY MODAL
// ==========================================

let availableLeads = [];

async function fetchLeadsForMentions() {
    try {
        // Get active resume context
        const profileRes = await authFetch(`${API_BASE}/profile`);
        const profile = await profileRes.json();
        const resumeName = profile.primary_resume_name;

        if (!resumeName) return;

        // Fetch leads from DB for this resume
        const url = `${API_BASE}/leads/?resume=${encodeURIComponent(resumeName)}`;
        const res = await authFetch(url);
        const data = await res.json();

        if (data.leads) {
            availableLeads = data.leads;
        }
    } catch (e) {
        console.error("Failed to fetch leads for mentions", e);
    }
}

function initMentionSystem() {
    const chatInput = document.getElementById("chat-input");
    if (!chatInput) return;

    // Create Dropdown Element
    let dropdown = document.createElement("div");
    dropdown.className = "mention-dropdown";
    dropdown.id = "mention-dropdown";

    // Convert to relative positioning wrapper if needed, but absolute fixed to input area is easier
    // For now, let's append to the input-area-wrapper
    const wrapper = document.querySelector(".input-area-wrapper");
    if (wrapper) {
        wrapper.style.position = "relative";
        wrapper.appendChild(dropdown);
    } else {
        document.body.appendChild(dropdown);
    }

    // Refresh leads on load
    fetchLeadsForMentions();

    chatInput.addEventListener("keyup", (e) => {
        const val = chatInput.value;
        const cursorMoved = e.key === "ArrowLeft" || e.key === "ArrowRight";

        // Detect @ symbol
        const atIndex = val.lastIndexOf("@");

        if (atIndex !== -1 && !val.substring(atIndex).includes(" ")) {
            // User is typing a mention
            const query = val.substring(atIndex + 1).toLowerCase();
            showMentionDropdown(query, atIndex);
        } else {
            dropdown.style.display = "none";
        }
    });

    // Intercept Enter processing in the main sendMessage function, 
    // BUT we also need to handle Enter for selecting a mention
    chatInput.addEventListener("keydown", (e) => {
        if (dropdown.style.display === "block" && (e.key === "Enter" || e.key === "Tab")) {
            e.preventDefault();
            e.stopPropagation();
            selectMention();
        }
    });
}

function showMentionDropdown(query, atIndex) {
    const dropdown = document.getElementById("mention-dropdown");
    if (!dropdown) return;

    // Filter leads
    const matches = availableLeads.filter(l =>
        l.title.toLowerCase().includes(query) ||
        l.company.toLowerCase().includes(query)
    ).slice(0, 5);

    if (matches.length === 0) {
        dropdown.style.display = "none";
        return;
    }

    dropdown.innerHTML = "";
    matches.forEach((lead, index) => {
        const item = document.createElement("div");
        item.className = "mention-item";
        if (index === 0) item.classList.add("active");

        item.innerHTML = `
            <div class="mention-title">${lead.title}</div>
            <div class="mention-company">${lead.company}</div>
        `;

        item.onclick = () => insertMention(lead);
        dropdown.appendChild(item);
    });

    dropdown.style.display = "block";
    dropdown.dataset.atIndex = atIndex;
}

function selectMention() {
    const dropdown = document.getElementById("mention-dropdown");
    const activeItem = dropdown.querySelector(".mention-item.active"); // Or first
    if (activeItem) activeItem.click();
}

function insertMention(lead) {
    const chatInput = document.getElementById("chat-input");
    const dropdown = document.getElementById("mention-dropdown");
    const atIndex = parseInt(dropdown.dataset.atIndex);

    const before = chatInput.value.substring(0, atIndex);
    // STRUCTURE: Apply to @Job Title at Company
    // We insert just the Title but we might want to store the URL?
    // For natural language parsing, "Apply to @Title" is fine, we look it up later.
    const mentionText = `@${lead.title} at ${lead.company} `;

    chatInput.value = before + mentionText;
    chatInput.focus();
    dropdown.style.display = "none";

    // Store context for this specific input flow?
    // We can lookup by title later or set a global "pendingContext"
    window.lastMentionedJob = lead;
}


// --- Updated Interception Logic ---

// We need to Hook into the existing sendMessage function or replace it.
// Since sendMessage is defined earlier, we can overwrite it or modify the event listener.
// A cleaner way is to keep sendMessage as is, but add a check at the top of it.
// However, since `sendMessage` is defined in this file, we can just modify it IN PLACE using `replace_file_content`.
// BUT, `script.js` is one big file. I am replacing the end, so I can't easily modify the middle `sendMessage` function without a separate call.
// So I will override `sendMessage` here at the end. Javascript allows re-definition if using `function` keyword (hoisting) or just assignment.
// `sendMessage` was defined as `async function sendMessage`. Re-defining it here overrides the previous one.

const originalSendMessage = sendMessage;

sendMessage = async function () {
    const chatInput = document.getElementById("chat-input");
    const text = chatInput.value.trim();

    // Regex to detect "Apply to @..." command
    if (text.toLowerCase().startsWith("apply to @")) {
        try {
            console.log("Intercepted Apply Command:", text);

            // Try to identify the job
            // 1. Check window.lastMentionedJob (most reliable if user clicked dropdown)
            let job = window.lastMentionedJob;

            // 2. If not set, try to fuzzy match from text
            if (!job && Array.isArray(availableLeads)) {
                let raw = text.substring(9).trim(); // Remove "apply to @" and trim

                // Try Exact Match first (case-insensitive)
                job = availableLeads.find(l => l.title && l.title.toLowerCase() === raw.toLowerCase());

                // Fallback to fuzzy includes
                if (!job) {
                    job = availableLeads.find(l => l.title && raw.toLowerCase().includes(l.title.toLowerCase()));
                }
            }

            if (job) {
                console.log("Job identified for apply:", job);

                // Clear input first to show we consumed it
                chatInput.value = "";
                chatInput.style.height = "auto";

                // Get Resume Context
                let resumeName = null;
                try {
                    const profileRes = await authFetch(`${API_BASE}/profile`);
                    if (profileRes.ok) {
                        const profile = await profileRes.json();
                        resumeName = profile.primary_resume_name;
                    }
                } catch (pe) {
                    console.warn("Could not fetch profile for resume context", pe);
                }

                await openApplyModal(job, resumeName);
                return;
            } else {
                console.warn("Could not identify job from text:", text);
                // Optional: Show toast "Could not find job"? 
                // For now, let it fall through or maybe just alert?
                // Falling through means it goes to Chat LLM, which might be fine.
            }
        } catch (e) {
            console.error("Error in Apply Interception:", e);
            alert("Unexpected error opening apply modal. Check console.");
            // Fallback: Restore text so they can try again or send as normal message
            chatInput.value = text;
        }
    }

    // Fallback to normal message
    await originalSendMessage();
};


// ==========================================
// APPLY MODAL LOGIC (Unified)
// ==========================================

// Initialize Apply Modal
function initApplyModal() {
    // If modal HTML doesn't exist (Chat Page), inject it
    if (!document.getElementById('apply-modal')) {
        injectApplyModalHtml();
    }

    const modal = document.getElementById('apply-modal');
    const closeBtn = modal.querySelector('.close-apply-modal');
    const confirmBtn = document.getElementById('apply-confirm-btn');
    const uploadBtn = document.getElementById('apply-upload-btn');
    const uploadInput = document.getElementById('apply-resume-upload');

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });

    if (confirmBtn) {
        // Remove old listeners to avoid duplicates if re-init
        const newBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
        newBtn.addEventListener('click', confirmApplyToChat);
    }

    if (uploadBtn && uploadInput) {
        // Same for upload
        const newUpBtn = uploadBtn.cloneNode(true);
        uploadBtn.parentNode.replaceChild(newUpBtn, uploadBtn);
        const newUpInput = uploadInput.cloneNode(true);
        uploadInput.parentNode.replaceChild(newUpInput, uploadInput);

        newUpBtn.addEventListener('click', () => newUpInput.click());
        newUpInput.addEventListener('change', handleApplyResumeUpload);
    }
}

function injectApplyModalHtml() {
    const modalHtml = `
    <div id="apply-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Apply Configuration</h3>
                <span class="close-apply-modal">&times;</span>
            </div>
            <div class="modal-body">
                <div id="apply-job-info" style="margin-bottom: 20px; padding: 15px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                    <h4 id="apply-job-title" style="margin: 0 0 5px 0; color: var(--accent-color);"></h4>
                    <p id="apply-job-company" style="margin: 0; color: var(--text-secondary); font-size: 0.9rem;"></p>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 0.9rem;">Select Resume</label>
                    <select id="apply-resume-select" style="width: 100%; padding: 10px; border-radius: 6px; background: var(--input-bg); color: var(--text-primary); border: 1px solid var(--border-color);"></select>
                </div>
                
                 <!-- Upload New Resume Option -->
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 0.9rem;">
                        Or upload a new resume
                    </label>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <input type="file" id="apply-resume-upload" accept=".pdf,.docx" style="display: none;">
                        <button id="apply-upload-btn" class="chip" style="margin: 0;">
                            <i class="fas fa-upload"></i> Upload New
                        </button>
                        <span id="apply-upload-status" style="font-size: 0.85rem; color: var(--text-secondary);"></span>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 0.9rem;">Execution Mode</label>
                    <div style="display: flex; gap: 15px; flex-direction: column;">
                         <!-- Option 1: Browser Use Cloud (Managed) -->
                        <label style="display: flex; align-items: flex-start; cursor: pointer; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 6px;">
                            <input type="radio" name="execution-mode" value="browser_use_cloud" style="margin-right: 12px; margin-top: 4px;">
                            <div>
                                <span style="display:block; color: var(--text-primary); font-weight: 500;">Browser Use Cloud</span>
                                <span style="display:block; font-size: 0.8rem; color: var(--text-secondary); margin-top: 3px;">
                                    Uses managed cloud browser. View live stream on dashboard.
                                </span>
                            </div>
                        </label>

                        <!-- Option 2: Google Cloud Run (Self-Hosted) -->
                        <label style="display: flex; align-items: flex-start; cursor: pointer; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 6px;">
                            <input type="radio" name="execution-mode" value="cloud_run" checked style="margin-right: 12px; margin-top: 4px;">
                            <div>
                                <span style="display:block; color: var(--text-primary); font-weight: 500;">Google Cloud Run (Recommended)</span>
                                <span style="display:block; font-size: 0.8rem; color: var(--text-secondary); margin-top: 3px;">
                                    Runs on your specific Cloud Run instance. View live stream in chat.
                                </span>
                            </div>
                        </label>

                        <!-- Option 3: Local -->
                        <label style="display: flex; align-items: flex-start; cursor: pointer; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 6px;">
                            <input type="radio" name="execution-mode" value="local" style="margin-right: 12px; margin-top: 4px;">
                            <div>
                                <span style="display:block; color: var(--text-primary); font-weight: 500;">Local Machine</span>
                                <span style="display:block; font-size: 0.8rem; color: var(--text-secondary); margin-top: 3px;">
                                    Runs invisibly on your machine (Headless) or visible if configured.
                                </span>
                            </div>
                        </label>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 0.9rem;">Additional Instructions</label>
                    <textarea id="apply-instructions" placeholder="e.g., Highlight my Python experience..." style="width: 100%; min-height: 80px; padding: 10px; border-radius: 6px; background: var(--input-bg); color: var(--text-primary); border: 1px solid var(--border-color); font-family: inherit;"></textarea>
                </div>

                <button id="apply-confirm-btn" style="width: 100%; padding: 12px; background: var(--accent-color); color: #000; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 1rem;">
                    <i class="fas fa-paper-plane"></i> Start Application
                </button>
            </div>
        </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Handle Resume Upload inside Apply Modal
async function handleApplyResumeUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const statusEl = document.getElementById("apply-upload-status");
    if (statusEl) statusEl.textContent = "Uploading...";

    const formData = new FormData();
    formData.append("file", file);

    const token = localStorage.getItem("token");
    try {
        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });

        if (res.ok) {
            if (statusEl) statusEl.innerHTML = '<span style="color: var(--accent-color);">✅ Uploaded!</span>';

            // Refresh the select dropdown
            const resumeSelect = document.getElementById('apply-resume-select');
            if (resumeSelect) {
                // Add new option and select it
                const opt = document.createElement('option');
                opt.value = file.name;
                opt.textContent = file.name;
                opt.selected = true;
                resumeSelect.appendChild(opt);
                // Ideally we should re-fetch all to ensure order/metadata, but this is faster feedback
            }
        } else {
            if (statusEl) statusEl.textContent = "❌ Upload failed.";
        }
    } catch (e) {
        console.error("Apply upload failed", e);
        if (statusEl) statusEl.textContent = "❌ Error uploading.";
    }
}

// Open Apply Modal with job data
async function openApplyModal(lead, contextResumeName) {
    // console.log("openApplyModal called with:", lead, contextResumeName);
    // Ensure initialized
    initApplyModal();

    const modal = document.getElementById('apply-modal');
    const titleEl = document.getElementById('apply-job-title');
    const companyEl = document.getElementById('apply-job-company');
    const resumeSelect = document.getElementById('apply-resume-select');
    const instructionsEl = document.getElementById('apply-instructions');

    // Store lead data
    window.pendingApplyJob = {
        title: lead.title,
        company: lead.company,
        url: lead.url, // Ensure we have URL
        contextResume: contextResumeName
    };

    if (titleEl) titleEl.textContent = lead.title;
    if (companyEl) companyEl.textContent = lead.company;
    if (instructionsEl) instructionsEl.value = '';

    // Load Resumes
    if (resumeSelect) {
        resumeSelect.innerHTML = '<option value="">Loading...</option>';
        try {
            const res = await authFetch(`${API_BASE}/resumes`);
            const resumes = await res.json();
            resumeSelect.innerHTML = '';
            if (resumes.length === 0) {
                resumeSelect.innerHTML = '<option value="">No resumes found</option>';
            } else {
                resumes.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.name;
                    opt.textContent = r.name;
                    if (r.name === contextResumeName) opt.selected = true;
                    resumeSelect.appendChild(opt);
                });
            }
        } catch (e) {
            resumeSelect.innerHTML = '<option>Error loading resumes</option>';
        }
    }

    modal.style.display = 'block';
}

// Confirm Apply
async function confirmApplyToChat() {
    const job = window.pendingApplyJob;
    if (!job) return;

    const resumeSelect = document.getElementById('apply-resume-select');
    const instructionsEl = document.getElementById('apply-instructions');

    const selectedResume = resumeSelect.value;
    const instructions = instructionsEl.value.trim();

    let selectedMode = 'cloud_run';
    document.getElementsByName('execution-mode').forEach(rad => {
        if (rad.checked) selectedMode = rad.value;
    });

    if (!selectedResume) {
        alert("Please select a resume");
        return;
    }

    // Close Modal
    document.getElementById('apply-modal').style.display = 'none';

    // Map mode to label
    const modeLabels = {
        'cloud_run': '☁️ Cloud Run',
        'browser_use_cloud': '🌐 Browser Use Cloud',
        'local': '💻 Local'
    };
    const modeLabel = modeLabels[selectedMode] || selectedMode;

    // TRIGGER THE AGENT directly via API
    addMessage("user", `Apply to ${job.title} (${modeLabel})`);
    addMessage("model", `Starting Application...`);

    try {
        const payload = {
            job_url: job.url,
            mode: selectedMode,
            resume_filename: selectedResume,
            instructions: instructions
        };

        const res = await authFetch(`${API_BASE}/agents/apply`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const data = await res.json();
            let msg = "✅ Application started.";
            if (data.session_url) msg += `\n\n🔗 [Watch Live](${data.session_url})`;

            // If we are on CHAT page, just add message
            // If we are on JOBS page (or other), REDIRECT to CHAT page with session_id
            if (data.session_id) {
                const currentPath = window.location.pathname;
                if (currentPath === "/" || currentPath.includes("index.html")) {
                    // We are on chat page, just ensuring we are on correct session?
                    // Usually initApplyModal is global. 
                    // If we started a NEW session (which this API does typically if not passed), we should switch to it.
                    // The API /agents/apply creates a session if we passed one? 
                    // Wait, confirmApplyToChat logic doesn't pass session_id in payload above!
                    // The API creates a NEW session if one isn't passed? run_applier_task takes session_id.
                    // Check /agents/apply endpoint. It creates a new one!

                    addCancelButtonMessage(data.session_id);
                    loadSession(data.session_id);
                } else {
                    // Redirect
                    window.location.href = `/?session_id=${data.session_id}`;
                }
            } else {
                addMessage("model", msg);
            }

        } else {
            addMessage("model", "❌ Failed to start application.");
        }
    } catch (e) {
        console.error(e);
        addMessage("model", "❌ Error starting application.");
    }
}

// End of script
