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
        <div class="resume-item">
            <div class="resume-info">
                <span class="resume-name">
                    ${isPrimary ? '<span class="primary-badge" title="Primary Resume">⭐</span>' : ''}
                    ${file.name}
                </span>
                <span class="resume-date">${new Date(file.created_at).toLocaleDateString()}</span>
            </div>
            <div style="display:flex; align-items:center;">
                <a href="${file.url}" target="_blank" class="resume-link">View</a>
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

    // 1. Fetch Profile Data
    try {
        const res = await fetch('/api/profile', { headers });
        if (!res.ok) throw new Error("Failed to load profile");
        const user = await res.json();

        full_name.value = user.full_name || '';
        profile_data.value = JSON.stringify(user.profile_data || {}, null, 2);

        // 2. Fetch Resumes for Dropdown
        const resumeRes = await fetch('/api/resumes', { headers });
        if (resumeRes.ok) {
            const files = await resumeRes.json();
            files.forEach(f => {
                const option = document.createElement('option');
                option.value = f.name; // Storing filename as identifier
                option.textContent = f.name;
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
            // Validate JSON
            let pData = {};
            try {
                pData = JSON.parse(profile_data.value);
            } catch (jsonErr) {
                throw new Error("Invalid JSON in profile data");
            }

            const payload = {
                full_name: full_name.value,
                primary_resume_name: resume_select.value,
                profile_data: pData
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
            // Create toast or status
            status_msg.textContent = "✅ Saved successfully!";
            status_msg.style.color = "#4ade80";

            // Re-format JSON
            profile_data.value = JSON.stringify(updated.profile_data, null, 2);

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
            profile_data.value = JSON.stringify(parsedData, null, 2);

            status_msg.textContent = "✅ Parsing Complete & Saved!";
            status_msg.style.color = "#4ade80";

        } catch (e) {
            console.error(e);
            status_msg.textContent = `❌ Parsing Failed: ${e.message}`;
            status_msg.style.color = "#f87171";
        } finally {
            parse_btn.disabled = false;
            parse_btn.textContent = "✨ Auto-Fill from Resume";
        }
    });
}
