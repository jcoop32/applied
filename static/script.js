// Main Entry for Chat Page (index.html) and Profile Page (profile.html)
let currentSessionId = null;

document.addEventListener("DOMContentLoaded", () => {
    // Determine if we are on index or profile
    const isProfilePage = !!document.getElementById("profile-form");

    // Auth Check runs on both
    checkAuth().then(() => {
        if (!isProfilePage) {
            initChatPage();
        } else {
            initProfilePage();
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
        const savedSessionId = localStorage.getItem('currentChatSessionId');
        if (savedSessionId) {
            loadSession(savedSessionId);
        }
    });

    // Check Researcher Visibility
    checkResearcherVisibility();

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

    // Expose global actions
    window.triggerResearch = triggerResearch;
    window.triggerApply = triggerApply;

    initMentionSystem();
    initAttachResume();

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
    loadSessions();

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
    } catch (e) {
        console.error(e);
        addMessage("model", "❌ Failed to load chat history.");
    }
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

    // Loading
    const loadingId = "loading-" + Date.now();
    const container = document.getElementById("messages-container");
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "message bot-message loading-msg";
    loadingDiv.innerHTML = `<div class="avatar"><i class="fas fa-robot"></i></div><div class="content"><i class="fas fa-ellipsis-h fa-spin"></i></div>`;
    container.appendChild(loadingDiv);
    scrollToBottom();

    try {
        const payload = {
            message: text,
            session_id: currentSessionId // Send null if new, backend will create and return ID
        };

        const res = await authFetch(`${API_BASE}/chat/message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("API Error");

        const data = await res.json();

        // Update Session ID if new
        if (!currentSessionId && data.session_id) {
            currentSessionId = data.session_id;
            localStorage.setItem('currentChatSessionId', data.session_id);
            loadSessions(); // Refresh list to show new chat
        }

        loadingDiv.remove();
        addMessage("model", data.content, false, data.buttons);

    } catch (e) {
        const el = document.getElementById(loadingId);
        if (el) el.remove();
        addMessage("model", "Sorry, something went wrong.");
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

async function checkResearcherVisibility() {
    const btns = document.querySelectorAll(".research-btn");
    if (!btns || btns.length === 0) return;

    // Default hidden handled by logic below

    try {
        // Fetch profile to check resume
        const res = await authFetch(`${API_BASE}/profile`);
        const data = await res.json();
        const hasResume = !!data.primary_resume_name;

        // Just hide/show
        btns.forEach(btn => {
            if (hasResume) {
                btn.style.display = "inline-flex";
            } else {
                btn.style.display = "none";
            }
        });
    } catch (e) {
        btns.forEach(btn => btn.style.display = "none");
    }
}

async function triggerResearch() {
    addMessage("user", `Start Researcher`);
    try {
        const profileRes = await authFetch(`${API_BASE}/profile`);
        const profileData = await profileRes.json();
        const resumeName = profileData.primary_resume_name;

        if (!resumeName) {
            addMessage("model", "Please upload a resume first.");
            return;
        }

        addMessage("model", `Starting research with **${resumeName}**...`);

        const res = await authFetch(`${API_BASE}/agents/research`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                resume_filename: resumeName,
                limit: 10
            })
        });

        if (res.ok) {
            // Start Polling
            pollResearchStatus(resumeName);
        }
    } catch (e) {
        addMessage("model", "❌ Error starting research.");
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
                "skills": p.skills ? p.skills.join(", ") : ""
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
    // If no mode specified, prompt user for choice
    if (!mode) {
        const choice = await showApplyModeModal(url, title);
        if (!choice) return; // User cancelled
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
        } else {
            addMessage("model", "❌ Failed to start application.");
        }
    } catch (e) {
        console.error(e);
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
                    <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
                        <button id="mode-local-btn" class="chip" style="padding: 15px 25px; font-size: 1rem;">
                            💻 Run Locally
                        </button>
                        <button id="mode-cloud-btn" class="chip" style="padding: 15px 25px; font-size: 1rem; background: linear-gradient(135deg, #667eea, #764ba2);">
                            ☁️ Run in Cloud
                        </button>
                    </div>
                    <p style="margin-top: 15px; font-size: 0.85rem; color: var(--text-secondary);">
                        Cloud mode bypasses CAPTCHAs and provides enhanced stealth.
                    </p>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const close = () => { modal.remove(); resolve(null); };
        modal.querySelector('.close-modal').onclick = close;
        modal.onclick = (e) => { if (e.target === modal) close(); };

        modal.querySelector('#mode-local-btn').onclick = () => { modal.remove(); resolve('local'); };
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

async function pollResearchStatus(resumeName) {
    let attempts = 0;
    const maxAttempts = 30;

    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await authFetch(`${API_BASE}/agents/matches?resume_filename=${resumeName}`);
            if (!res.ok) return;

            const data = await res.json();
            const status = data.status.status;

            if (status === "COMPLETED" || (data.matches && data.matches.length > 0 && attempts % 5 === 0)) {
                if (status === "COMPLETED" || attempts > 5) {
                    clearInterval(interval);
                    addMessage("model", `Research Complete! Found ${data.matches.length} jobs.`);
                    addJobCards(data.matches);
                    return;
                }
            }

            if (attempts >= maxAttempts) {
                clearInterval(interval);
                addMessage("model", "Research is taking longer than expected. Check back later.");
            }

        } catch (e) {
            console.error("Polling error", e);
        }
    }, 3000);
}

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
            listContainer.innerHTML = "<p>No resu found. Upload one first!</p>";
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
    const resumeSelect = document.getElementById("resume-filter");
    const refreshBtn = document.getElementById("refresh-jobs-btn");

    // Inject Email into Sidebar
    await loadUserInfo();

    // Load Resumes into Filter
    try {
        const res = await authFetch(`${API_BASE}/resumes`);
        const resumes = await res.json();

        resumeSelect.innerHTML = "";

        // Option: All Resumes? Or select primary
        // Let's check profile for primary
        const profRes = await authFetch(`${API_BASE}/profile`);
        const profile = await profRes.json();
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

        data.leads.forEach(lead => {
            const div = document.createElement("div");
            div.className = "job-item";

            // Determine Status Color
            let statusClass = "status-new";
            if (lead.status === "APPLIED") statusClass = "status-applied";

            div.innerHTML = `
                <div class="job-main-info">
                    <h3>${lead.title}</h3>
                    <p>${lead.company}</p>
                </div>
                <div class="job-meta">
                    <span class="match-score">${lead.match_score}% Match</span>
                    <span class="status-pill ${statusClass}">${lead.status}</span>
                    <div class="actions">
                        <button class="apply-chat-btn" data-lead-id="${lead.id}" style="padding: 6px 12px; font-size: 0.8rem; background: var(--accent-color); color: #000; border: none; border-radius: 4px; cursor: pointer; font-weight: 500;">
                            Apply <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>
            `;

            // Add click handler for Apply button
            const applyBtn = div.querySelector('.apply-chat-btn');
            if (applyBtn) {
                applyBtn.addEventListener('click', () => openApplyModal(lead, resumeName));
            }
            container.appendChild(div);
        });

    } catch (e) {
        console.error("Error loading jobs", e);
        container.innerHTML = "<p style='text-align:center;'>Error loading leads.</p>";
    }
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
    // Accepts: Apply to @JobTitle ...
    if (text.toLowerCase().startsWith("apply to @")) {
        // Try to identify the job
        // 1. Check window.lastMentionedJob (most reliable if user clicked dropdown)
        let job = window.lastMentionedJob;

        // 2. If not set, try to fuzzy match from text
        if (!job) {
            // Extract title: "Apply to @Software Engineer at Google"
            // Remove "Apply to @"
            let raw = text.substring(9);
            // This is loose, but let's try to match against availableLeads
            job = availableLeads.find(l => raw.toLowerCase().includes(l.title.toLowerCase()));
        }

        if (job) {
            // Open Modal instead of sending
            // Clear input? Maybe keep it until confirmed?
            // Let's clear it to show we "consumed" the command
            chatInput.value = "";
            chatInput.style.height = "auto";

            // Open Unified Modal
            // We need to pass the resume context too.
            const profileRes = await authFetch(`${API_BASE}/profile`);
            const profile = await profileRes.json();

            openApplyModal(job, profile.primary_resume_name);
            return;
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
                    <div style="display: flex; gap: 20px;">
                        <label style="display: flex; align-items: center; cursor: pointer;">
                            <input type="radio" name="execution-mode" value="cloud" checked style="margin-right: 8px;">
                            <span style="color: var(--text-primary);">Cloud (Recommended)</span>
                        </label>
                        <label style="display: flex; align-items: center; cursor: pointer;">
                            <input type="radio" name="execution-mode" value="local" style="margin-right: 8px;">
                            <span style="color: var(--text-primary);">Local</span>
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

// Open Apply Modal with job data
async function openApplyModal(lead, contextResumeName) {
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

    let selectedMode = 'cloud';
    document.getElementsByName('execution-mode').forEach(rad => {
        if (rad.checked) selectedMode = rad.value;
    });

    if (!selectedResume) {
        alert("Please select a resume");
        return;
    }

    // Close Modal
    document.getElementById('apply-modal').style.display = 'none';

    // TRIGGER THE AGENT directly via API
    addMessage("user", `Apply to ${job.title} (${selectedMode === 'cloud' ? '☁️ Cloud' : '💻 Local'})`);
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
            addMessage("model", msg);
        } else {
            addMessage("model", "❌ Failed to start application.");
        }
    } catch (e) {
        console.error(e);
        addMessage("model", "❌ Error starting application.");
    }
}

