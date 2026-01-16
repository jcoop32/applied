const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusText = document.getElementById('upload-status');
const resumeList = document.getElementById('resume-list');

// --- Global Auth Helper ---
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '/login';
        return null;
    }
    return {
        'Authorization': `Bearer ${token}`
    };
}

// Check where we are executing
if (document.getElementById('drop-zone')) {
    // We are on index page
    fetchResumes();

    // Drag & Drop Events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
}

// --- Upload Logic ---
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFiles(files);
}

function handleFiles(files) {
    if (files.length > 0) {
        uploadFile(files[0]);
    }
}

async function uploadFile(file) {
    if (!statusText) return;
    statusText.textContent = `Uploading ${file.name}...`;
    statusText.className = 'status-text status-uploading';

    const formData = new FormData();
    formData.append('file', file);

    const headers = getAuthHeaders();
    if (!headers) return; // Redirected

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            headers: headers,
            body: formData
        });

        if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
            return;
        }

        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        statusText.textContent = `✅ Upload Complete!`;
        statusText.className = 'status-text status-success';

        // Refresh list
        fetchResumes();

        // Clear status after 3s
        setTimeout(() => {
            statusText.textContent = '';
        }, 3000);

    } catch (error) {
        console.error('Error:', error);
        statusText.textContent = `❌ Error: ${error.message}`;
        statusText.className = 'status-text status-error';
    }
}

let globalFiles = [];

async function fetchResumes() {
    if (!resumeList) return;

    const headers = getAuthHeaders();
    if (!headers) return;

    try {
        // Parallel Fetch: Resumes AND Profile (to know which is Primary)
        const [resumeRes, profileRes] = await Promise.all([
            fetch('/api/resumes', { headers }),
            fetch('/api/profile', { headers })
        ]);

        if (resumeRes.status === 401 || profileRes.status === 401) {
            window.location.href = '/login';
            return;
        }

        if (!resumeRes.ok) throw new Error("Failed to fetch resumes");

        const files = await resumeRes.json();
        let primaryName = null;

        if (profileRes.ok) {
            const user = await profileRes.json();
            primaryName = user.primary_resume_name;
        }

        globalFiles = files; // Store for other uses if needed
        renderList(files, primaryName);
        checkDashboardStatuses(); // Update UI with agent status

    } catch (error) {
        console.error("Fetch error:", error);
        resumeList.innerHTML = `<div style="text-align:center; color: var(--text-secondary)">Failed to load resumes</div>`;
    }
}

function renderList(files, primaryName) {
    if (files.length === 0) {
        resumeList.innerHTML = `<div style="text-align:center; color: var(--text-secondary)">No resumes found</div>`;
        return;
    }

    resumeList.innerHTML = files.map(file => {
        // Check if this file is the primary resume
        const isPrimary = file.name === primaryName;

        return `
        <div class="resume-item" id="resume-item-${file.name}">
            <div class="resume-info" onclick="openResumeDetails('${file.name}', '${file.url}', ${file.job_count || 0})" style="cursor: pointer;">
                <span class="resume-name" style="text-decoration: underline; text-decoration-color: rgba(255,255,255,0.3);">
                    ${isPrimary ? '<span class="primary-badge" title="Primary Resume">⭐</span>' : ''}
                    ${file.name}
                    ${file.job_count ? `<span style="font-size:0.8rem; color:var(--text-secondary); margin-left:5px;">(${file.job_count} Jobs)</span>` : ''}
                </span>
                <span class="resume-date">${new Date(file.created_at).toLocaleDateString()}</span>
            </div>
            <div style="display:flex; align-items:center; gap: 8px;">
                <button onclick="openResumeDetails('${file.name}', '${file.url}', ${file.job_count || 0})" class="btn-secondary" style="font-size:0.8rem; padding: 4px 8px;">📂 Open</button>
                <button onclick="deleteResume('${file.name}')" class="btn-delete" title="Delete">🗑️</button>
            </div>
        </div>
    `}).join('');
}

// Global scope for onclick
window.deleteResume = async function (filename) {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) return;

    const headers = getAuthHeaders();
    if (!headers) return;

    try {
        const res = await fetch(`/api/upload/${filename}`, {
            method: 'DELETE',
            headers: headers
        });

        if (!res.ok) throw new Error(await res.text());

        // Refresh
        fetchResumes();
    } catch (e) {
        alert(`Failed to delete: ${e.message}`);
    }
};

// --- Dashboard Agent Logic (Resume Details Modal) ---

// Make applyToJob global (Moved from Profile Page)
window.applyToJob = async (btn, url, resume, mode = 'cloud') => {
    console.log("👉 ApplyToJob Clicked", url, resume, mode);
    const headers = getAuthHeaders();
    if (!headers) return;

    // Optimistic UI Update
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ Application in Progress...";
    btn.style.opacity = "0.8";

    try {
        const res = await fetch('/api/agents/apply', {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_url: url, resume_filename: resume, mode: mode })
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Request failed");
        }

        // Success State
        btn.textContent = "✅ Application Started";
        btn.style.background = "var(--success, #4ade80)";
        btn.style.color = "black";
        // Optional: Reload status after a delay?
        setTimeout(() => {
            if (currentModalResume) refreshModalStatus(currentModalResume);
        }, 2000);

    } catch (e) {
        alert("Apply Failed: " + e.message);
        console.error(e);

        // Revert state on failure
        btn.textContent = "❌ Failed (Retry)";
        btn.style.background = "#f87171";
        btn.disabled = false;

        setTimeout(() => {
            btn.textContent = originalText; // Restore original text
            btn.style.background = "";
        }, 3000);
    }
};


let currentModalResume = null;
let dashboardPollInterval = null;

// Poll Statuses (Simplified: Just update the modal if open)
async function checkDashboardStatuses() {
    if (currentModalResume) {
        await refreshModalStatus(currentModalResume);
    }
}

// Open Modal
window.openResumeDetails = async (filename, fileUrl, jobCount = 0) => {
    currentModalResume = filename;

    const modal = document.getElementById('resume-details-modal');

    // Title with Count
    const countText = jobCount > 0 ? ` (${jobCount} Jobs Found)` : '';
    document.getElementById('modal-resume-title').textContent = filename + countText;

    document.getElementById('modal-btn-view-file').href = fileUrl;

    const findBtn = document.getElementById('modal-btn-find-jobs');
    const statusDiv = document.getElementById('modal-status-bar');
    const listDiv = document.getElementById('modal-matches-list');

    modal.style.display = 'flex';

    // Reset state
    statusDiv.textContent = "Checking status...";
    // listDiv.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">Loading...</p>';

    // Bind both buttons
    const btnGetWork = document.getElementById('modal-btn-find-getwork');
    const btnGoogle = document.getElementById('modal-btn-find-google');

    btnGetWork.onclick = () => triggerResumeSearch(filename, 'getwork');
    btnGoogle.onclick = () => triggerResumeSearch(filename, 'google');

    // Fetch initial status & matches
    await refreshModalStatus(filename);

    // Start Polling while modal is open
    if (dashboardPollInterval) clearInterval(dashboardPollInterval);
    dashboardPollInterval = setInterval(() => checkDashboardStatuses(), 6000);

    // Bind Filter Toggle (re-bind safely)
    const filterBtn = document.getElementById('modal-btn-filter');
    const inputContainer = document.getElementById('manual-search-inputs');
    if (filterBtn && inputContainer) {
        // Remove old listeners to avoid dupes if re-opened?
        // Actually, replacing onclick is safer.
        filterBtn.onclick = () => {
            const isHidden = inputContainer.style.display === 'none';
            inputContainer.style.display = isHidden ? 'block' : 'none';
            // Optional: visual toggle state on button?
            filterBtn.style.background = isHidden ? 'rgba(255,255,255,0.2)' : '';
        };
    }
};

window.closeResumeModal = () => {
    document.getElementById('resume-details-modal').style.display = 'none';
    const inputContainer = document.getElementById('manual-search-inputs');
    if (inputContainer) inputContainer.style.display = 'none'; // Reset to hidden

    currentModalResume = null;
    if (dashboardPollInterval) clearInterval(dashboardPollInterval);
};

// Refresh Status Logic
async function refreshModalStatus(filename) {
    if (!filename) return;
    const headers = getAuthHeaders();
    if (!headers) return;

    const findBtn = document.getElementById('modal-btn-find-jobs');
    const statusDiv = document.getElementById('modal-status-bar');
    const listDiv = document.getElementById('modal-matches-list');

    try {
        const res = await fetch(`/api/agents/matches?resume_filename=${encodeURIComponent(filename)}`, { headers });
        const data = await res.json();

        const statusObj = data.status || {};
        const state = statusObj.status || "IDLE";
        const matches = data.matches || [];

        // Stop polling if terminal state
        if ((state === 'COMPLETED' || state === 'FAILED') && dashboardPollInterval) {
            clearInterval(dashboardPollInterval);
            dashboardPollInterval = null;
        }

        // Update Status Bar
        let statusText = `Status: ${state}`;
        statusDiv.style.color = "var(--text-primary)"; // Reset color

        if (state === 'SEARCHING') {
            statusText = "Status: 🕵️ Researching Job Sites... (Background)";
            statusDiv.style.color = "#fbbf24"; // Amber
        }
        if (state === 'COMPLETED') {
            statusText = `Status: ✅ Completed (${matches.length} matches)`;
            statusDiv.style.color = "#4ade80"; // Green
        }
        if (state === 'FAILED') {
            statusText = "Status: ❌ Failed (Check Logs)";
            statusDiv.style.color = "#f87171"; // Red
        }
        statusDiv.textContent = statusText;

        // Update Button State
        const btnGetWork = document.getElementById('modal-btn-find-getwork');
        const btnGoogle = document.getElementById('modal-btn-find-google');

        if (state === 'SEARCHING') {
            btnGetWork.disabled = true;
            btnGoogle.disabled = true;
            btnGoogle.textContent = "⏳ Working...";
            // Maybe just dim them?
        } else {
            btnGetWork.disabled = false;
            btnGoogle.disabled = false;
            btnGetWork.textContent = "🔍 GetWork";
            btnGoogle.textContent = "✅ Google Search";
        }

        // Render Matches
        if (matches.length > 0) {
            listDiv.innerHTML = matches.map(m => `
                <div class="job-card" style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border-left: 4px solid var(--accent); color: white;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                        <h4 style="margin:0;">${m.title}</h4>
                        <span style="font-size:0.8rem; background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px;">${m.match_score}% Match</span>
                    </div>
                    <div style="font-size:0.9rem; color:var(--text-secondary); margin-bottom:10px;">
                        ${(() => {
                    const rawSource = m.query_source || '';
                    let badge = '<span style="background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-size:0.7rem;">🔍 Standard</span>';
                    let query = rawSource;

                    if (rawSource.startsWith('GOOGLE|')) {
                        badge = '<span style="background:#4ade80; color:black; padding:2px 6px; border-radius:4px; font-size:0.7rem; font-weight:bold;">✅ Google Verified</span>';
                        query = rawSource.replace('GOOGLE|', '');
                    } else if (rawSource.startsWith('GETWORK|')) {
                        badge = '<span style="background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-size:0.7rem;">🔍 GetWork</span>';
                        query = rawSource.replace('GETWORK|', '');
                    }
                    return `${badge} <span style="font-size:0.8rem; opacity:0.8; margin-left:5px;">Source: ${query}</span>`;
                })()}
                         • <span style="font-size:0.8rem; opacity:0.8;">Added: ${m.created_at ? new Date(m.created_at).toLocaleDateString() : 'Recently'}</span>
                    </div>
                    <p style="font-size:0.85rem; margin-bottom:10px; color: #ddd;">
                        ${m.match_reason || ''}
                    </p>
                    <div style="display:flex; gap:10px;">
                        <a href="${m.url}" target="_blank" class="btn-secondary" style="font-size:0.8rem; padding: 5px 10px;">View Link</a>
                        ${(() => {
                    if (m.status === 'APPLIED') {
                        return `<button disabled class="btn-secondary" style="font-size:0.8rem; padding: 5px 10px; opacity: 0.7; cursor: not-allowed; background: var(--success, #4ade80); color: black;">✅ Applied</button>`;
                    } else if (m.status === 'FAILED') {
                        return `<button onclick="applyToJob(this, '${m.url}', '${filename}')" class="btn-primary" style="font-size:0.8rem; padding: 5px 10px; background: #f87171;">❌ Retry</button>`;
                    } else if (m.status === 'NEW' || !m.status) {
                        return `
                            <button onclick="applyToJob(this, '${m.url}', '${filename}', 'cloud')" class="btn-primary" style="font-size:0.75rem; padding: 4px 8px; background: #60a5fa; margin-right: 5px;" title="Use Browser Use Cloud (Best)">☁️ Cloud Apply</button>
                            <button onclick="applyToJob(this, '${m.url}', '${filename}', 'github')" class="btn-secondary" style="font-size:0.75rem; padding: 4px 8px;" title="Use GitHub Actions">🤖 GitHub Action</button>
                        `;
                    } else {
                        // Catch-all for granular active statuses (Navigating, Filling Form, etc.)
                        // Use a cleaned up display string
                        let displayStatus = m.status;
                        if (displayStatus === 'IN_PROGRESS') displayStatus = "In Progress...";
                        return `<button disabled class="btn-secondary" style="font-size:0.8rem; padding: 5px 10px; opacity: 0.7; cursor: not-allowed; background: #fbbf24; color: black;">⏳ ${displayStatus}</button>`;
                    }
                })()}
                    </div>
                </div>
            `).join('');
        } else {
            if (state === 'COMPLETED') {
                listDiv.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">No matches found for this resume.</p>';
            } else if (state === 'IDLE') {
                listDiv.innerHTML = '<div style="text-align:center; margin-top:40px;"><h3>Ready to Search</h3><p style="color:var(--text-secondary);">Click "Find Jobs" to start looking for roles matching this resume.</p></div>';
            }
        }

    } catch (e) {
        console.error(e);
        statusDiv.textContent = "Status: Error updating";
    }
}


async function triggerResumeSearch(filename, type) {
    console.log("👉 TriggerResumeSearch Clicked", filename, type);

    const btnGetWork = document.getElementById('modal-btn-find-getwork');
    const btnGoogle = document.getElementById('modal-btn-find-google');

    const limitInput = document.getElementById('job-limit-input');
    const limit = limitInput ? parseInt(limitInput.value, 10) : 20;

    // Get Manual Inputs
    const jobTitleInput = document.getElementById('manual-job-title');
    const locationInput = document.getElementById('manual-location');

    // Only use them if visible? Or always?
    // Let's use them if they have values. The visibility is UI-only preference.
    const job_title = jobTitleInput ? jobTitleInput.value.trim() : "";
    const location = locationInput ? locationInput.value.trim() : "";

    // Disable both
    btnGetWork.disabled = true;
    btnGoogle.disabled = true;

    if (type === 'google') {
        btnGoogle.textContent = "🚀 Starting...";
    } else {
        btnGetWork.textContent = "🚀 Starting...";
    }

    // Hide inputs to provide "sent" feedback
    const inputContainer = document.getElementById('manual-search-inputs');
    if (inputContainer) {
        inputContainer.style.display = 'none';
        // Reset button background if we set it
        const filterBtn = document.getElementById('modal-btn-filter');
        if (filterBtn) filterBtn.style.background = '';
    }

    const headers = getAuthHeaders();
    try {
        const payload = {
            resume_filename: filename,
            limit: limit,
            researcher_type: type
        };
        // Add manual overrides if present
        if (job_title) payload.job_title = job_title;
        if (location) payload.location = location;

        const res = await fetch('/api/agents/research', {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error((await res.json()).detail);

        // Restart Polling implicitly?
        // Actually, if we stopped polling because of COMPLETED, we need to restart it here.
        if (dashboardPollInterval) clearInterval(dashboardPollInterval);
        dashboardPollInterval = setInterval(() => checkDashboardStatuses(), 6000);

        refreshModalStatus(filename);

    } catch (e) {
        alert("Error: " + e.message);
        btnGetWork.disabled = false;
        btnGoogle.disabled = false;
        btnGetWork.textContent = "🔍 GetWork";
        btnGoogle.textContent = "✅ Google Search";
    }
}

// Update fetchResumes to call checkDashboardStatuses
const originalRenderList = renderList; // already defined? No, RenderList calls are inside fetchResumes.
// We need to modify fetchResumes to call checkDashboardStatuses after render.
// But we cannot easily hook inside.
// Instead, we will override/append behavior.
// Actually, I can just call checkDashboardStatuses() at the end of fetchResumes inside the try block.
// But I can't modify fetchResumes without rewriting it.
// I will rewrite fetchResumes slightly or just call checkDashboardStatuses in a timeout from renderList?
// I updated renderList so I can add the call there? No, renderList is pure UI.
// I'll call it in window.onload or similar?
// Since I can't easily edit fetchResumes mid-function, I added logic to poll.

// --- Profile Page Logic ---

async function initProfilePage() {
    const headers = getAuthHeaders();
    if (!headers) return;

    const full_name = document.getElementById('full_name');
    const profile_data = document.getElementById('profile_data');
    const resume_select = document.getElementById('primary-resume-select');
    const save_btn = document.getElementById('save-btn');
    const parse_btn = document.getElementById('parse-btn');
    const status_msg = document.getElementById('status-msg');
    const logout_btn = document.getElementById('logout-btn');

    if (logout_btn) {
        logout_btn.addEventListener('click', () => {
            localStorage.removeItem('token');
            window.location.href = '/login';
        });
    }

    // --- Date Helpers ---
    const MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];

    const getYearOptions = () => {
        const currentYear = new Date().getFullYear();
        const startYear = 1970;
        const endYear = currentYear + 10;
        let options = '<option value="">Year</option>';
        for (let y = endYear; y >= startYear; y--) {
            options += `<option value="${y}">${y}</option>`;
        }
        return options;
    };

    const getMonthOptions = () => {
        return '<option value="">Month</option>' + MONTHS.map(m => `<option value="${m}">${m}</option>`).join('');
    };

    // Helper: Parse string date "Jan 2020" -> {month: "January", year: "2020"}
    const parseDateString = (str) => {
        if (!str) return { month: "", year: "" };
        if (str.toLowerCase() === 'present') return { month: "", year: "", current: true };

        const parts = str.trim().split(' ');
        if (parts.length === 2) {
            // Try to match month abbreviation
            const m = MONTHS.find(mon => mon.toLowerCase().startsWith(parts[0].toLowerCase()));
            return { month: m || "", year: parts[1] };
        } else if (parts.length === 1 && /^\d{4}$/.test(parts[0])) {
            return { month: "", year: parts[0] };
        }
        return { month: "", year: "" };
    };


    window.addExperienceItem = (data = {}) => {
        const container = document.getElementById('experience-container');
        const div = document.createElement('div');
        div.className = 'experience-item';
        div.style = "background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border: 1px solid var(--glass-border); position: relative;";

        // Parse existing duration string if needed
        let start = { month: "", year: "" };
        let end = { month: "", year: "" };
        let isCurrent = false;

        if (data.duration) {
            const parts = data.duration.split(' - ');
            if (parts.length >= 1) start = parseDateString(parts[0]);
            if (parts.length >= 2) {
                if (parts[1].toLowerCase() === 'present' || parts[1].toLowerCase() === 'current') {
                    isCurrent = true;
                } else {
                    end = parseDateString(parts[1]);
                }
            } else if (data.duration.toLowerCase().includes('present')) {
                // Fallback for messy strings
                isCurrent = true;
            }
        }

        // Use structure if available (overwrites string parsing)
        if (data.start_year) start = { month: data.start_month, year: data.start_year };
        if (data.end_year) end = { month: data.end_month, year: data.end_year };
        if (data.is_current) isCurrent = true;

        div.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" style="position:absolute; top:10px; right:12px; background:transparent; border:none; color:#f87171; cursor:pointer;">✖</button>
            <div class="form-grid" style="margin-bottom:0;">
                <div class="form-group">
                    <label>Company</label>
                    <input type="text" class="exp-company" value="${data.company || ''}" placeholder="Company Name">
                </div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" class="exp-title" value="${data.title || ''}" placeholder="Job Title">
                </div>
                
                <!-- Date Grid -->
                <div class="form-group full-width">
                     <label>Time Period</label>
                     <div style="display:grid; grid-template-columns: 1fr 1fr 20px 1fr 1fr; gap:10px; align-items:center;">
                        
                        <!-- Start -->
                        <select class="exp-start-month">${getMonthOptions()}</select>
                        <select class="exp-start-year">${getYearOptions()}</select>
                        
                        <span style="text-align:center; color:var(--text-secondary)">to</span>
                        
                        <!-- End -->
                        <select class="exp-end-month" ${isCurrent ? 'disabled' : ''}>${getMonthOptions()}</select>
                        <select class="exp-end-year" ${isCurrent ? 'disabled' : ''}>${getYearOptions()}</select>
                     </div>
                     <div style="margin-top:8px;">
                        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; font-weight:normal; font-size:0.9rem;">
                            <input type="checkbox" class="exp-current" ${isCurrent ? 'checked' : ''} onchange="toggleEndDate(this)">
                            I currently work here
                        </label>
                     </div>
                </div>

                 <div class="form-group full-width">
                    <label>Description</label>
                    <textarea class="exp-desc" style="min-height:60px; font-size:0.9rem;">${data.responsibilities || (Array.isArray(data.description) ? data.description.join('\\n') : (data.description || ''))}</textarea>
                </div>
            </div>
        `;

        // Set values
        div.querySelector('.exp-start-month').value = start.month || "";
        div.querySelector('.exp-start-year').value = start.year || "";
        if (!isCurrent) {
            div.querySelector('.exp-end-month').value = end.month || "";
            div.querySelector('.exp-end-year').value = end.year || "";
        }

        container.appendChild(div);
    };

    window.toggleEndDate = (checkbox) => {
        const parent = checkbox.closest('.form-group'); // The checkbox wrapper
        const dateRow = parent.previousElementSibling; // The grid row
        const endMonth = dateRow.querySelector('.exp-end-month');
        const endYear = dateRow.querySelector('.exp-end-year');

        if (checkbox.checked) {
            endMonth.disabled = true;
            endYear.disabled = true;
            endMonth.value = "";
            endYear.value = "";
        } else {
            endMonth.disabled = false;
            endYear.disabled = false;
        }
    };

    window.addEducationItem = (data = {}) => {
        const container = document.getElementById('education-container');
        const div = document.createElement('div');
        div.className = 'education-item';
        div.style = "background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border: 1px solid var(--glass-border); position: relative;";

        // Parse existing date
        let start = { month: "", year: "" };
        let end = { month: "", year: "" };

        // Logic for Edu: sometimes it's just "2022" (Graduation), sometimes "2018 - 2022"
        if (data.date || data.year) {
            const raw = data.date || data.year;
            // Check for range
            if (raw.includes('-')) {
                const parts = raw.split('-');
                if (parts.length >= 1) start = parseDateString(parts[0]);
                if (parts.length >= 2) end = parseDateString(parts[1]);
            } else {
                // Assume Single Date is End Date (Graduation)
                end = parseDateString(raw);
            }
        }

        if (data.start_year) start = { month: data.start_month, year: data.start_year };
        if (data.end_year) end = { month: data.end_month, year: data.end_year };

        div.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" style="position:absolute; top:10px; right:12px; background:transparent; border:none; color:#f87171; cursor:pointer;">✖</button>
            <div class="form-grid" style="margin-bottom:0;">
                <div class="form-group">
                    <label>School / Institution</label>
                    <input type="text" class="edu-school" value="${data.institution || data.school || ''}" placeholder="University Name">
                </div>
                <div class="form-group">
                    <label>Degree / Certificate</label>
                    <input type="text" class="edu-degree" value="${data.degree || ''}" placeholder="B.S. Computer Science">
                </div>
                
                 <!-- Date Grid -->
                <div class="form-group full-width">
                     <label>Dates Attended</label>
                     <div style="display:grid; grid-template-columns: 1fr 1fr 20px 1fr 1fr; gap:10px; align-items:center;">
                        <!-- Start -->
                        <select class="edu-start-month">${getMonthOptions()}</select>
                        <select class="edu-start-year">${getYearOptions()}</select>
                        
                        <span style="text-align:center; color:var(--text-secondary)">to</span>
                        
                        <!-- End -->
                        <select class="edu-end-month">${getMonthOptions()}</select>
                        <select class="edu-end-year">${getYearOptions()}</select>
                     </div>
                </div>
            </div>
        `;

        // Set Values
        div.querySelector('.edu-start-month').value = start.month || "";
        div.querySelector('.edu-start-year').value = start.year || "";
        div.querySelector('.edu-end-month').value = end.month || "";
        div.querySelector('.edu-end-year').value = end.year || "";

        container.appendChild(div);
    };

    // Helper: Populate Form
    const populateForm = (pd) => {
        if (!pd) return;

        if (pd.contact_info) {
            const c = pd.contact_info;
            document.getElementById('phone').value = c.phone || '';
            document.getElementById('linkedin').value = c.linkedin || '';
            document.getElementById('portfolio').value = c.portfolio || '';
            document.getElementById('address').value = c.address || '';
        }

        const salaryInput = document.getElementById('salary_expectations');
        if (salaryInput) {
            salaryInput.value = pd.salary_expectations || '';
            // Auto-format initial value
            if (salaryInput.value) {
                // Determine if we need to format it (might already be formatted)
                // Just let the user see what is saved, but we can try to format if it looks like a raw number
                if (/^\d+$/.test(salaryInput.value)) {
                    salaryInput.value = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(salaryInput.value);
                }
            }
        }
        document.getElementById('summary').value = pd.summary || '';
        document.getElementById('skills').value = Array.isArray(pd.skills) ? pd.skills.join(', ') : (pd.skills || '');

        // Demographics (if present and user manually saved them)
        if (pd.demographics) {
            const d = pd.demographics;
            if (d.race) document.getElementById('race').value = d.race;
            if (d.veteran) document.getElementById('veteran').value = d.veteran;
            if (d.disability) document.getElementById('disability').value = d.disability;
            if (d.authorization) document.getElementById('authorization').value = d.authorization;
        }

        // Details (Dynamic List Helpers must be defined before calling) (they are attached to window now)
        document.getElementById('experience-container').innerHTML = '';
        if (pd.experience && Array.isArray(pd.experience)) {
            pd.experience.forEach(addExperienceItem);
        }

        document.getElementById('education-container').innerHTML = '';
        if (pd.education && Array.isArray(pd.education)) {
            pd.education.forEach(addEducationItem);
        }
    };

    // --- Dynamic List Helpers (Moved to top) ---
    // (We replaced the old window.addExperienceItem / addEducationItem above with the new versions that have dropdowns)

    // Bind Add Buttons
    const addExpBtn = document.getElementById('add-experience-btn');
    if (addExpBtn) addExpBtn.onclick = () => addExperienceItem();

    const addEduBtn = document.getElementById('add-education-btn');
    if (addEduBtn) addEduBtn.onclick = () => addEducationItem();




    // 1. Fetch Profile Data
    try {
        const res = await fetch('/api/profile', { headers });
        if (!res.ok) throw new Error("Failed to load profile");
        const user = await res.json();

        full_name.value = user.full_name || '';
        profile_data.value = JSON.stringify(user.profile_data || {}, null, 2);

        if (user.profile_data) {
            populateForm(user.profile_data);
        }

        // 1.5 Bind Currency Formatter
        const salaryInfo = document.getElementById('salary_expectations');
        if (salaryInfo) {
            salaryInfo.addEventListener('blur', (e) => {
                const val = e.target.value;
                if (!val) return;
                // Strip chars to get number
                const clean = val.replace(/[^0-9.]/g, '');
                if (!clean) return;
                const num = parseFloat(clean);
                if (!isNaN(num)) {
                    e.target.value = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
                }
            });
        }

        // 2. Fetch Resumes for Dropdown
        const resumeRes = await fetch('/api/resumes', { headers });
        if (resumeRes.ok) {
            const files = await resumeRes.json();
            files.forEach(f => {
                const option = document.createElement('option');
                option.value = f.name; // Storing filename as identifier

                // Show count if available
                const countLabel = f.job_count ? ` (${f.job_count} Jobs Found)` : '';
                option.textContent = f.name + countLabel;

                // Pre-select if matches
                if (user.primary_resume_name === f.name) {
                    option.selected = true;
                }
                resume_select.appendChild(option);
            });
        }
    } catch (e) {
        console.error(e);
        status_msg.textContent = "Error loading profile.";
        status_msg.style.color = "red";
    }

    // 3. Save Handler
    document.getElementById('profile-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        status_msg.textContent = "Saving...";
        status_msg.style.color = "var(--text-secondary)";
        save_btn.disabled = true;

        try {
            // Reconstruct JSON from fields
            const newProfileData = {
                contact_info: {
                    phone: document.getElementById('phone').value,
                    linkedin: document.getElementById('linkedin').value,
                    portfolio: document.getElementById('portfolio').value,
                    address: document.getElementById('address').value
                },
                demographics: {
                    race: document.getElementById('race').value,
                    veteran: document.getElementById('veteran').value,
                    disability: document.getElementById('disability').value,
                    authorization: document.getElementById('authorization').value
                },
                salary_expectations: document.getElementById('salary_expectations').value,
                summary: document.getElementById('summary').value,
                skills: document.getElementById('skills').value.split(',').map(s => s.trim()).filter(Boolean),
                experience: [],
                education: []
            };

            // Scrape Dynamic Inputs
            document.querySelectorAll('.experience-item').forEach(el => {
                const startM = el.querySelector('.exp-start-month').value;
                const startY = el.querySelector('.exp-start-year').value;
                const isCurrent = el.querySelector('.exp-current').checked;

                let endM = "";
                let endY = "";
                let durationStr = "";

                if (startM || startY) {
                    durationStr = `${startM.substring(0, 3)} ${startY}`;
                }

                if (isCurrent) {
                    durationStr += " - Present";
                } else {
                    endM = el.querySelector('.exp-end-month').value;
                    endY = el.querySelector('.exp-end-year').value;
                    if (endM || endY) {
                        durationStr += ` - ${endM.substring(0, 3)} ${endY}`;
                    }
                }

                durationStr = durationStr.trim().replace(/^- /, '').replace(/ -$/, '');

                newProfileData.experience.push({
                    company: el.querySelector('.exp-company').value,
                    title: el.querySelector('.exp-title').value,
                    description: el.querySelector('.exp-desc').value,
                    // New Fields
                    start_month: startM,
                    start_year: startY,
                    end_month: endM,
                    end_year: endY,
                    is_current: isCurrent,
                    // Legacy Support
                    duration: durationStr
                });
            });

            document.querySelectorAll('.education-item').forEach(el => {
                const startM = el.querySelector('.edu-start-month').value;
                const startY = el.querySelector('.edu-start-year').value;
                const endM = el.querySelector('.edu-end-month').value;
                const endY = el.querySelector('.edu-end-year').value;

                let dateStr = "";
                if (startM || startY) {
                    dateStr = `${startM.substring(0, 3)} ${startY}`;
                }
                if (endM || endY) {
                    // If both exist, range. If only end exists (grad year), just end? 
                    // Usually education range is "2018 - 2022".
                    if (dateStr) dateStr += ` - `;
                    dateStr += `${endM.substring(0, 3)} ${endY}`;
                }
                dateStr = dateStr.trim();

                newProfileData.education.push({
                    school: el.querySelector('.edu-school').value,
                    degree: el.querySelector('.edu-degree').value,
                    // New Fields
                    start_month: startM,
                    start_year: startY,
                    end_month: endM,
                    end_year: endY,
                    // Legacy Support
                    date: dateStr
                });
            });

            // Raw JSON fallback if empty? No, rely on UI.

            // Merge with existing raw data to keep unmapped fields?
            // Actually, safest to overwrite with structured data, but if we have extra keys they might be lost?
            // Let's assume the UI covers everything we care about for the agent.

            const payload = {
                full_name: full_name.value,
                primary_resume_name: resume_select.value,
                profile_data: newProfileData
            };

            const res = await fetch('/api/profile', {
                method: 'PATCH',
                headers: {
                    ...headers,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error((await res.json()).detail || "Failed to update");

            const updated = await res.json();
            status_msg.textContent = "✅ Saved successfully!";
            status_msg.style.color = "#4ade80";

            // Update hidden raw view if needed
            // profile_data.value = JSON.stringify(updated.profile_data, null, 2);

        } catch (err) {
            status_msg.textContent = `❌ Error: ${err.message}`;
            status_msg.style.color = "#f87171";
        } finally {
            save_btn.disabled = false;
        }
    });

    // 4. Parse Handler
    parse_btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const selectedResume = resume_select.value;
        if (!selectedResume) {
            alert("Please select a Primary Resume first.");
            return;
        }

        if (!confirm("This will overwrite your current profile data with data parsed from " + selectedResume + ". Continue?")) {
            return;
        }

        parse_btn.disabled = true;
        parse_btn.textContent = "⏳ Parsing...";
        status_msg.textContent = "Parsing resume with AI... Please wait.";
        status_msg.style.color = "var(--text-secondary)";

        try {
            const res = await fetch('/api/profile/parse', {
                method: 'POST',
                headers: {
                    ...headers,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ resume_path: selectedResume })
            });

            if (!res.ok) {
                const errText = await res.text();
                try {
                    const jsonErr = JSON.parse(errText);
                    throw new Error(jsonErr.detail);
                } catch (e) {
                    throw new Error(errText);
                }
            }

            const parsedData = await res.json();
            // profile_data.value = JSON.stringify(parsedData, null, 2);

            if (parsedData.profile_data) {
                populateForm(parsedData.profile_data);



                // Raw Backup
                // if(pd.experience) document.getElementById('experience_json').value = JSON.stringify(pd.experience, null, 2);
                // if(pd.education) document.getElementById('education_json').value = JSON.stringify(pd.education, null, 2);

                status_msg.textContent = "✅ Auto-filled from resume! Format calibrated.";
                status_msg.style.color = "#4ade80";
            } else {
                status_msg.textContent = "✅ Parsing Complete!";
                status_msg.style.color = "#4ade80";
            }


        } catch (e) {
            console.error(e);
            status_msg.textContent = `❌ Parsing Failed: ${e.message}`;
            status_msg.style.color = "#f87171";
        } finally {
            parse_btn.disabled = false;
            parse_btn.textContent = "✨ Auto-Fill from Resume";
        }
    });

    // 4b. Generate Summary Handler
    const generateSummaryBtn = document.getElementById('generate-summary-btn');
    const revertSummaryBtn = document.getElementById('revert-summary-btn');
    let previousSummary = "";

    if (generateSummaryBtn) {
        generateSummaryBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            const selectedResume = resume_select.value;
            if (!selectedResume) {
                alert("Please select a Primary Resume first.");
                return;
            }

            // Capture
            previousSummary = document.getElementById('summary').value;

            generateSummaryBtn.disabled = true;
            generateSummaryBtn.textContent = "⏳ Generating...";

            try {
                const res = await fetch('/api/profile/summary', {
                    method: 'POST',
                    headers: {
                        ...headers,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ resume_path: selectedResume })
                });

                if (!res.ok) {
                    const errText = await res.text();
                    throw new Error(errText);
                }

                const data = await res.json();
                if (data.summary) {
                    document.getElementById('summary').value = data.summary;
                    status_msg.textContent = "✅ Summary Generated!";
                    status_msg.style.color = "#4ade80";

                    if (revertSummaryBtn) revertSummaryBtn.style.display = "inline-block";
                }
            } catch (e) {
                console.error(e);
                alert("Failed to generate summary: " + e.message);
            } finally {
                generateSummaryBtn.disabled = false;
                generateSummaryBtn.textContent = "✨ Generate with AI";
            }
        });
    }

    if (revertSummaryBtn) {
        revertSummaryBtn.addEventListener('click', () => {
            document.getElementById('summary').value = previousSummary;
            revertSummaryBtn.style.display = "none";
            status_msg.textContent = "↩️ Summary Reverted";
            status_msg.style.color = "var(--text-secondary)";
        });
    }
    // 5. Agent Controls logic - REMOVED per user request
    // const findJobsBtn = document.getElementById('find-jobs-btn');
    // const viewMatchesBtn = document.getElementById('view-matches-btn');
    const matchesSection = document.getElementById('matches-section');
    const matchesList = document.getElementById('matches-list');

    // Helper: Verify Resume Selection
    const getSelectedResume = () => {
        const val = resume_select.value;
        if (!val) alert("Please select a Primary Resume first.");
        return val;
    };

    // Helper: Poll Status
    let pollInterval = null;
    const checkResearchStatus = async (resumeName) => {
        try {
            const res = await fetch(`/api/agents/matches?resume_filename=${encodeURIComponent(resumeName)}`, { headers });
            if (!res.ok) return;
            const data = await res.json();
            const statusObj = data.status || {};
            const state = statusObj.status || "IDLE";

            updateAgentUI(state);

            if (state === "COMPLETED" || state === "FAILED") {
                clearInterval(pollInterval);
            }
        } catch (e) {
            console.error("Poll error", e);
        }
    };

    const updateAgentUI = (status) => {
        // Buttons removed
        /*
        if (status === "SEARCHING" || status === "QUEUED") {
            findJobsBtn.disabled = true;
            findJobsBtn.textContent = status === "QUEUED" ? "⏳ Queued..." : "⏳ Scanning...";
            viewMatchesBtn.style.display = "none";
        } else if (status === "COMPLETED") {
            findJobsBtn.disabled = false;
            findJobsBtn.textContent = "🔄 Re-Scan";
            viewMatchesBtn.style.display = "inline-block";
        } else {
            findJobsBtn.disabled = false;
            findJobsBtn.textContent = "🔍 Find Jobs";
            viewMatchesBtn.style.display = "none";
        }
        */
    };

    // Check on load if value exists
    /*
    resume_select.addEventListener('change', () => {
       const val = resume_select.value;
       if (val) {
           // Check status immediately
           // checkResearchStatus(val);
       } else {
           // viewMatchesBtn.style.display = "none";
       }
    });
    */
    // We'll add a slight delay or MutationObserver?
    // Simpler: Just poll once after a second.
    setTimeout(() => {
        if (resume_select.value) checkResearchStatus(resume_select.value);
    }, 1000);


    /*
    findJobsBtn.addEventListener('click', async () => {
        const resume = getSelectedResume();
        if (!resume) return;

        findJobsBtn.disabled = true;
        findJobsBtn.textContent = "🚀 Starting...";

        try {
            const res = await fetch('/api/agents/research', {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ resume_filename: resume })
            });
            if(!res.ok) throw new Error((await res.json()).detail);

            updateAgentUI("SEARCHING");

            // Start Polling
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(() => checkResearchStatus(resume), 4000);

        } catch (e) {
            alert("Error: " + e.message);
            updateAgentUI("IDLE");
        }
    });
    */

    /*
    viewMatchesBtn.addEventListener('click', async () => {
        const resume = getSelectedResume();
        if (!resume) return;

        if (matchesSection.style.display === "block") {
            matchesSection.style.display = "none";
            return;
        }

        matchesSection.style.display = "block";
        matchesList.innerHTML = '<p style="color:white;">Loading matches...</p>';

        try {
            const res = await fetch(`/api/agents/matches?resume_filename=${encodeURIComponent(resume)}`, { headers });
            const data = await res.json();

            if (!data.matches || data.matches.length === 0) {
                matchesList.innerHTML = '<p style="color:var(--text-secondary);">No matches found.</p>';
                return;
            }

            matchesList.innerHTML = data.matches.map(m => `
                <div class="job-card" style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border-left: 4px solid var(--accent);">
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                        <h4 style="margin:0;">${m.title}</h4>
                        <span style="font-size:0.8rem; background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px;">${m.match_score}% Match</span>
                    </div>
                    <div style="font-size:0.9rem; color:var(--text-secondary); margin-bottom:10px;">
                        ${m.company} • ${m.query_source || 'Search'} • Added: ${m.created_at ? new Date(m.created_at).toLocaleDateString() : 'Just now'}
                    </div>
                    <p style="font-size:0.85rem; margin-bottom:10px; color: #ddd;">
                        ${m.match_reason || ''}
                    </p>
                    <div style="display:flex; gap:10px;">
                        <a href="${m.url}" target="_blank" class="btn-secondary" style="font-size:0.8rem; padding: 5px 10px;">View Link</a>
                        <button onclick="applyToJob(this, '${m.url}', '${filename}')" class="btn-primary" style="font-size:0.8rem; padding: 5px 10px;">⚡ Quick Apply</button>
                    </div>
                </div>
            `).join('');

        } catch (e) {
            console.error(e);
            matchesList.innerHTML = '<p style="color:var(--text-secondary);">Error loading matches.</p>';
        }
    });
    */




}
