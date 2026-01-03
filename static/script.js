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
window.deleteResume = async function(filename) {
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
    findBtn.onclick = () => triggerResumeSearch(filename);

    // Fetch initial status & matches
    await refreshModalStatus(filename);

    // Start Polling while modal is open
    if (dashboardPollInterval) clearInterval(dashboardPollInterval);
    dashboardPollInterval = setInterval(() => checkDashboardStatuses(), 4000);
};

window.closeResumeModal = () => {
    document.getElementById('resume-details-modal').style.display = 'none';
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
        if (state === 'SEARCHING') {
            findBtn.disabled = true;
            findBtn.textContent = "⏳ Working...";
        } else {
            findBtn.disabled = false;
            findBtn.textContent = (state === 'COMPLETED') ? "🔄 Re-Scan" : "🔍 Find Jobs";
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
                        ${m.company} • ${m.query_source || 'Search'}
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


async function triggerResumeSearch(filename) {
    const findBtn = document.getElementById('modal-btn-find-jobs');
    const limitInput = document.getElementById('job-limit-input');
    const limit = limitInput ? parseInt(limitInput.value, 10) : 20;

    findBtn.disabled = true;
    findBtn.textContent = "🚀 Starting...";

    const headers = getAuthHeaders();
    try {
        const res = await fetch('/api/agents/research', {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume_filename: filename, limit: limit })
        });
        if(!res.ok) throw new Error((await res.json()).detail);

        refreshModalStatus(filename);

    } catch (e) {
        alert("Error: " + e.message);
        findBtn.disabled = false;
        findBtn.textContent = "🔍 Find Jobs";
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

    // Helper: Populate Form
    const populateForm = (pd) => {
        if (!pd) return;

        if(pd.contact_info) {
            const c = pd.contact_info;
            document.getElementById('phone').value = c.phone || '';
            document.getElementById('linkedin').value = c.linkedin || '';
            document.getElementById('portfolio').value = c.portfolio || '';
            document.getElementById('address').value = c.address || '';
        }

        document.getElementById('summary').value = pd.summary || '';
        document.getElementById('skills').value = Array.isArray(pd.skills) ? pd.skills.join(', ') : (pd.skills || '');

        // Demographics (if present and user manually saved them)
        if(pd.demographics) {
            const d = pd.demographics;
            if(d.race) document.getElementById('race').value = d.race;
            if(d.veteran) document.getElementById('veteran').value = d.veteran;
            if(d.disability) document.getElementById('disability').value = d.disability;
            if(d.authorization) document.getElementById('authorization').value = d.authorization;
        }

        // Details (Dynamic)
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
    window.addExperienceItem = (data = {}) => {
        const container = document.getElementById('experience-container');
        const id = Date.now() + Math.random();
        const div = document.createElement('div');
        div.className = 'experience-item';
        div.style = "background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border: 1px solid var(--glass-border); position: relative;";
        div.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" style="position:absolute; top:10px; right:10px; background:transparent; border:none; color:#f87171; cursor:pointer;">✖</button>
            <div class="form-grid" style="margin-bottom:0;">
                <div class="form-group">
                    <label>Company</label>
                    <input type="text" class="exp-company" value="${data.company || ''}" placeholder="Company Name">
                </div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" class="exp-title" value="${data.title || ''}" placeholder="Job Title">
                </div>
                <div class="form-group">
                    <label>Date Range</label>
                    <input type="text" class="exp-date" value="${data.duration || ''}" placeholder="e.g. 2020 - Present">
                </div>
                 <div class="form-group full-width">
                    <label>Description</label>
                    <textarea class="exp-desc" style="min-height:60px; font-size:0.9rem;">${data.responsibilities || (Array.isArray(data.description) ? data.description.join('\\n') : (data.description || ''))}</textarea>
                </div>
            </div>
        `;
        container.appendChild(div);
    };

    window.addEducationItem = (data = {}) => {
        const container = document.getElementById('education-container');
        const div = document.createElement('div');
        div.className = 'education-item';
        div.style = "background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border: 1px solid var(--glass-border); position: relative;";
        div.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" style="position:absolute; top:10px; right:10px; background:transparent; border:none; color:#f87171; cursor:pointer;">✖</button>
            <div class="form-grid" style="margin-bottom:0;">
                <div class="form-group">
                    <label>School / Institution</label>
                    <input type="text" class="edu-school" value="${data.institution || data.school || ''}" placeholder="University Name">
                </div>
                <div class="form-group">
                    <label>Degree / Certificate</label>
                    <input type="text" class="edu-degree" value="${data.degree || ''}" placeholder="B.S. Computer Science">
                </div>
                <div class="form-group">
                    <label>Date</label>
                    <input type="text" class="edu-date" value="${data.date || data.year || ''}" placeholder="e.g. 2018 - 2022">
                </div>
            </div>
        `;
        container.appendChild(div);
    };

    // Bind Add Buttons
    const addExpBtn = document.getElementById('add-experience-btn');
    if (addExpBtn) addExpBtn.onclick = () => addExperienceItem();

    const addEduBtn = document.getElementById('add-education-btn');
    if (addEduBtn) addEduBtn.onclick = () => addEducationItem();


    // Make applyToJob global
    window.applyToJob = async (btn, url, resume) => {
        if (!confirm("Start background application logic for this job? (Headless Mode)")) return;

        btn.disabled = true;
        btn.textContent = "🚀 Sending...";

        try {
            const res = await fetch('/api/agents/apply', {
                method: 'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_url: url, resume_filename: resume })
            });
            if(!res.ok) throw new Error((await res.json()).detail);

            btn.textContent = "✅ Started";
            // Check status logic could be complex (another poller?), for now just fire-and-forget UI
        } catch (e) {
            alert("Apply Failed: " + e.message);
            btn.textContent = "❌ Failed";
            btn.disabled = false;
        }
    };

    // 1. Fetch Profile Data
    try {
        const res = await fetch('/api/profile', { headers });
        if (!res.ok) throw new Error("Failed to load profile");
        const user = await res.json();

        full_name.value = user.full_name || '';
        profile_data.value = JSON.stringify(user.profile_data || {}, null, 2);

        // Populate Form Fields
        if (user.profile_data) {
            populateForm(user.profile_data);
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
                summary: document.getElementById('summary').value,
                skills: document.getElementById('skills').value.split(',').map(s => s.trim()).filter(Boolean),
                experience: [],
                education: []
            };

            // Scrape Dynamic Inputs
            document.querySelectorAll('.experience-item').forEach(el => {
                newProfileData.experience.push({
                    company: el.querySelector('.exp-company').value,
                    title: el.querySelector('.exp-title').value,
                    duration: el.querySelector('.exp-date').value,
                    description: el.querySelector('.exp-desc').value
                });
            });

            document.querySelectorAll('.education-item').forEach(el => {
                newProfileData.education.push({
                    school: el.querySelector('.edu-school').value,
                    degree: el.querySelector('.edu-degree').value,
                    date: el.querySelector('.edu-date').value
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
                } catch(e) {
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
