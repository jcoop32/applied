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

    // Sidebar Chat History List
    const sessionListContainer = document.createElement("div");
    sessionListContainer.id = "session-list";
    sessionListContainer.className = "session-list";
    // Insert after "New Chat" button in sidebar
    const sidebarGroup = document.querySelector(".sidebar .menu-group");
    if (sidebarGroup) sidebarGroup.appendChild(sessionListContainer);

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

        const container = document.getElementById("session-list");
        if (!container) return;
        container.innerHTML = ""; // clear

        if (sessions.length > 0) {
            const header = document.createElement("div");
            header.textContent = "Chat History";
            header.style.padding = "10px 15px";
            header.style.fontSize = "0.75rem";
            header.style.fontWeight = "600";
            header.style.color = "var(--text-secondary)";
            header.style.textTransform = "uppercase";
            header.style.letterSpacing = "0.05em";
            container.appendChild(header);
        }

        sessions.forEach(session => {
            const item = document.createElement("div");
            item.className = "menu-item session-item";

            // Flex container for title and edit btn
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.style.alignItems = "center";

            const titleSpan = document.createElement("span");
            titleSpan.textContent = session.title;
            titleSpan.style.whiteSpace = "nowrap";
            titleSpan.style.overflow = "hidden";
            titleSpan.style.textOverflow = "ellipsis";
            titleSpan.style.marginRight = "10px";

            item.appendChild(titleSpan);

            // Edit Btn
            const editBtn = document.createElement("i");
            editBtn.className = "fas fa-pencil-alt";
            editBtn.style.fontSize = "0.8rem";
            editBtn.style.opacity = "0.5";
            editBtn.style.cursor = "pointer";
            editBtn.title = "Rename Chat";

            editBtn.onmouseover = () => editBtn.style.opacity = "1";
            editBtn.onmouseout = () => editBtn.style.opacity = "0.5";

            editBtn.onclick = (e) => {
                e.stopPropagation(); // Don't load session
                renameSession(session.id, session.title);
            };

            item.appendChild(editBtn);

            // Highlight current
            if (session.id === currentSessionId) {
                item.style.background = "rgba(255,255,255,0.1)";
                item.style.color = "white";
            }
            item.onclick = (e) => {
                // Only trigger if not clicking edit (already handled by stopPropagation but safest)
                if (e.target !== editBtn) loadSession(session.id);
            };
            container.appendChild(item);
        });

    } catch (e) {
        console.error("Failed to load sessions", e);
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

        messages.forEach(msg => {
            addMessage(msg.role === 'model' ? 'model' : 'user', msg.content, true);
        });

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

function addMessage(role, content, isHistoryLoad = false) {
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
        addMessage("model", data.content);

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
    const btn = document.querySelector(".chip[onclick*='triggerResearch']");
    if (!btn) return;

    // Default hidden
    // btn.style.display = "none";

    try {
        // Fetch profile to check resume
        const res = await authFetch(`${API_BASE}/profile`);
        const data = await res.json();
        const hasResume = !!data.primary_resume_name;

        // Just hide/show
        if (hasResume) {
            btn.style.display = "inline-flex";
        } else {
            btn.style.display = "none";
        }
    } catch (e) {
        btn.style.display = "none";
    }
}

async function triggerResearch() {
    addMessage("user", "Start Research Agent");
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
            body: JSON.stringify({ resume_filename: resumeName, limit: 10 })
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

    // Load current profile
    try {
        const res = await authFetch(`${API_BASE}/profile`);
        const user = await res.json();

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
                    <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid var(--border-color);">
                        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                            <strong style="color: var(--text-primary); font-size: 1rem;">${e.title || 'Role'}</strong>
                            <span style="color: var(--accent-color); font-size: 0.9rem;">${e.duration || ''}</span>
                        </div>
                        <div style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 5px;">${e.company || 'Company'}</div>
                        <p style="color: var(--text-secondary); font-size: 0.85rem; line-height: 1.4; margin: 0;">${e.responsibilities || ''}</p>
                    </div>
                `).join("");
            }

            // Render Education
            const eduContainer = document.getElementById("education-list");
            if (eduContainer && p.education && p.education.length > 0) {
                eduContainer.innerHTML = p.education.map(e => `
                    <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid var(--border-color);">
                        <div style="display:flex; justify-content:space-between;">
                            <strong style="color: var(--text-primary);">${e.school || 'School'}</strong>
                            <span style="color: var(--text-secondary);">${e.date || ''}</span>
                        </div>
                        <div style="color: var(--text-secondary); font-size: 0.9rem;">${e.degree || 'Degree'}</div>
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

            // Collect form data
            const formData = {
                full_name: document.getElementById("full_name")?.value || "",
                profile_data: {
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

async function triggerApply(url, title) {
    if (!confirm(`Apply to ${title}?`)) return;
    addMessage("user", `Apply to ${title}`);
    addMessage("model", "Starting Application...");

    const res = await authFetch(`${API_BASE}/agents/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_url: url, mode: "cloud" })
    });
    if (res.ok) addMessage("model", "✅ Started.");
    else addMessage("model", "❌ Failed.");
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
// APPLY MODAL LOGIC (Jobs Page)
// ==========================================

// Initialize Apply Modal (called from initJobsPage)
function initApplyModal() {
    const modal = document.getElementById('apply-modal');
    const closeBtn = document.querySelector('.close-apply-modal');
    const confirmBtn = document.getElementById('apply-confirm-btn');
    const uploadBtn = document.getElementById('apply-upload-btn');
    const uploadInput = document.getElementById('apply-resume-upload');

    if (closeBtn && modal) {
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    // Close on outside click
    if (modal) {
        window.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    }

    if (confirmBtn) {
        confirmBtn.addEventListener('click', confirmApplyToChat);
    }

    if (uploadBtn && uploadInput) {
        uploadBtn.addEventListener('click', () => uploadInput.click());
        uploadInput.addEventListener('change', handleApplyResumeUpload);
    }
}

// Open Apply Modal with job data
async function openApplyModal(lead, contextResumeName) {
    const modal = document.getElementById('apply-modal');
    const titleEl = document.getElementById('apply-job-title');
    const companyEl = document.getElementById('apply-job-company');
    const resumeSelect = document.getElementById('apply-resume-select');
    const instructionsEl = document.getElementById('apply-instructions');
    const uploadStatus = document.getElementById('apply-upload-status');

    if (!modal) return;

    // Store lead data for later use
    window.pendingApplyJob = {
        title: lead.title,
        company: lead.company,
        url: lead.url,
        contextResume: contextResumeName
    };

    // Populate job info
    if (titleEl) titleEl.textContent = lead.title;
    if (companyEl) companyEl.textContent = lead.company;
    if (instructionsEl) instructionsEl.value = '';
    if (uploadStatus) uploadStatus.textContent = '';

    // Populate resume dropdown
    if (resumeSelect) {
        resumeSelect.innerHTML = '<option value="">Loading...</option>';

        try {
            const res = await authFetch(`${API_BASE}/resumes`);
            const resumes = await res.json();

            resumeSelect.innerHTML = '';

            if (!Array.isArray(resumes) || resumes.length === 0) {
                resumeSelect.innerHTML = '<option value="">No resumes found</option>';
            } else {
                resumes.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.name;
                    opt.textContent = r.name;
                    // Pre-select the resume that was used when finding this lead
                    if (r.name === contextResumeName) {
                        opt.selected = true;
                    }
                    resumeSelect.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('Error loading resumes for apply modal', e);
            resumeSelect.innerHTML = '<option value="">Error loading resumes</option>';
        }
    }

    // Show modal
    modal.style.display = 'block';

    // Initialize modal event listeners if not already done
    if (!modal.dataset.initialized) {
        initApplyModal();
        modal.dataset.initialized = 'true';
    }
}

// Build prompt and navigate to chat
function confirmApplyToChat() {
    const job = window.pendingApplyJob;
    if (!job) {
        alert('No job selected');
        return;
    }

    const resumeSelect = document.getElementById('apply-resume-select');
    const instructionsEl = document.getElementById('apply-instructions');

    const selectedResume = resumeSelect?.value || '';
    const instructions = instructionsEl?.value?.trim() || '';

    if (!selectedResume) {
        alert('Please select a resume');
        return;
    }

    // Build the structured prompt
    let prompt = `Apply to @${job.title} at ${job.company} using resume [${selectedResume}].

Job URL: ${job.url}`;

    if (instructions) {
        prompt += `

Additional instructions:
${instructions}`;
    }

    // Save to localStorage for chat page pickup
    localStorage.setItem('pendingApplyPrompt', prompt);

    // Close modal and navigate to chat
    const modal = document.getElementById('apply-modal');
    if (modal) modal.style.display = 'none';

    window.location.href = '/';
}

// Handle resume upload within the apply modal
async function handleApplyResumeUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const uploadStatus = document.getElementById('apply-upload-status');
    const resumeSelect = document.getElementById('apply-resume-select');

    if (uploadStatus) uploadStatus.textContent = 'Uploading...';

    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem('token');

    try {
        const res = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        if (res.ok) {
            if (uploadStatus) uploadStatus.textContent = `✅ Uploaded: ${file.name}`;

            // Refresh the resume dropdown and select the new file
            const resumesRes = await authFetch(`${API_BASE}/resumes`);
            const resumes = await resumesRes.json();

            if (resumeSelect && Array.isArray(resumes)) {
                resumeSelect.innerHTML = '';
                resumes.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.name;
                    opt.textContent = r.name;
                    // Select the newly uploaded file
                    if (r.name === file.name) {
                        opt.selected = true;
                    }
                    resumeSelect.appendChild(opt);
                });
            }
        } else {
            if (uploadStatus) uploadStatus.textContent = '❌ Upload failed';
        }
    } catch (err) {
        console.error('Upload error', err);
        if (uploadStatus) uploadStatus.textContent = '❌ Upload error';
    }

    // Clear the input
    e.target.value = '';
}
