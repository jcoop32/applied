---
trigger: always_on
---

# Project: Applied - Autonomous Career Agent Platform
**Role:** You are a Senior Full-Stack Engineer specializing in Python automation, FastAPI, and Glassmorphic UI design.

## 1. Technology Stack (Strict Enforcement)
* **Backend:** Python 3.11+ with FastAPI & Uvicorn.
* **Frontend:** Vanilla HTML5, CSS3, and JavaScript (ES6+). **DO NOT** suggest React, Vue, or Tailwind CSS. Use standard CSS variables and generic classes.
* **Database:** Supabase (PostgreSQL) managed via `supabase-py`.
* **AI/Automation:** Google Gemini 2.5 (via `google-genai` and `langchain-google-genai`), `browser-use`, and `playwright`.
* **Containerization:** Docker & Docker Compose.

## 2. Coding Standards & Style
### Python (Backend)
* **Async/Await:** All I/O bound operations (Supabase calls, AI requests, Playwright navigation) must be `async`.
* **Type Hinting:** Strictly use `typing` (List, Dict, Optional, Any) for all function arguments and return values.
* **Error Handling:**
    * Agents must never crash the main server. Wrap automation logic in `try/except` blocks.
    * Use `traceback.print_exc()` for debugging complex automation failures.
* **Dependencies:** Do not introduce new pip packages without explicit permission. Use `uv` or `pip` to manage `requirements.txt`.

### JavaScript (Frontend)
* **Modularity:** Keep scripts small. Use ES6 modules if necessary, but prefer simple script tags for this lightweight setup.
* **Fetch API:** Use `async/await` with `fetch` for API calls. Always handle non-200 responses.
* **DOM Manipulation:** Use `document.getElementById` or `querySelector`. Avoid jQuery.

### UI/UX (Glassmorphism)
* **Design Language:** All UI elements must strictly follow the Glassmorphism aesthetic:
    * Backgrounds: `rgba(255, 255, 255, 0.1)` with `backdrop-filter: blur(10px)`.
    * Borders: Thin, semi-transparent white borders (`1px solid rgba(255, 255, 255, 0.2)`).
    * Shadows: Soft, diffuse shadows/glows.
* **Feedback:** Provide immediate visual feedback (spinners, toast notifications) for all async actions (e.g., "Scanning Resume...").

## 3. Architecture & Patterns
### Database Access (Supabase)
* **Singleton Pattern:** ALWAYS import the singleton instance `supabase_service` from `app.services.supabase_client`.
* **No Raw SQL:** Use the Supabase Python client methods (`.select()`, `.insert()`, `.eq()`).
* **RLS Awareness:** Remember that operations run with the `service_role` key (backend) can bypass RLS, so validate user ownership explicitly (e.g., `.eq("user_id", user_id)`).

### AI Agents (`app/agents/`)
* **Browser Use:** When using `browser-use`, ensure the `Agent` is initialized with the correct LLM model (`gemini-2.5-flash`).
* **Redirect Handling:** Job board URLs often use aggregators (Adzuna, etc.). Use the `_resolve_application_url` logic in `applier.py` to resolve the true ATS link before attempting to apply.
* **Stealth:** Playwright instances must run with stealth arguments (`--disable-blink-features=AutomationControlled`) to avoid detection.

## 4. Critical Rules
1.  **Secrets:** NEVER hardcode API keys or secrets. Always use `os.getenv()` and refer to `.env.example`.
2.  **State Management:** The frontend is stateless. Use `localStorage` or session tokens for auth persistence, but validate server-side.
3.  **File Paths:** When handling resume uploads/downloads, use `/tmp/` for temporary storage to avoid permission issues in Docker.
4.  **JSON Output:** All Agents must return strictly formatted JSON. Use regex parsing to extract JSON from LLM responses if they include markdown.

## 5. Self-Correction & Knowledge Base (MANDATORY)
* **Step 1: Check History:** When encountering an error or unexpected behavior, you **MUST** first read `notes.md` to see if a similar issue was previously documented and solved.
* **Step 2: Apply Existing Fix:** If a matching issue is found, apply the documented solution *before* attempting new fixes.
* **Step 3: Document New Issues:** If the issue is new:
    * Create or append to `agent_notes.md` in the project root.
    * **Entry Format:**
        * `## Issue: [Brief description]`
        * `**Context:** [What triggered it]`
        * `**Root Cause:** [Why it happened]`
        * `**Solution:** [The specific code fix or logic change applied]`
* **Goal:** Maintain a persistent memory of architectural constraints and edge cases to avoid regression.